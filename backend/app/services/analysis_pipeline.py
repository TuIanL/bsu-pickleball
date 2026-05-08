from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.schemas.calibration import CourtPoint2D, ImagePoint
from app.schemas.metrics import PerformanceMetrics
from app.schemas.pipeline import AnalysisArtifacts, AnalysisPipelineResult, PipelineStageResult
from app.schemas.tracking import Detection, PlayerFramePosition, ProjectedTrackPoint, TrackingResult
from app.services.calibration_service import CalibrationService
from app.services.storage_service import StorageService
from app.services.video_service import VideoMetadata, VideoService
from app.vision.courtvision_calibration_engine.court_geometry import standard_court
from app.vision.pickleball_performance_engine.doubles_spacing_metrics import doubles_spacing
from app.vision.pickleball_performance_engine.heatmap_generator import generate_heatmap
from app.vision.pickleball_performance_engine.speed_metrics import speed_summaries
from app.vision.pickleball_performance_engine.trajectory_metrics import total_distances
from app.vision.pickleball_performance_engine.zone_metrics import kitchen_dwell
from app.vision.player_tracking_engine.footpoint_estimator import FootpointEstimator
from app.vision.player_tracking_engine.multi_object_tracker import MultiObjectTracker
from app.vision.player_tracking_engine.person_detector import PersonDetector
from app.vision.player_tracking_engine.player_projector import PlayerProjector


logger = logging.getLogger(__name__)


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
        frame_stride: int = 1,
    ) -> None:
        self.video_service = video_service or VideoService()
        self.calibration_service = calibration_service or CalibrationService()
        self.storage = storage or StorageService()
        self.detector = detector or PersonDetector()
        self.tracker = tracker
        self.footpoint_estimator = footpoint_estimator or FootpointEstimator()
        self.projector = projector or PlayerProjector(footpoint_estimator=self.footpoint_estimator)
        self.frame_stride = max(1, int(frame_stride))

    def run(
        self,
        job_id: str,
        video_id: str | None,
        calibration_id: str | None = None,
        frame_stride: int | None = None,
    ) -> AnalysisPipelineResult:
        stages: list[PipelineStageResult] = []
        video = self.video_service.get_video(video_id) if video_id else None

        if video_id and video is None:
            result = self._failed(job_id, video_id, calibration_id, "Uploaded video not found")
            self._write_result(result)
            return result

        stages.append(self._stage("video-read", "读取视频", "done", "视频元数据已加载" if video else "未提供视频，使用 MVP mock 轨迹"))

        calibration = self.calibration_service.get_calibration(calibration_id) if calibration_id else None
        stages.append(
            self._stage(
                "calibration",
                "场地标定",
                "done" if calibration else "skipped",
                "已加载手工标定" if calibration else "未提供标定，使用标准场地 mock 轨迹",
            )
        )

        tracking_artifact_path: str | None = None
        if video and calibration:
            try:
                tracking_result = self._run_tracking(
                    video=video,
                    homography=calibration.homography.values,
                    video_id=video_id,
                    calibration_id=calibration_id,
                    frame_stride=frame_stride or self.frame_stride,
                )
            except Exception as exc:
                stages.append(self._stage("tracking", "多目标跟踪", "failed", str(exc)))
                result = self._failed(job_id, video_id, calibration_id, str(exc), stages=stages)
                self._write_result(result)
                return result

            tracking_path = self.storage.tracking_json_path(job_id)
            self.storage.write_json(tracking_path, tracking_result.model_dump(mode="json"))
            tracking_artifact_path = str(tracking_path)

            stages.append(
                self._stage(
                    "detection",
                    "人体检测",
                    "done",
                    f"已处理 {tracking_result.processed_frame_count} 帧，检测到 {len(tracking_result.detections)} 个人体框",
                )
            )
            stages.append(
                self._stage(
                    "tracking",
                    "多目标跟踪",
                    "done",
                    f"已输出 {len(tracking_result.tracks)} 个当前轨迹样本",
                )
            )
            stages.append(
                self._stage(
                    "projection",
                    "脚点投影",
                    "done",
                    f"已生成 {len(tracking_result.positions)} 个场地坐标球员位置",
                )
            )
            tracks = self._positions_to_projected_tracks(tracking_result.positions)
            message = "Pipeline completed with Player Tracking Engine output."
        else:
            stages.append(self._stage("detection", "人体检测", "skipped", "未提供视频或标定，返回确定性轨迹"))
            stages.append(self._stage("tracking", "多目标跟踪", "done", "已生成 MVP 轨迹样本"))
            tracks = self._mock_projected_tracks()
            stages.append(self._stage("projection", "脚点投影", "done", "轨迹已位于标准球场坐标系"))
            message = "MVP pipeline completed with deterministic model-free tracking output."

        metrics = self._compute_metrics(tracks)
        stages.append(self._stage("metrics", "运动指标", "done", "已计算距离、速度、厨房区、双打间距和热力图"))
        stages.append(self._stage("visualization", "可视化视频", "skipped", "MVP 暂不生成叠加视频文件"))

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
            ),
            message=message,
        )
        self._write_result(result)
        return result

    def _run_tracking(
        self,
        video: VideoMetadata,
        homography: list[list[float]],
        video_id: str | None,
        calibration_id: str | None,
        frame_stride: int,
    ) -> TrackingResult:
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
        processed_frame_count = 0
        all_detections: list[Detection] = []
        all_tracks = []
        positions: list[PlayerFramePosition] = []
        tracker = self.tracker or MultiObjectTracker()

        frame_index = 0
        try:
            while True:
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

                all_detections.extend(detections)
                all_tracks.extend(tracks)
                positions.extend(frame_positions)
                processed_frame_count += 1

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
            "Player tracking completed: processed %s frames, %s positions",
            processed_frame_count,
            len(positions),
        )

        return TrackingResult(
            video_id=video_id,
            calibration_id=calibration_id,
            fps=fps,
            frame_count=frame_count,
            processed_frame_count=processed_frame_count,
            frame_stride=stride,
            detections=all_detections,
            tracks=all_tracks,
            positions=positions,
        )

    def _detect_frame(self, frame: object, frame_index: int) -> list[Detection]:
        if hasattr(self.detector, "detect_frame"):
            return self.detector.detect_frame(frame, frame_index)
        return self.detector.detect(frame)

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

    def _compute_metrics(self, tracks: list[ProjectedTrackPoint]) -> PerformanceMetrics:
        return PerformanceMetrics(
            distances=total_distances(tracks),
            speeds=speed_summaries(tracks),
            kitchen_dwell=kitchen_dwell(tracks),
            doubles_spacing=doubles_spacing(tracks),
            heatmap=generate_heatmap(tracks),
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
