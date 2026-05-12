from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path

from pydantic import BaseModel, Field


class Settings(BaseModel):
    app_name: str = "Pre Pickleball Vision API"
    app_version: str = "0.2.0"
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )
    data_dir: Path = Path("data")
    uploads_dir: Path = Path("data/uploads")
    outputs_dir: Path = Path("data/outputs")
    calibrations_dir: Path = Path("data/calibrations")
    tmp_dir: Path = Path("data/tmp")
    model_dir: Path = Path("../models")
    default_detector_model: str = "yolo11n.pt"
    detector_confidence: float = 0.25
    detector_device: str | None = None
    enable_model_inference: bool = True
    enable_pose_inference: bool = False
    rtmpose_config_path: str | None = None
    rtmpose_checkpoint_path: str | None = None
    rtmpose_device: str | None = None
    pose_confidence: float = 0.3
    pose_keypoint_schema: str = "rtmpose26"
    overlay_frame_stride: int = 2

    def resolve_path(self, path: Path) -> Path:
        if path.is_absolute():
            return path
        return Path.cwd() / path

    @property
    def resolved_uploads_dir(self) -> Path:
        return self.resolve_path(self.uploads_dir)

    @property
    def resolved_outputs_dir(self) -> Path:
        return self.resolve_path(self.outputs_dir)

    @property
    def resolved_calibrations_dir(self) -> Path:
        return self.resolve_path(self.calibrations_dir)

    @property
    def resolved_tmp_dir(self) -> Path:
        return self.resolve_path(self.tmp_dir)

    def ensure_data_dirs(self) -> None:
        for path in (
            self.resolved_uploads_dir,
            self.resolved_outputs_dir,
            self.resolved_calibrations_dir,
            self.resolved_tmp_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    cors_origins = os.getenv("PICKLEBALL_CORS_ORIGINS")
    settings = Settings(
        app_name=os.getenv("PICKLEBALL_APP_NAME", Settings.model_fields["app_name"].default),
        uploads_dir=Path(os.getenv("PICKLEBALL_UPLOADS_DIR", "data/uploads")),
        outputs_dir=Path(os.getenv("PICKLEBALL_OUTPUTS_DIR", "data/outputs")),
        calibrations_dir=Path(os.getenv("PICKLEBALL_CALIBRATIONS_DIR", "data/calibrations")),
        tmp_dir=Path(os.getenv("PICKLEBALL_TMP_DIR", "data/tmp")),
        default_detector_model=os.getenv("PICKLEBALL_DEFAULT_DETECTOR_MODEL", "yolo11n.pt"),
        detector_confidence=float(os.getenv("PICKLEBALL_DETECTOR_CONFIDENCE", "0.25")),
        detector_device=os.getenv("PICKLEBALL_DETECTOR_DEVICE") or None,
        enable_model_inference=os.getenv("PICKLEBALL_ENABLE_MODEL_INFERENCE", "true").lower()
        in {"1", "true", "yes"},
        enable_pose_inference=os.getenv("PICKLEBALL_ENABLE_POSE_INFERENCE", "false").lower()
        in {"1", "true", "yes"},
        rtmpose_config_path=os.getenv("PICKLEBALL_RTMPOSE_CONFIG_PATH")
        or os.getenv("RTMPOSE_CONFIG_PATH")
        or None,
        rtmpose_checkpoint_path=os.getenv("PICKLEBALL_RTMPOSE_CHECKPOINT_PATH")
        or os.getenv("RTMPOSE_CHECKPOINT_PATH")
        or None,
        rtmpose_device=os.getenv("PICKLEBALL_RTMPOSE_DEVICE") or os.getenv("RTMPOSE_DEVICE") or None,
        pose_confidence=float(os.getenv("PICKLEBALL_POSE_CONFIDENCE", "0.3")),
        pose_keypoint_schema=os.getenv("PICKLEBALL_POSE_KEYPOINT_SCHEMA", "rtmpose26"),
        overlay_frame_stride=max(1, int(os.getenv("PICKLEBALL_OVERLAY_FRAME_STRIDE", "2"))),
        cors_origins=[origin.strip() for origin in cors_origins.split(",")]
        if cors_origins
        else Settings.model_fields["cors_origins"].default_factory(),
    )
    settings.ensure_data_dirs()
    return settings
