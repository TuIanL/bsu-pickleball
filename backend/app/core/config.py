"""应用配置管理 —— 通过环境变量和默认值管理所有后端运行参数。"""

from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path

from pydantic import BaseModel, Field


class Settings(BaseModel):
    """后端全局配置，所有字段可通过 PICKLEBALL_ 前缀的环境变量覆盖。"""
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
    primary_player_min_confidence: float = 0.65
    primary_player_max_subjects: int = 4
    primary_player_min_box_area_ratio: float = 0.0005
    primary_player_max_box_area_ratio: float = 0.85
    primary_player_court_margin_ft: float = 12.0
    player_identity_max_players: int = 4
    player_identity_lost_buffer_frames: int = 90
    player_identity_inactive_buffer_frames: int = 180
    player_identity_interpolation_buffer_frames: int = 90
    player_identity_match_threshold: float = 0.55
    player_identity_max_reconnect_distance_m: float = 2.5
    player_identity_max_speed_mps: float = 7.0
    player_identity_court_buffer_m: float = 0.75
    player_identity_smoothing_window: int = 5
    court_line_model_path: str | None = None
    court_line_device: str | None = None
    court_line_confidence: float = 0.35
    court_line_geometry_min_area_ratio: float = 0.03
    court_line_frame_ratio: float = 0.1
    enable_job_worker: bool = True
    max_cpu_jobs: int = 1
    max_gpu_jobs: int = 1
    enable_gpu_jobs: bool = False
    job_stage_timeout_seconds: int = 0
    job_max_retries: int = 1
    serve_baseline_margin_ft: float = 6.0
    serve_pre_still_window_seconds: float = 1.5
    serve_pre_still_gap_seconds: float = 0.2
    serve_post_rally_window_seconds: float = 3.0
    serve_min_gap_seconds: float = 6.0
    serve_pose_smooth_window_frames: int = 5
    serve_clip_pre_seconds: float = 2.0
    serve_clip_post_seconds: float = 4.0
    enable_serve_debug_artifacts: bool = True
    enable_serve_debug_clips: bool = False
    enable_serve_debug_overlay: bool = False
    serve_debug_clip_limit: int = 20

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
        primary_player_min_confidence=float(os.getenv("PICKLEBALL_PRIMARY_PLAYER_MIN_CONFIDENCE", "0.65")),
        primary_player_max_subjects=max(1, int(os.getenv("PICKLEBALL_PRIMARY_PLAYER_MAX_SUBJECTS", "4"))),
        primary_player_min_box_area_ratio=float(os.getenv("PICKLEBALL_PRIMARY_PLAYER_MIN_BOX_AREA_RATIO", "0.0005")),
        primary_player_max_box_area_ratio=float(os.getenv("PICKLEBALL_PRIMARY_PLAYER_MAX_BOX_AREA_RATIO", "0.85")),
        primary_player_court_margin_ft=float(os.getenv("PICKLEBALL_PRIMARY_PLAYER_COURT_MARGIN_FT", "12.0")),
        player_identity_max_players=max(1, int(os.getenv("PICKLEBALL_PLAYER_IDENTITY_MAX_PLAYERS", "4"))),
        player_identity_lost_buffer_frames=max(
            1,
            int(os.getenv("PICKLEBALL_PLAYER_IDENTITY_LOST_BUFFER_FRAMES", "90")),
        ),
        player_identity_inactive_buffer_frames=max(
            1,
            int(os.getenv("PICKLEBALL_PLAYER_IDENTITY_INACTIVE_BUFFER_FRAMES", "180")),
        ),
        player_identity_interpolation_buffer_frames=max(
            1,
            int(os.getenv("PICKLEBALL_PLAYER_IDENTITY_INTERPOLATION_BUFFER_FRAMES", "90")),
        ),
        player_identity_match_threshold=_clamp_float(
            os.getenv("PICKLEBALL_PLAYER_IDENTITY_MATCH_THRESHOLD", "0.55"),
            0.0,
            1.0,
        ),
        player_identity_max_reconnect_distance_m=float(
            os.getenv("PICKLEBALL_PLAYER_IDENTITY_MAX_RECONNECT_DISTANCE_M", "2.5")
        ),
        player_identity_max_speed_mps=float(os.getenv("PICKLEBALL_PLAYER_IDENTITY_MAX_SPEED_MPS", "7.0")),
        player_identity_court_buffer_m=float(os.getenv("PICKLEBALL_PLAYER_IDENTITY_COURT_BUFFER_M", "0.75")),
        player_identity_smoothing_window=max(1, int(os.getenv("PICKLEBALL_PLAYER_IDENTITY_SMOOTHING_WINDOW", "5"))),
        court_line_model_path=os.getenv("PICKLEBALL_COURT_LINE_MODEL_PATH")
        or _first_existing_path(model_dir, ["court-line/best.pt", "court-line/court-line-seg.pt"]),
        court_line_device=os.getenv("PICKLEBALL_COURT_LINE_DEVICE") or None,
        court_line_confidence=float(os.getenv("PICKLEBALL_COURT_LINE_CONFIDENCE", "0.35")),
        court_line_geometry_min_area_ratio=float(os.getenv("PICKLEBALL_COURT_LINE_GEOMETRY_MIN_AREA_RATIO", "0.03")),
        court_line_frame_ratio=_clamp_float(os.getenv("PICKLEBALL_COURT_LINE_FRAME_RATIO", "0.1"), 0.0, 0.95),
        enable_job_worker=os.getenv("PICKLEBALL_ENABLE_JOB_WORKER", "true").lower() in {"1", "true", "yes"},
        max_cpu_jobs=max(1, int(os.getenv("PICKLEBALL_MAX_CPU_JOBS", "1"))),
        max_gpu_jobs=max(1, int(os.getenv("PICKLEBALL_MAX_GPU_JOBS", "1"))),
        enable_gpu_jobs=os.getenv("PICKLEBALL_ENABLE_GPU_JOBS", "false").lower() in {"1", "true", "yes"},
        job_stage_timeout_seconds=max(0, int(os.getenv("PICKLEBALL_JOB_STAGE_TIMEOUT_SECONDS", "0"))),
        job_max_retries=max(0, int(os.getenv("PICKLEBALL_JOB_MAX_RETRIES", "1"))),
        serve_baseline_margin_ft=float(os.getenv("PICKLEBALL_SERVE_BASELINE_MARGIN_FT", "6.0")),
        serve_pre_still_window_seconds=float(os.getenv("PICKLEBALL_SERVE_PRE_STILL_WINDOW_SECONDS", "1.5")),
        serve_pre_still_gap_seconds=float(os.getenv("PICKLEBALL_SERVE_PRE_STILL_GAP_SECONDS", "0.2")),
        serve_post_rally_window_seconds=float(os.getenv("PICKLEBALL_SERVE_POST_RALLY_WINDOW_SECONDS", "3.0")),
        serve_min_gap_seconds=float(os.getenv("PICKLEBALL_SERVE_MIN_GAP_SECONDS", "6.0")),
        serve_pose_smooth_window_frames=max(1, int(os.getenv("PICKLEBALL_SERVE_POSE_SMOOTH_WINDOW_FRAMES", "5"))),
        serve_clip_pre_seconds=float(os.getenv("PICKLEBALL_SERVE_CLIP_PRE_SECONDS", "2.0")),
        serve_clip_post_seconds=float(os.getenv("PICKLEBALL_SERVE_CLIP_POST_SECONDS", "4.0")),
        enable_serve_debug_artifacts=os.getenv("PICKLEBALL_ENABLE_SERVE_DEBUG_ARTIFACTS", "true").lower()
        in {"1", "true", "yes"},
        enable_serve_debug_clips=os.getenv("PICKLEBALL_ENABLE_SERVE_DEBUG_CLIPS", "false").lower()
        in {"1", "true", "yes"},
        enable_serve_debug_overlay=os.getenv("PICKLEBALL_ENABLE_SERVE_DEBUG_OVERLAY", "false").lower()
        in {"1", "true", "yes"},
        serve_debug_clip_limit=max(0, int(os.getenv("PICKLEBALL_SERVE_DEBUG_CLIP_LIMIT", "20"))),
        cors_origins=[origin.strip() for origin in cors_origins.split(",")]
        if cors_origins
        else Settings.model_fields["cors_origins"].default_factory(),
    )
    settings.ensure_data_dirs()
    return settings


def _env_bool(value: str | None) -> bool:
    return (value or "").lower() in {"1", "true", "yes"}


def _clamp_float(value: str, minimum: float, maximum: float) -> float:
    return min(max(float(value), minimum), maximum)


def _first_existing_path(base: Path, relative_paths: list[str]) -> str | None:
    for relative_path in relative_paths:
        candidate = base / relative_path
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        if candidate.exists():
            return str(candidate)
    return None
