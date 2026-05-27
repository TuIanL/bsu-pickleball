"""分析流水线 —— MVP 版本的端到端视频分析流程（检测→跟踪→投影→指标计算→可视化）。"""

from __future__ import annotations

import logging
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

from app.schemas.calibration import CourtPoint2D, ImagePoint
from app.schemas.metrics import PerformanceMetrics
from app.schemas.pipeline import AnalysisArtifacts, AnalysisPipelineResult, PipelineStageResult
from app.schemas.pose import PoseOverlayArtifact, default_skeleton_edges
from app.schemas.tracking import (
    Detection,
    DetectionOverlayFrame,
    FrameDetection,
    PlayerFramePosition,
    PlayerTrajectoryArtifact,
    ProjectedTrackPoint,
    SourceFrameSize,
    TrackingOverlayArtifact,
    TrackingResult,
)
from app.services.calibration_service import CalibrationService
from app.services.storage_service import StorageService
from app.services.video_service import VideoMetadata, VideoService
from app.core.config import get_settings
from app.vision.courtvision_calibration_engine.court_geometry import standard_court
from app.vision.pickleball_performance_engine.doubles_spacing_metrics import doubles_spacing
from app.vision.pickleball_performance_engine.heatmap_generator import generate_heatmap
from app.vision.pickleball_performance_engine.speed_metrics import speed_summaries
from app.vision.pickleball_performance_engine.trajectory_metrics import total_distances
from app.vision.pickleball_performance_engine.zone_metrics import kitchen_dwell
from app.vision.player_tracking_engine.footpoint_estimator import FootpointEstimator
from app.vision.player_tracking_engine.multi_object_tracker import MultiObjectTracker
from app.vision.player_tracking_engine.person_detector import EmptyPersonDetector, PersonDetector
from app.vision.player_tracking_engine.player_identity import PlayerIdentityConfig, PlayerIdentityManager
from app.vision.player_tracking_engine.player_projector import PlayerProjector
from app.vision.player_tracking_engine.primary_player_selector import PrimaryPlayerSelector
from app.vision.pose.rtmpose26_adapter import RTMPose26Adapter


logger = logging.getLogger(__name__)
ProgressCallback = Callable[[PipelineStageResult], None]


class CancellationToken(Protocol):
    def raise_if_cancelled(self) -> None:
        ...


@dataclass
class _TrackingRunOutput:
    tracking: TrackingResult
    player_trajectories: PlayerTrajectoryArtifact | None = None
    player_metric_tracks: list[ProjectedTrackPoint] | None = None
    pose: PoseOverlayArtifact | None = None
    pose_stage: PipelineStageResult | None = None


