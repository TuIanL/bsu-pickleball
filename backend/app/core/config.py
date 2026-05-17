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
    enable_multitarget_inference: bool = False
    ball_confidence: float = 0.25
    paddle_confidence: float = 0.25
    ball_min_box_area_ratio: float = 0.000001
    ball_max_box_area_ratio: float = 0.02
    ball_max_repair_gap_frames: int = 5
    ball_max_speed_px_per_frame: float = 180.0
    primary_player_min_confidence: float = 0.65
    primary_player_max_subjects: int = 4
    primary_player_min_box_area_ratio: float = 0.0005
    primary_player_max_box_area_ratio: float = 0.85
    primary_player_court_margin_ft: float = 12.0

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
    model_dir = Path(os.getenv("PICKLEBALL_MODEL_DIR", "../models"))
    rtmpose_config_path = (
        os.getenv("PICKLEBALL_RTMPOSE_CONFIG_PATH")
        or os.getenv("RTMPOSE_CONFIG_PATH")
        or _first_existing_path(
            model_dir,
            [
                "rtmpose/configs/body_2d_keypoint/rtmpose/body8/rtmpose-m_8xb512-700e_body8-halpe26-256x192.py",
                "rtmpose/rtmpose-m_8xb512-700e_body8-halpe26-256x192.py",
            ],
        )
    )
    rtmpose_checkpoint_path = (
        os.getenv("PICKLEBALL_RTMPOSE_CHECKPOINT_PATH")
        or os.getenv("RTMPOSE_CHECKPOINT_PATH")
        or _first_existing_path(
            model_dir,
            ["rtmpose/rtmpose-m_simcc-body7_pt-body7-halpe26_700e-256x192-4d3e73dd_20230605.pth"],
        )
    )
    pose_inference_env = os.getenv("PICKLEBALL_ENABLE_POSE_INFERENCE")
    settings = Settings(
        app_name=os.getenv("PICKLEBALL_APP_NAME", Settings.model_fields["app_name"].default),
        uploads_dir=Path(os.getenv("PICKLEBALL_UPLOADS_DIR", "data/uploads")),
        outputs_dir=Path(os.getenv("PICKLEBALL_OUTPUTS_DIR", "data/outputs")),
        calibrations_dir=Path(os.getenv("PICKLEBALL_CALIBRATIONS_DIR", "data/calibrations")),
        tmp_dir=Path(os.getenv("PICKLEBALL_TMP_DIR", "data/tmp")),
        model_dir=model_dir,
        default_detector_model=os.getenv("PICKLEBALL_DEFAULT_DETECTOR_MODEL", "yolo11n.pt"),
        detector_confidence=float(os.getenv("PICKLEBALL_DETECTOR_CONFIDENCE", "0.25")),
        detector_device=os.getenv("PICKLEBALL_DETECTOR_DEVICE") or None,
        enable_model_inference=os.getenv("PICKLEBALL_ENABLE_MODEL_INFERENCE", "true").lower()
        in {"1", "true", "yes"},
        enable_pose_inference=_env_bool(pose_inference_env)
        if pose_inference_env is not None
        else bool(rtmpose_config_path and rtmpose_checkpoint_path),
        rtmpose_config_path=rtmpose_config_path,
        rtmpose_checkpoint_path=rtmpose_checkpoint_path,
        rtmpose_device=os.getenv("PICKLEBALL_RTMPOSE_DEVICE") or os.getenv("RTMPOSE_DEVICE") or None,
        pose_confidence=float(os.getenv("PICKLEBALL_POSE_CONFIDENCE", "0.3")),
        pose_keypoint_schema=os.getenv("PICKLEBALL_POSE_KEYPOINT_SCHEMA", "rtmpose26"),
        overlay_frame_stride=max(1, int(os.getenv("PICKLEBALL_OVERLAY_FRAME_STRIDE", "2"))),
        enable_multitarget_inference=os.getenv("PICKLEBALL_ENABLE_MULTITARGET_INFERENCE", "false").lower()
        in {"1", "true", "yes"},
        ball_confidence=float(os.getenv("PICKLEBALL_BALL_CONFIDENCE", "0.25")),
        paddle_confidence=float(os.getenv("PICKLEBALL_PADDLE_CONFIDENCE", "0.25")),
        ball_min_box_area_ratio=float(os.getenv("PICKLEBALL_BALL_MIN_BOX_AREA_RATIO", "0.000001")),
        ball_max_box_area_ratio=float(os.getenv("PICKLEBALL_BALL_MAX_BOX_AREA_RATIO", "0.02")),
        ball_max_repair_gap_frames=max(0, int(os.getenv("PICKLEBALL_BALL_MAX_REPAIR_GAP_FRAMES", "5"))),
        ball_max_speed_px_per_frame=float(os.getenv("PICKLEBALL_BALL_MAX_SPEED_PX_PER_FRAME", "180")),
        primary_player_min_confidence=float(os.getenv("PICKLEBALL_PRIMARY_PLAYER_MIN_CONFIDENCE", "0.65")),
        primary_player_max_subjects=max(1, int(os.getenv("PICKLEBALL_PRIMARY_PLAYER_MAX_SUBJECTS", "4"))),
        primary_player_min_box_area_ratio=float(os.getenv("PICKLEBALL_PRIMARY_PLAYER_MIN_BOX_AREA_RATIO", "0.0005")),
        primary_player_max_box_area_ratio=float(os.getenv("PICKLEBALL_PRIMARY_PLAYER_MAX_BOX_AREA_RATIO", "0.85")),
        primary_player_court_margin_ft=float(os.getenv("PICKLEBALL_PRIMARY_PLAYER_COURT_MARGIN_FT", "12.0")),
        cors_origins=[origin.strip() for origin in cors_origins.split(",")]
        if cors_origins
        else Settings.model_fields["cors_origins"].default_factory(),
    )
    settings.ensure_data_dirs()
    return settings


def _env_bool(value: str | None) -> bool:
    return (value or "").lower() in {"1", "true", "yes"}


def _first_existing_path(base: Path, relative_paths: list[str]) -> str | None:
    for relative_path in relative_paths:
        candidate = base / relative_path
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        if candidate.exists():
            return str(candidate)
    return None
