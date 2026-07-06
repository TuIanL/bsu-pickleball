"""本地文件存储服务 —— 管理上传视频、JSON 产物、标定文件和临时文件的读写。"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings


class StorageService:
    """Small local-file storage helper for MVP uploads and JSON artifacts."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.settings.ensure_data_dirs()

    @property
    def uploads_dir(self) -> Path:
        return self.settings.resolved_uploads_dir

    @property
    def outputs_dir(self) -> Path:
        return self.settings.resolved_outputs_dir

    @property
    def calibrations_dir(self) -> Path:
        return self.settings.resolved_calibrations_dir

    @property
    def tmp_dir(self) -> Path:
        return self.settings.resolved_tmp_dir

    def write_json(self, path: Path, payload: dict[str, Any]) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def write_json_atomic(self, path: Path, payload: dict[str, Any]) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f".{path.name}.tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp_path, path)
        return path

    def read_json(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def delete_path(path: Path) -> bool:
        if not path.exists():
            return False
        if path.is_dir():
            shutil.rmtree(path)
            return True
        path.unlink()
        return True

    @staticmethod
    def delete_path_tree(path: Path) -> bool:
        return StorageService.delete_path(path)

    def output_json_path(self, job_id: str) -> Path:
        return self.outputs_dir / f"{job_id}.json"

    def job_json_path(self, job_id: str) -> Path:
        return self.outputs_dir / "jobs" / f"{job_id}.json"

    def jobs_dir(self) -> Path:
        return self.outputs_dir / "jobs"

    def report_json_path(self, job_id: str) -> Path:
        return self.outputs_dir / "reports" / f"{job_id}.json"

    def tracking_json_path(self, job_id: str) -> Path:
        return self.outputs_dir / job_id / "tracking_result.json"

    def tracking_overlay_json_path(self, job_id: str) -> Path:
        return self.outputs_dir / job_id / "tracking_overlay.json"

    def player_selection_json_path(self, job_id: str) -> Path:
        return self.outputs_dir / job_id / "player_selection.json"

    def player_selection_training_samples_json_path(self, job_id: str) -> Path:
        return self.outputs_dir / job_id / "player_selection_training_samples.json"

    def ball_overlay_json_path(self, job_id: str) -> Path:
        return self.outputs_dir / job_id / "ball_overlay.json"

    def detections_jsonl_path(self, job_id: str) -> Path:
        return self.outputs_dir / job_id / "detections.jsonl"

    def ball_trajectory_json_path(self, job_id: str) -> Path:
        return self.outputs_dir / job_id / "ball_trajectory.json"

    def cleaned_ball_trajectory_json_path(self, job_id: str) -> Path:
        return self.outputs_dir / job_id / "cleaned_ball_trajectory.json"

    def bounce_events_json_path(self, job_id: str) -> Path:
        return self.outputs_dir / job_id / "bounce_events.json"

    def analysis_overlay_video_path(self, job_id: str) -> Path:
        return self.outputs_dir / job_id / "analysis_overlay.mp4"

    def position_visualizations_dir(self, job_id: str) -> Path:
        return self.outputs_dir / job_id / "position_visualizations"

    def heatmaps_dir(self, job_id: str) -> Path:
        return self.position_visualizations_dir(job_id) / "heatmaps"

    def scatter_plots_dir(self, job_id: str) -> Path:
        return self.position_visualizations_dir(job_id) / "scatter_plots"

    def heatmaps_manifest_json_path(self, job_id: str) -> Path:
        return self.heatmaps_dir(job_id) / "manifest.json"

    def scatter_plots_manifest_json_path(self, job_id: str) -> Path:
        return self.scatter_plots_dir(job_id) / "manifest.json"

    def pose_overlay_json_path(self, job_id: str) -> Path:
        return self.outputs_dir / job_id / "pose_overlay.json"

    def serve_events_json_path(self, job_id: str) -> Path:
        return self.outputs_dir / job_id / "serve_events.json"

    def serve_debug_candidates_json_path(self, job_id: str) -> Path:
        return self.outputs_dir / job_id / "serve_debug_candidates.json"

    def serve_score_series_json_path(self, job_id: str) -> Path:
        return self.outputs_dir / job_id / "serve_score_series.json"

    def serve_clips_manifest_json_path(self, job_id: str) -> Path:
        return self.outputs_dir / job_id / "serve_clips_manifest.json"

    def serve_debug_overlay_video_path(self, job_id: str) -> Path:
        return self.outputs_dir / job_id / "serve_debug_overlay.mp4"

    def serve_clips_dir(self, job_id: str) -> Path:
        return self.outputs_dir / job_id / "serve_clips"

    def player_trajectory_json_path(self, job_id: str) -> Path:
        return self.outputs_dir / job_id / "players_trajectory.json"

    def player_trajectory_csv_path(self, job_id: str) -> Path:
        return self.outputs_dir / job_id / "players_trajectory.csv"

    def court_view_roi_json_path(self, job_id: str) -> Path:
        return self.outputs_dir / job_id / "court_view_roi.json"

    def video_metadata_path(self, video_id: str) -> Path:
        return self.uploads_dir / f"{video_id}.json"

    def calibration_json_path(self, calibration_id: str) -> Path:
        return self.calibrations_dir / f"{calibration_id}.json"

    def preview_image_path(self, calibration_id: str) -> Path:
        return self.outputs_dir / f"{calibration_id}-preview.png"

    def automatic_calibration_preview_path(self, suggestion_id: str) -> Path:
        return self.outputs_dir / "calibration-previews" / f"{suggestion_id}.png"
