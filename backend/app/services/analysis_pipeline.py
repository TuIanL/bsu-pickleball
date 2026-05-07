from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.metrics import PerformanceMetrics
from app.schemas.pipeline import AnalysisArtifacts, AnalysisPipelineResult, PipelineStageResult
from app.schemas.tracking import ProjectedTrackPoint
from app.services.calibration_service import CalibrationService
from app.services.storage_service import StorageService
from app.services.video_service import VideoService
from app.vision.courtvision_calibration_engine.court_geometry import standard_court
from app.vision.pickleball_performance_engine.doubles_spacing_metrics import doubles_spacing
from app.vision.pickleball_performance_engine.heatmap_generator import generate_heatmap
from app.vision.pickleball_performance_engine.speed_metrics import speed_summaries
from app.vision.pickleball_performance_engine.trajectory_metrics import total_distances
from app.vision.pickleball_performance_engine.zone_metrics import kitchen_dwell


class AnalysisPipeline:
    """MVP analysis pipeline with model-free deterministic output.

    Real detector/tracker stages can replace `_mock_projected_tracks` later
    without changing API response schemas.
    """

    def __init__(
        self,
        video_service: VideoService | None = None,
        calibration_service: CalibrationService | None = None,
        storage: StorageService | None = None,
    ) -> None:
        self.video_service = video_service or VideoService()
        self.calibration_service = calibration_service or CalibrationService()
        self.storage = storage or StorageService()

    def run(
        self,
        job_id: str,
        video_id: str | None,
        calibration_id: str | None = None,
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
        stages.append(self._stage("detection", "人体检测", "skipped", "MVP 默认不加载 YOLO，返回确定性轨迹"))
        stages.append(self._stage("tracking", "多目标跟踪", "done", "已生成 MVP 轨迹样本"))

        tracks = self._mock_projected_tracks()
        stages.append(self._stage("projection", "脚点投影", "done", "轨迹已位于标准球场坐标系"))

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
            artifacts=AnalysisArtifacts(result_json_path=str(self.storage.output_json_path(job_id))),
            message="MVP pipeline completed with deterministic model-free tracking output.",
        )
        self._write_result(result)
        return result

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
    ) -> AnalysisPipelineResult:
        return AnalysisPipelineResult(
            job_id=job_id,
            video_id=video_id,
            calibration_id=calibration_id,
            status="failed",
            generated_at=datetime.now(timezone.utc),
            stages=[self._stage("video-read", "读取视频", "failed", message)],
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
