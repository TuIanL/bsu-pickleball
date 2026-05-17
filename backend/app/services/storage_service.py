from __future__ import annotations

import json
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

    def read_json(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def output_json_path(self, job_id: str) -> Path:
        return self.outputs_dir / f"{job_id}.json"

    def job_json_path(self, job_id: str) -> Path:
        return self.outputs_dir / "jobs" / f"{job_id}.json"

    def report_json_path(self, job_id: str) -> Path:
        return self.outputs_dir / "reports" / f"{job_id}.json"

    def tracking_json_path(self, job_id: str) -> Path:
        return self.outputs_dir / job_id / "tracking_result.json"

    def tracking_overlay_json_path(self, job_id: str) -> Path:
        return self.outputs_dir / job_id / "tracking_overlay.json"

    def ball_overlay_json_path(self, job_id: str) -> Path:
        return self.outputs_dir / job_id / "ball_overlay.json"

    def pose_overlay_json_path(self, job_id: str) -> Path:
        return self.outputs_dir / job_id / "pose_overlay.json"

    def video_metadata_path(self, video_id: str) -> Path:
        return self.uploads_dir / f"{video_id}.json"

    def calibration_json_path(self, calibration_id: str) -> Path:
        return self.calibrations_dir / f"{calibration_id}.json"

    def preview_image_path(self, calibration_id: str) -> Path:
        return self.outputs_dir / f"{calibration_id}-preview.png"