class AnalysisPipeline:
    """MVP analysis pipeline with real tracking when video and calibration are available."""

    def __init__(
        self,
        video_service: VideoService | None = None,
        calibration_service: CalibrationService | None = None,
        storage: StorageService | None = None,
        detector: Any | None = None,
        tracker: MultiObjectTracker | None = None,
        footpoint_estimator: FootpointEstimator | None = None,
        projector: PlayerProjector | None = None,
        primary_player_selector: PrimaryPlayerSelector | None = None,
        pose_estimator: Any | None = None,
        frame_stride: int | None = None,
    ) -> None:
        self.video_service = video_service or VideoService()
        self.calibration_service = calibration_service or CalibrationService()
        self.storage = storage or StorageService()
        self.settings = get_settings()
        detector_was_injected = detector is not None
        self.detector = detector or (
            PersonDetector(
                model_path=self.settings.default_detector_model,
                conf_threshold=self.settings.detector_confidence,
                device=self.settings.detector_device,
            )
            if self.settings.enable_model_inference
            else EmptyPersonDetector()
        )
        self.model_inference_enabled = (
            not isinstance(self.detector, EmptyPersonDetector)
            if detector_was_injected
            else self.settings.enable_model_inference
        )
        self.tracker = tracker
        self.footpoint_estimator = footpoint_estimator or FootpointEstimator()
        self.projector = projector or PlayerProjector(
            footpoint_estimator=self.footpoint_estimator,
            include_invalid=True,
        )
        self.primary_player_selector = primary_player_selector or PrimaryPlayerSelector(
            min_confidence=self.settings.primary_player_min_confidence,
            max_subjects=self.settings.primary_player_max_subjects,
            min_box_area_ratio=self.settings.primary_player_min_box_area_ratio,
            max_box_area_ratio=self.settings.primary_player_max_box_area_ratio,
            court_margin_ft=self.settings.primary_player_court_margin_ft,
        )
        self.pose_estimator = pose_estimator or (
            RTMPose26Adapter(
                config_path=self.settings.rtmpose_config_path,
                checkpoint_path=self.settings.rtmpose_checkpoint_path,
                device=self.settings.rtmpose_device,
                conf_threshold=self.settings.pose_confidence,
                keypoint_schema=self.settings.pose_keypoint_schema,
            )
            if self.settings.enable_pose_inference
            else None
        )
        self.pose_inference_enabled = self.pose_estimator is not None
        self.frame_stride = max(1, int(frame_stride or self.settings.overlay_frame_stride))

    def run(
        self,
        job_id: str,
        video_id: str | None,
        calibration_id: str | None = None,
        frame_stride: int | None = None,
        progress_callback: ProgressCallback | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> AnalysisPipelineResult:
        stages: list[PipelineStageResult] = []
        self._check_cancelled(cancellation_token)
        video = self.video_service.get_video(video_id) if video_id else None

        if video_id and video is None:
            result = self._failed(job_id, video_id, calibration_id, "Uploaded video not found")
            self._write_result(result)
            return result

        video_stage = self._stage("video-read", "读取视频", "done", "视频元数据已加载" if video else "未提供视频，使用 MVP mock 轨迹")
        stages.append(video_stage)
        self._notify_progress(progress_callback, video_stage)
        self._check_cancelled(cancellation_token)

        calibration = self.calibration_service.get_calibration(calibration_id) if calibration_id else None
        calibration_stage = self._stage(
            "calibration",
            "场地标定",
            "done" if calibration else "skipped",
            "已加载手工标定" if calibration else "未提供标定，使用标准场地 mock 轨迹",
        )
        stages.append(calibration_stage)
        self._notify_progress(progress_callback, calibration_stage)
        self._check_cancelled(cancellation_token)

        source_video_url = f"/api/videos/{video_id}/stream" if video_id else None
        tracking_artifact_path: str | None = None
        tracking_overlay_artifact_path: str | None = None
        tracking_overlay_url: str | None = None
        tracking_overlay_status: str | None = None
        tracking_overlay_detail: str | None = None
        pose_overlay_artifact_path: str | None = None
        pose_overlay_url: str | None = None
        pose_overlay_status: str | None = None
        pose_overlay_detail: str | None = None
        player_trajectory_json_path: str | None = None
        player_trajectory_csv_path: str | None = None
        player_trajectory_url: str | None = None
        player_trajectory_status: str | None = None
        player_trajectory_detail: str | None = None
        if video and calibration:
            try:
                self._notify_progress(
                    progress_callback,
                    self._stage("frame-sampling", "抽帧采样", "active", "正在读取视频帧并按配置抽样"),
                )
                run_output = self._run_tracking(
                    job_id=job_id,
                    video=video,
                    homography=calibration.homography.values,
                    video_id=video_id,
                    calibration_id=calibration_id,
                    frame_stride=frame_stride or self.frame_stride,
                    cancellation_token=cancellation_token,
                )
            except Exception as exc:
                failed_stage = self._stage("tracking", "多目标跟踪", "failed", str(exc))
                stages.append(failed_stage)
                self._notify_progress(progress_callback, failed_stage)
                result = self._failed(job_id, video_id, calibration_id, str(exc), stages=stages)
                self._write_result(result)
                return result
            tracking_result = run_output.tracking
            sampling_stage = self._stage(
                "frame-sampling",
                "抽帧采样",
                "done",
                f"已按配置帧间隔读取 {tracking_result.processed_frame_count} 帧",
            )
            stages.append(sampling_stage)
            self._notify_progress(progress_callback, sampling_stage)
            self._check_cancelled(cancellation_token)

            tracking_path = self.storage.tracking_json_path(job_id)
            self.storage.write_json(tracking_path, tracking_result.model_dump(mode="json"))
            tracking_artifact_path = str(tracking_path)
            tracking_overlay = self._build_tracking_overlay(
                job_id,
                video_id,
                tracking_result,
                enabled=self.model_inference_enabled,
            )
            tracking_overlay_path = self.storage.tracking_overlay_json_path(job_id)
            self.storage.write_json(tracking_overlay_path, tracking_overlay.model_dump(mode="json"))
            tracking_overlay_artifact_path = str(tracking_overlay_path)
            tracking_overlay_url = f"/api/analysis/jobs/{job_id}/artifacts/tracking-overlay"
            tracking_overlay_status = tracking_overlay.status
            tracking_overlay_detail = tracking_overlay.detail

            if run_output.pose is not None:
                pose_overlay_path = self.storage.pose_overlay_json_path(job_id)
                self.storage.write_json(pose_overlay_path, run_output.pose.model_dump(mode="json"))
                pose_overlay_artifact_path = str(pose_overlay_path)
                pose_overlay_url = f"/api/analysis/jobs/{job_id}/artifacts/pose-overlay"
                pose_overlay_status = run_output.pose.status
                pose_overlay_detail = run_output.pose.detail
            elif run_output.pose_stage is not None:
                pose_overlay_status = "unavailable"
                pose_overlay_detail = run_output.pose_stage.detail

            if run_output.player_trajectories is not None:
                player_trajectory_json = self.storage.player_trajectory_json_path(job_id)
                player_trajectory_csv = self.storage.player_trajectory_csv_path(job_id)
                self.storage.write_json(player_trajectory_json, run_output.player_trajectories.model_dump(mode="json"))
                self._write_player_trajectory_csv(player_trajectory_csv, run_output.player_trajectories)
                player_trajectory_json_path = str(player_trajectory_json)
                player_trajectory_csv_path = str(player_trajectory_csv)
                player_trajectory_url = f"/api/analysis/jobs/{job_id}/artifacts/player-trajectories"
                player_count = len(run_output.player_trajectories.players)
                sample_count = sum(len(samples) for samples in run_output.player_trajectories.players.values())
                player_trajectory_status = "available" if sample_count else "no_detections"
                player_trajectory_detail = f"已生成 {player_count} 名球员的 {sample_count} 个公制轨迹样本"

            detection_stage = self._stage(
                "detection",
                "人体检测",
                "done" if self.model_inference_enabled else "skipped",
                self._detection_stage_detail(tracking_result, enabled=self.model_inference_enabled),
            )
            stages.append(detection_stage)
            self._notify_progress(progress_callback, detection_stage)
            self._check_cancelled(cancellation_token)
            tracking_stage = self._stage(
                "tracking",
                "多目标跟踪",
                "done" if self.model_inference_enabled else "skipped",
                (
                    f"已输出 {len(tracking_result.tracks)} 个当前轨迹样本"
                    if self.model_inference_enabled
                    else "YOLO 人体检测未运行，未生成可跟踪人体框"
                ),
            )
            stages.append(tracking_stage)
            self._notify_progress(progress_callback, tracking_stage)
            self._check_cancelled(cancellation_token)
            pose_stage = (
                run_output.pose_stage
                or self._stage(
                    "pose",
                    "人体姿态",
                    "skipped",
                    "RTMPose 姿态识别未启用，暂不生成骨架关节",
                )
            )
            stages.append(pose_stage)
            self._notify_progress(progress_callback, pose_stage)
            self._check_cancelled(cancellation_token)
            projection_stage = self._stage(
                "projection",
                "脚点投影",
                "done",
                self._projection_stage_detail(tracking_result.positions),
            )
            stages.append(projection_stage)
            self._notify_progress(progress_callback, projection_stage)
            self._check_cancelled(cancellation_token)
            tracks = run_output.player_metric_tracks or self._positions_to_projected_tracks(tracking_result.positions)
            message = "Pipeline completed with Player Tracking Engine output."
        elif video and not calibration:
            limited_stages = [
                self._stage("frame-sampling", "抽帧采样", "skipped", "未提供标定，跳过真实抽帧分析"),
                self._stage("detection", "人体检测", "skipped", "缺少场地标定，暂不运行真实检测"),
                self._stage("tracking", "多目标跟踪", "skipped", "需要有效标定后才能生成可用场地轨迹"),
                self._stage("pose", "人体姿态", "skipped", "需要检测和跟踪框后才能运行 RTMPose"),
                self._stage("projection", "脚点投影", "skipped", "未提供标定，无法投影到标准球场坐标"),
            ]
            for stage in limited_stages:
                stages.append(stage)
                self._notify_progress(progress_callback, stage)
                self._check_cancelled(cancellation_token)
            tracks = []
            message = "Limited pipeline completed without court calibration; no court-projected tracks were generated."
        else:
            mock_stages = [
                self._stage("frame-sampling", "抽帧采样", "skipped", "未提供真实视频，跳过抽帧"),
                self._stage("detection", "人体检测", "skipped", "未提供视频或标定，返回确定性轨迹"),
                self._stage("tracking", "多目标跟踪", "done", "已生成 MVP 轨迹样本"),
                self._stage("pose", "人体姿态", "skipped", "未提供真实视频，跳过骨架关节识别"),
            ]
            for stage in mock_stages:
                stages.append(stage)
                self._notify_progress(progress_callback, stage)
                self._check_cancelled(cancellation_token)
            tracks = self._mock_projected_tracks()
            projection_stage = self._stage("projection", "脚点投影", "done", "轨迹已位于标准球场坐标系")
            stages.append(projection_stage)
            self._notify_progress(progress_callback, projection_stage)
            self._check_cancelled(cancellation_token)
            message = "MVP pipeline completed with deterministic model-free tracking output."

        metrics = self._compute_metrics(tracks)
        metrics_stage = self._stage("metrics", "运动指标", "done", "已计算距离、速度、厨房区、双打间距和热力图")
        stages.append(metrics_stage)
        self._notify_progress(progress_callback, metrics_stage)
        self._check_cancelled(cancellation_token)
        visualization_stage = self._stage("visualization", "可视化视频", "skipped", "MVP 暂不生成叠加视频文件")
        stages.append(visualization_stage)
        self._notify_progress(progress_callback, visualization_stage)
        self._check_cancelled(cancellation_token)

        result = AnalysisPipelineResult(
            job_id=job_id,
            video_id=video_id,
            calibration_id=calibration_id,
            status="completed",
            generated_at=datetime.now(timezone.utc),
            stages=stages,
            tracks=tracks,
            metrics=metrics,
            artifacts=AnalysisArtifacts(
                result_json_path=str(self.storage.output_json_path(job_id)),
                tracking_result_json_path=tracking_artifact_path,
                tracking_overlay_json_path=tracking_overlay_artifact_path,
                tracking_overlay_url=tracking_overlay_url,
                pose_overlay_json_path=pose_overlay_artifact_path,
                pose_overlay_url=pose_overlay_url,
                player_trajectory_json_path=player_trajectory_json_path,
                player_trajectory_csv_path=player_trajectory_csv_path,
                player_trajectory_url=player_trajectory_url,
                source_video_url=source_video_url,
                tracking_overlay_status=tracking_overlay_status,
                tracking_overlay_detail=tracking_overlay_detail,
                pose_overlay_status=pose_overlay_status,
                pose_overlay_detail=pose_overlay_detail,
                player_trajectory_status=player_trajectory_status,
                player_trajectory_detail=player_trajectory_detail,
            ),
            message=message,
        )
        self._write_result(result)
        return result

    def _run_tracking(
        self,
        job_id: str,
        video: VideoMetadata,
        homography: list[list[float]],
        video_id: str | None,
        calibration_id: str | None,
        frame_stride: int,
        cancellation_token: CancellationToken | None = None,
    ) -> _TrackingRunOutput:
        try:
            import cv2  # type: ignore
        except ImportError as exc:
            raise RuntimeError("OpenCV is required to read video frames") from exc

        stride = max(1, int(frame_stride))
        capture = cv2.VideoCapture(video.path)
        if not capture.isOpened():
            raise RuntimeError(f"Could not read uploaded video: {video.path}")

        raw_fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        fps = raw_fps if raw_fps > 0 else 0.0
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        frame_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        frame_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        processed_frame_count = 0
        all_detections: list[Detection] = []
        overlay_frames: list[DetectionOverlayFrame] = []
        all_tracks = []
        positions: list[PlayerFramePosition] = []
        pose_frames = []
        pose_stage = (
            self._stage("pose", "人体姿态", "skipped", "RTMPose 姿态识别未启用，暂不生成骨架关节")
            if self.pose_estimator is None
            else None
        )
        pose_error: str | None = None
        tracker = self.tracker or MultiObjectTracker(max_lost=self.settings.player_identity_lost_buffer_frames)
        identity_manager = PlayerIdentityManager(
            PlayerIdentityConfig(
                max_players=self.settings.player_identity_max_players,
                fps=fps if fps > 0 else 30.0,
                match_threshold=self.settings.player_identity_match_threshold,
                max_reconnect_distance_m=self.settings.player_identity_max_reconnect_distance_m,
                max_speed_mps=self.settings.player_identity_max_speed_mps,
                lost_buffer_frames=self.settings.player_identity_lost_buffer_frames,
                inactive_buffer_frames=self.settings.player_identity_inactive_buffer_frames,
                interpolation_buffer_frames=self.settings.player_identity_interpolation_buffer_frames,
                court_buffer_m=self.settings.player_identity_court_buffer_m,
                input_court_unit="ft",
                smoothing_window=self.settings.player_identity_smoothing_window,
            )
        )

        frame_index = 0
        try:
            while True:
                self._check_cancelled(cancellation_token)
                ok, frame = capture.read()
                if not ok:
                    break
                if frame_index % stride != 0:
                    frame_index += 1
                    continue

                timestamp = frame_index / raw_fps if raw_fps > 0 else float(frame_index)
                detections = self._detect_frame(frame, frame_index)
                tracks = tracker.update(detections)
                footpoints = {track.track_id: self.footpoint_estimator.estimate(track) for track in tracks}
                frame_positions = self.projector.project(
                    tracks=tracks,
                    homography=homography,
                    frame_index=frame_index,
                    timestamp=timestamp,
                    footpoints=footpoints,
                )
                primary_player_track_ids = {
                    selection.track_id
                    for selection in self.primary_player_selector.select(
                        tracks=tracks,
                        positions=frame_positions,
                        frame_width=frame_width,
                        frame_height=frame_height,
                    )
                }
                frame_detections = self._tracks_to_frame_detections(
                    tracks=tracks,
                    frame_index=frame_index,
                    timestamp=timestamp,
                    frame_width=frame_width,
                    frame_height=frame_height,
                    eligible_track_ids=primary_player_track_ids,
                )
                player_samples = identity_manager.update(
                    frame_index=frame_index,
                    positions=frame_positions,
                    eligible_track_ids=primary_player_track_ids,
                )
                player_by_track = {
                    sample.track_id: sample.player_id
                    for sample in player_samples
                    if sample.track_id is not None and sample.tracking_status == "detected"
                }
                for detection in frame_detections:
                    if detection.track_id is None:
                        continue
                    player_id = player_by_track.get(int(detection.track_id))
                    if player_id is not None:
                        detection.player_id = player_id
                        detection.label = f"{player_id.replace('Player_', 'P')} / T{detection.track_id}"

                all_detections.extend(detections)
                overlay_frames.append(
                    DetectionOverlayFrame(
                        frame_index=frame_index,
                        timestamp_seconds=timestamp,
                        detections=frame_detections,
                    )
                )
                all_tracks.extend(tracks)
                positions.extend(frame_positions)
                if self.pose_estimator is not None and frame_detections and pose_error is None:
                    try:
                        pose_frame = self.pose_estimator.estimate_frame(
                            frame=frame,
                            subjects=frame_detections,
                            frame_index=frame_index,
                            timestamp_seconds=timestamp,
                        )
                        pose_frame.subjects = [subject for subject in pose_frame.subjects if subject.keypoints]
                        if pose_frame.subjects:
                            pose_frames.append(pose_frame)
                    except Exception as exc:
                        pose_error = str(exc)
                        pose_frames = []
                processed_frame_count += 1
                self._check_cancelled(cancellation_token)

                if processed_frame_count == 1 or processed_frame_count % 30 == 0:
                    logger.info(
                        "Player tracking progress: processed %s/%s frames",
                        processed_frame_count,
                        frame_count or "unknown",
                    )

                frame_index += 1
        finally:
            capture.release()

        logger.info(
            "Player tracking completed: processed %s frames, %s projected position samples",
            processed_frame_count,
            len(positions),
        )

        tracking_result = TrackingResult(
            video_id=video_id,
            calibration_id=calibration_id,
            fps=fps,
            frame_count=frame_count,
            frame_width=frame_width,
            frame_height=frame_height,
            processed_frame_count=processed_frame_count,
            frame_stride=stride,
            detections=all_detections,
            overlay_frames=overlay_frames,
            tracks=all_tracks,
            positions=positions,
        )
        player_trajectories = identity_manager.to_artifact(
            job_id=job_id,
            video_id=video_id,
            fps=fps,
            frame_count=frame_count,
            processed_frame_count=processed_frame_count,
            frame_stride=stride,
        )
        player_metric_tracks = identity_manager.to_projected_track_points(output_court_unit="ft")
        if self.pose_estimator is not None:
            if pose_error:
                pose_stage = self._stage("pose", "人体姿态", "skipped", f"RTMPose 不可用：{pose_error}")
            elif pose_frames:
                pose_stage = self._stage("pose", "人体姿态", "done", f"已生成 {sum(len(frame.subjects) for frame in pose_frames)} 组骨架关节")
            else:
                pose_stage = self._stage("pose", "人体姿态", "skipped", "没有可用人体框或骨架关键点，未生成骨架关节")
        pose_artifact = None
        if pose_frames:
            pose_artifact = PoseOverlayArtifact(
                job_id=job_id,
                video_id=video_id,
                status="available",
                detail=f"已生成 {sum(len(frame.subjects) for frame in pose_frames)} 组骨架关节",
                keypoint_schema=self.settings.pose_keypoint_schema,
                source=SourceFrameSize(width=max(1, frame_width), height=max(1, frame_height)),
                skeleton_edges=default_skeleton_edges(),
                frames=pose_frames,
            )
        return _TrackingRunOutput(
            tracking=tracking_result,
            player_trajectories=player_trajectories,
            player_metric_tracks=player_metric_tracks,
            pose=pose_artifact,
            pose_stage=pose_stage,
        )

    def _detect_frame(self, frame: object, frame_index: int) -> list[Detection]:
        if hasattr(self.detector, "detect_frame"):
            return self.detector.detect_frame(frame, frame_index)
        return self.detector.detect(frame)

    @staticmethod
    def _tracks_to_frame_detections(
        tracks,
        frame_index: int,
        timestamp: float,
        frame_width: int,
        frame_height: int,
        eligible_track_ids: set[int] | None = None,
    ) -> list[FrameDetection]:
        source_width = max(1, int(frame_width))
        source_height = max(1, int(frame_height))
        return [
            FrameDetection(
                frame_index=frame_index,
                timestamp_seconds=timestamp,
                bbox=track.bbox,
                confidence=track.confidence,
                track_id=str(track.track_id),
                source_width=source_width,
                source_height=source_height,
            )
            for track in tracks
            if not track.lost and (eligible_track_ids is None or track.track_id in eligible_track_ids)
        ]

    @staticmethod
    def _detection_stage_detail(tracking_result: TrackingResult, enabled: bool = True) -> str:
        if not enabled:
            return "模型推理未启用，未运行 YOLO 人体检测；可设置 PICKLEBALL_ENABLE_MODEL_INFERENCE=true"
        detection_count = len(tracking_result.detections)
        overlay_count = sum(len(frame.detections) for frame in tracking_result.overlay_frames)
        dropped_count = max(0, detection_count - overlay_count)
        if detection_count == 0:
            return (
                f"已处理 {tracking_result.processed_frame_count} 帧，没有检测到可用人体框；"
                "请检查模型配置、拍摄角度、视频清晰度或标定范围"
            )
        if overlay_count == 0:
            return (
                f"已处理 {tracking_result.processed_frame_count} 帧，检测到 {detection_count} 个人体框，"
                "但没有通过主要球员置信度筛选的可渲染比赛球员框"
            )
        return (
            f"已处理 {tracking_result.processed_frame_count} 帧，检测到 {detection_count} 个人体框，"
            f"其中 {overlay_count} 个通过主要球员筛选并用于视频叠加，过滤 {dropped_count} 个低置信度或非主体人物框"
        )

    def _build_tracking_overlay(
        self,
        job_id: str,
        video_id: str | None,
        tracking_result: TrackingResult,
        enabled: bool = True,
    ) -> TrackingOverlayArtifact:
        detection_count = sum(len(frame.detections) for frame in tracking_result.overlay_frames)
        if not enabled:
            status = "unavailable"
            detail = "YOLO 人体检测未启用，未运行模型推理；请启用后重新分析"
        elif detection_count:
            status = "available"
            raw_count = len(tracking_result.detections)
            dropped_count = max(0, raw_count - detection_count)
            detail = (
                f"已生成 {detection_count} 个通过主要球员置信度筛选的可渲染比赛球员框；"
                f"原始检测 {raw_count} 个，过滤 {dropped_count} 个低置信度或非主体人物框"
            )
        else:
            status = "no_detections"
            detail = (
                f"YOLO 已运行并检测到 {len(tracking_result.detections)} 个人体框，"
                "但没有通过主要球员置信度筛选的可渲染比赛球员框；请检查阈值、球员人数、拍摄角度、视频清晰度或模型配置"
            )
        return TrackingOverlayArtifact(
            job_id=job_id,
            video_id=video_id,
            status=status,
            detail=detail,
            source=SourceFrameSize(
                width=max(1, tracking_result.frame_width),
                height=max(1, tracking_result.frame_height),
            ),
            fps=tracking_result.fps,
            frame_count=tracking_result.frame_count,
            processed_frame_count=tracking_result.processed_frame_count,
            frame_stride=tracking_result.frame_stride,
            frames=tracking_result.overlay_frames,
        )

    def _positions_to_projected_tracks(self, positions: list[PlayerFramePosition]) -> list[ProjectedTrackPoint]:
        projected: list[ProjectedTrackPoint] = []
        for position in positions:
            if not position.valid or position.court_position is None:
                continue
            court_x, court_y = position.court_position
            if not (0.0 <= court_x <= 20.0 and 0.0 <= court_y <= 44.0):
                continue
            image_x, image_y = position.image_footpoint
            projected.append(
                ProjectedTrackPoint(
                    frame_index=position.frame_index,
                    timestamp_seconds=position.timestamp,
                    track_id=str(position.track_id),
                    image_point=ImagePoint(x=image_x, y=image_y),
                    confidence=position.confidence,
                    side="unknown",
                    court_point=CourtPoint2D(x=court_x, y=court_y),
                )
            )
        return projected

    @staticmethod
    def _projection_stage_detail(positions: list[PlayerFramePosition]) -> str:
        valid_count = sum(1 for position in positions if position.valid and position.court_position is not None)
        invalid_count = len(positions) - valid_count
        if invalid_count:
            return f"已生成 {valid_count} 个有效场地坐标球员位置，并保留 {invalid_count} 个越界投影诊断样本"
        return f"已生成 {valid_count} 个有效场地坐标球员位置"

    def _compute_metrics(self, tracks: list[ProjectedTrackPoint]) -> PerformanceMetrics:
        return PerformanceMetrics(
            distances=total_distances(tracks),
            speeds=speed_summaries(tracks),
            kitchen_dwell=kitchen_dwell(tracks),
            doubles_spacing=doubles_spacing(tracks),
            heatmap=generate_heatmap(tracks),
        )

    @staticmethod
    def _write_player_trajectory_csv(path: Path, artifact: PlayerTrajectoryArtifact) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "frame_index",
                    "timestamp_seconds",
                    "player_id",
                    "track_id",
                    "bbox",
                    "image_footpoint",
                    "court_x",
                    "court_y",
                    "smoothed_court_x",
                    "smoothed_court_y",
                    "court_unit",
                    "confidence",
                    "tracking_status",
                    "is_interpolated",
                ],
            )
            writer.writeheader()
            for player_id, samples in sorted(artifact.players.items()):
                for sample in samples:
                    writer.writerow(
                        {
                            "frame_index": sample.frame_index,
                            "timestamp_seconds": sample.timestamp_seconds,
                            "player_id": player_id,
                            "track_id": sample.track_id if sample.track_id is not None else "",
                            "bbox": sample.bbox or "",
                            "image_footpoint": sample.image_footpoint or "",
                            "court_x": sample.court_x,
                            "court_y": sample.court_y,
                            "smoothed_court_x": sample.smoothed_court_x if sample.smoothed_court_x is not None else "",
                            "smoothed_court_y": sample.smoothed_court_y if sample.smoothed_court_y is not None else "",
                            "court_unit": sample.court_unit,
                            "confidence": sample.confidence,
                            "tracking_status": sample.tracking_status,
                            "is_interpolated": sample.is_interpolated,
                        }
                    )

    def _write_result(self, result: AnalysisPipelineResult) -> None:
        self.storage.write_json(self.storage.output_json_path(result.job_id), result.model_dump(mode="json"))

    def _failed(
        self,
        job_id: str,
        video_id: str | None,
        calibration_id: str | None,
        message: str,
        stages: list[PipelineStageResult] | None = None,
    ) -> AnalysisPipelineResult:
        return AnalysisPipelineResult(
            job_id=job_id,
            video_id=video_id,
            calibration_id=calibration_id,
            status="failed",
            generated_at=datetime.now(timezone.utc),
            stages=stages or [self._stage("video-read", "读取视频", "failed", message)],
            tracks=[],
            metrics=self._compute_metrics([]),
            artifacts=AnalysisArtifacts(result_json_path=str(self.storage.output_json_path(job_id))),
            message=message,
        )

    @staticmethod
    def _stage(stage_id: str, label: str, status: str, detail: str) -> PipelineStageResult:
        return PipelineStageResult(id=stage_id, label=label, status=status, detail=detail)

    @staticmethod
    def _notify_progress(progress_callback: ProgressCallback | None, stage: PipelineStageResult) -> None:
        if progress_callback is not None:
            progress_callback(stage)

    @staticmethod
    def _check_cancelled(cancellation_token: CancellationToken | None) -> None:
        if cancellation_token is not None:
            cancellation_token.raise_if_cancelled()

    @staticmethod
    def _mock_projected_tracks() -> list[ProjectedTrackPoint]:
        court = standard_court()
        raw_points = [
            ("near-a", "near", 0, 0.0, 5.0, 12.0),
            ("near-a", "near", 1, 1.0, 8.0, 15.5),
            ("near-a", "near", 2, 2.0, 10.0, 18.0),
            ("near-b", "near", 0, 0.0, 15.0, 11.0),
            ("near-b", "near", 1, 1.0, 13.5, 14.0),
            ("near-b", "near", 2, 2.0, 12.0, 16.0),
        ]
        tracks = []
        for track_id, side, frame_index, timestamp, x, y in raw_points:
            x = min(max(x, 0.0), court.width_ft)
            y = min(max(y, 0.0), court.length_ft)
            tracks.append(
                ProjectedTrackPoint(
                    frame_index=frame_index,
                    timestamp_seconds=timestamp,
                    track_id=track_id,
                    image_point={"x": x * 10.0, "y": y * 10.0},
                    confidence=0.95,
                    side=side,
                    court_point={"x": x, "y": y},
                )
            )
        return tracks
