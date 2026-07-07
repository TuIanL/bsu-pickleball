"""
应用配置管理 —— 通过环境变量和默认值管理所有后端运行参数。

本文件是整个后端的"总开关"：所有可调参数（目录位置、模型路径、各种阈值、
开关……）都集中定义在这里。启动时既可以用代码里的默认值，
也可以通过 PICKLEBALL_ 前缀的环境变量来覆盖（方便在不同机器/环境下部署）。
"""

from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path

from pydantic import BaseModel, Field


class Settings(BaseModel):
    """后端全局配置（Pydantic 模型）。

    所有字段都可以在启动时通过 PICKLEBALL_ 前缀的环境变量来覆盖，
    例如 app_name 默认是 "Pre Pickleball Vision API"，
    可用环境变量 PICKLEBALL_APP_NAME 改成别的。
    没有设置环境变量时就使用下面写的默认值。
    """

    # ---- 应用基本信息 ----
    app_name: str = "Pre Pickleball Vision API"          # 应用名称
    app_version: str = "0.2.0"                           # 应用版本号
    cors_origins: list[str] = Field(                     # 允许跨域访问的前端来源（CORS 白名单）
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    # ---- 数据与模型存放目录 ----
    data_dir: Path = Path("data")                        # 总数据目录
    database_path: Path = Path("data/app.sqlite3")       # 本地 SQLite 数据库文件
    uploads_dir: Path = Path("data/uploads")             # 上传视频存放目录
    outputs_dir: Path = Path("data/outputs")             # 分析结果输出目录
    calibrations_dir: Path = Path("data/calibrations")   # 标定文件目录
    recordings_dir: Path = Path("data/recordings")       # 录制视频目录
    cameras_dir: Path = Path("data/cameras")             # 摄像头配置目录
    tmp_dir: Path = Path("data/tmp")                     # 临时文件目录
    model_dir: Path = Path("../models")                  # 模型权重所在目录（相对项目根）

    # ---- 人体检测模型 ----
    default_detector_model: str = "yolo11n.pt"           # 默认人体检测模型文件名
    detector_confidence: float = 0.25                    # 检测置信度阈值（低于此值不认为是人）
    detector_device: str | None = None                   # 推理设备（None=自动/CPU；或 "cuda:0" 等 GPU）

    # ---- 姿态（Pose）推理 ----
    enable_model_inference: bool = True                  # 是否启用模型推理（总开关）
    enable_pose_inference: bool = False                  # 是否启用姿态（关键点）推理
    rtmpose_config_path: str | None = None               # RTMPose 配置文件路径
    rtmpose_checkpoint_path: str | None = None           # RTMPose 权重文件路径
    rtmpose_device: str | None = None                    # RTMPose 推理设备
    pose_confidence: float = 0.3                         # 姿态关键点置信度阈值
    pose_keypoint_schema: str = "rtmpose26"              # 姿态关键点方案名（26 点）

    # ---- 视频 / overlay 渲染 ----
    overlay_frame_stride: int = 2                        # overlay 抽帧步长（每隔几帧画一次叠加）

    # ---- 主球员筛选（从多人中确定"关注对象"）----
    primary_player_min_confidence: float = 0.65          # 主球员最低置信度
    primary_player_max_subjects: int = 4                  # 最多同时关注几个目标
    primary_player_min_box_area_ratio: float = 0.0005    # 检测框最小面积占比（过滤太小框）
    primary_player_max_box_area_ratio: float = 0.85      # 检测框最大面积占比（过滤太大框）
    primary_player_court_margin_ft: float = 12.0         # 球场外扩边距（英尺）
    primary_player_window_frames: int = 90               # 判定主球员的滑动窗口帧数
    primary_player_target_court_threshold: float = 0.45  # 主球员在目标球场的比例阈值
    primary_player_quality_threshold: float = 0.28       # 主球员质量阈值

    # ---- 注意力式主球员选择器（可选，默认关闭）----
    enable_attention_player_selector: bool = False        # 是否用注意力模型选主球员
    attention_player_selector_model_path: str | None = None  # 注意力选择器模型路径
    attention_player_selector_confidence: float = 0.65     # 注意力选择器置信度阈值

    # ---- 球检测 / 弹跳检测（默认开启，缺少模型时自动降级为 unavailable）----
    ball_model_path: str | None = None                    # 球检测模型路径
    enable_ball_detection: bool = True                    # 是否启用球检测
    enable_bounce_detection: bool = True                  # 是否启用弹跳检测
    ball_analysis_strict: bool = False                    # 球分析严格模式：true 时球分析异常导致 pipeline failed

    # ---- 可视化输出 ----
    enable_analysis_overlay_video: bool = True            # 是否生成分析叠加视频
    enable_position_visualizations: bool = True           # 是否生成位置可视化图
    visualization_language: str = "zh-CN"                 # 可视化文字语言

    # ---- 球员身份跟踪（跨帧保持同一人身份）----
    player_identity_max_players: int = 4                   # 最多追踪人数
    player_identity_lost_buffer_frames: int = 90          # 跟丢后保留缓存帧数
    player_identity_inactive_buffer_frames: int = 180     # 不活跃时保留缓存帧数
    player_identity_interpolation_buffer_frames: int = 90 # 插值补齐缓存帧数
    player_identity_match_threshold: float = 0.55         # 身份匹配阈值
    player_identity_max_reconnect_distance_m: float = 2.5 # 重连最大距离（米）
    player_identity_max_speed_mps: float = 7.0            # 最大速度（米/秒，过滤异常跳变）
    player_identity_court_buffer_m: float = 0.75          # 球场缓冲距离（米）
    player_identity_smoothing_window: int = 5             # 平滑窗口帧数

    # ---- 场地线检测（用于自动标定）----
    court_line_model_path: str | None = None              # 场地线分割模型路径
    court_line_device: str | None = None                  # 场地线模型推理设备
    court_line_confidence: float = 0.35                    # 场地线置信度阈值
    court_line_geometry_min_area_ratio: float = 0.03       # 场地线最小面积占比
    court_line_frame_ratio: float = 0.1                    # 场地线检测抽帧比例

    # ---- 任务队列 / Worker ----
    enable_job_worker: bool = True                         # 是否启用后台任务 Worker
    max_cpu_jobs: int = 1                                  # 最大并行 CPU 任务数
    max_gpu_jobs: int = 1                                  # 最大并行 GPU 任务数
    enable_gpu_jobs: bool = False                          # 是否启用 GPU 任务
    job_stage_timeout_seconds: int = 0                     # 单个阶段超时秒数（0=不限制）
    job_max_retries: int = 1                               # 任务失败最大重试次数

    # ---- 发球（serve）检测相关 ----
    serve_baseline_margin_ft: float = 6.0                  # 发球基线边距（英尺）
    serve_pre_still_window_seconds: float = 1.5           # 发球前静止窗口（秒）
    serve_pre_still_gap_seconds: float = 0.2              # 发球前静止间隔（秒）
    serve_post_rally_window_seconds: float = 3.0          # 发球后回合窗口（秒）
    serve_min_gap_seconds: float = 6.0                    # 发球之间最小间隔（秒）
    serve_pose_smooth_window_frames: int = 5              # 发球姿态平滑窗口帧数
    serve_clip_pre_seconds: float = 2.0                   # 发球片段前置秒数
    serve_clip_post_seconds: float = 4.0                  # 发球片段后置秒数
    enable_serve_debug_artifacts: bool = True             # 是否生成发球调试产物
    enable_serve_debug_clips: bool = False                # 是否生成发球调试片段
    enable_serve_debug_overlay: bool = False              # 是否生成发球调试叠加视频
    serve_debug_clip_limit: int = 20                      # 发球调试片段数量上限

    # ---- 场地视角（court view）门控 ----
    enable_court_view_gate: bool = True                   # 是否启用场地视角门控
    court_view_match_threshold: float = 0.75              # 场地视角匹配阈值
    court_view_start_frames: int = 5                      # 场地视角起始帧数
    court_view_end_frames: int = 5                        # 场地视角结束帧数
    court_view_match_width: int = 320                     # 场地视角匹配宽度（像素）
    court_view_diagnostic_only: bool = False              # 仅诊断模式（不输出正式结果）
    court_view_skip_non_court_frames: bool = True         # 跳过非球场帧

    # ---- 检测 ROI 过滤 ----
    enable_detection_roi_filter: bool = True              # 是否启用检测 ROI 过滤（只检测球场附近）
    detection_roi_padding_ratio: float = 0.15             # ROI 外扩比例
    detection_roi_min_padding_px: int = 24                # ROI 最小外扩像素

    def resolve_path(self, path: Path) -> Path:
        # 把相对路径解析成基于"当前工作目录"的绝对路径；绝对路径原样返回
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
    def resolved_recordings_dir(self) -> Path:
        return self.resolve_path(self.recordings_dir)

    @property
    def resolved_cameras_dir(self) -> Path:
        return self.resolve_path(self.cameras_dir)

    @property
    def resolved_tmp_dir(self) -> Path:
        return self.resolve_path(self.tmp_dir)

    def ensure_data_dirs(self) -> None:
        # 确保各个数据目录都存在（不存在就创建，已存在也不报错）
        for path in (
            self.resolved_uploads_dir,
            self.resolved_outputs_dir,
            self.resolved_calibrations_dir,
            self.resolved_tmp_dir,
            self.resolved_recordings_dir,
            self.resolved_cameras_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    # 从环境变量读取配置。约定：所有变量以 PICKLEBALL_ 开头，
    # 找不到环境变量时就用 Settings 类里写的默认值。
    # @lru_cache 让本函数只在第一次被调用时真正执行，之后直接返回缓存（配置只加载一次）。
    cors_origins = os.getenv("PICKLEBALL_CORS_ORIGINS")
    model_dir = Path(os.getenv("PICKLEBALL_MODEL_DIR", "../models"))

    # RTMPose 配置/权重路径：优先用环境变量，否则在模型目录里按已知文件名顺序找一个存在的
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
    ball_model_path = os.getenv("PICKLEBALL_BALL_MODEL_PATH") or _first_existing_path(
        model_dir,
        [
            "ball/tennis-ball.pt",
            "ball/pickleball-ball.pt",
            "ball/best.pt",
            "pickleball-multitarget/model.pt",
        ],
    )

    # 构造最终配置对象：逐项从环境变量读取，未设置则用默认值。
    # 注意下面大量使用 _env_bool(...) / _clamp_float(...) / max(...) 等，
    # 目的是把环境变量的"字符串"安全地转成对应的类型并限定取值范围。
    settings = Settings(
        app_name=os.getenv("PICKLEBALL_APP_NAME", Settings.model_fields["app_name"].default),
        data_dir=Path(os.getenv("PICKLEBALL_DATA_DIR", "data")),
        database_path=Path(os.getenv("PICKLEBALL_DATABASE_PATH", "data/app.sqlite3")),
        uploads_dir=Path(os.getenv("PICKLEBALL_UPLOADS_DIR", "data/uploads")),
        outputs_dir=Path(os.getenv("PICKLEBALL_OUTPUTS_DIR", "data/outputs")),
        calibrations_dir=Path(os.getenv("PICKLEBALL_CALIBRATIONS_DIR", "data/calibrations")),
        recordings_dir=Path(os.getenv("PICKLEBALL_RECORDINGS_DIR", "data/recordings")),
        cameras_dir=Path(os.getenv("PICKLEBALL_CAMERAS_DIR", "data/cameras")),
        tmp_dir=Path(os.getenv("PICKLEBALL_TMP_DIR", "data/tmp")),
        model_dir=model_dir,
        default_detector_model=os.getenv("PICKLEBALL_DEFAULT_DETECTOR_MODEL", "yolo11n.pt"),
        detector_confidence=float(os.getenv("PICKLEBALL_DETECTOR_CONFIDENCE", "0.25")),
        detector_device=os.getenv("PICKLEBALL_DETECTOR_DEVICE") or None,
        enable_model_inference=os.getenv("PICKLEBALL_ENABLE_MODEL_INFERENCE", "true").lower()
        in {"1", "true", "yes"},
        # 姿态推理开关：显式设了环境变量就用它；否则根据配置文件/权重是否齐全自动判断
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
        primary_player_window_frames=max(1, int(os.getenv("PICKLEBALL_PRIMARY_PLAYER_WINDOW_FRAMES", "90"))),
        primary_player_target_court_threshold=_clamp_float(
            os.getenv("PICKLEBALL_PRIMARY_PLAYER_TARGET_COURT_THRESHOLD", "0.45"),
            0.0,
            1.0,
        ),
        primary_player_quality_threshold=_clamp_float(
            os.getenv("PICKLEBALL_PRIMARY_PLAYER_QUALITY_THRESHOLD", "0.28"),
            0.0,
            1.0,
        ),
        enable_attention_player_selector=os.getenv("PICKLEBALL_ENABLE_ATTENTION_PLAYER_SELECTOR", "false").lower()
        in {"1", "true", "yes"},
        attention_player_selector_model_path=os.getenv("PICKLEBALL_ATTENTION_PLAYER_SELECTOR_MODEL_PATH") or None,
        attention_player_selector_confidence=_clamp_float(
            os.getenv("PICKLEBALL_ATTENTION_PLAYER_SELECTOR_CONFIDENCE", "0.65"),
            0.0,
            1.0,
        ),
        ball_model_path=ball_model_path,
        enable_ball_detection=os.getenv("PICKLEBALL_ENABLE_BALL_DETECTION", "true").lower()
        in {"1", "true", "yes"},
        enable_bounce_detection=os.getenv("PICKLEBALL_ENABLE_BOUNCE_DETECTION", "true").lower()
        in {"1", "true", "yes"},
        ball_analysis_strict=os.getenv("PICKLEBALL_BALL_ANALYSIS_STRICT", "false").lower()
        in {"1", "true", "yes"},
        enable_analysis_overlay_video=os.getenv("PICKLEBALL_ENABLE_ANALYSIS_OVERLAY_VIDEO", "true").lower()
        in {"1", "true", "yes"},
        enable_position_visualizations=os.getenv("PICKLEBALL_ENABLE_POSITION_VISUALIZATIONS", "true").lower()
        in {"1", "true", "yes"},
        visualization_language=os.getenv("PICKLEBALL_VISUALIZATION_LANGUAGE", "zh-CN"),
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
        enable_court_view_gate=os.getenv("PICKLEBALL_ENABLE_COURT_VIEW_GATE", "true").lower()
        in {"1", "true", "yes"},
        court_view_match_threshold=_clamp_float(
            os.getenv("PICKLEBALL_COURT_VIEW_MATCH_THRESHOLD", "0.75"),
            0.0,
            1.0,
        ),
        court_view_start_frames=max(1, int(os.getenv("PICKLEBALL_COURT_VIEW_START_FRAMES", "5"))),
        court_view_end_frames=max(1, int(os.getenv("PICKLEBALL_COURT_VIEW_END_FRAMES", "5"))),
        court_view_match_width=max(1, int(os.getenv("PICKLEBALL_COURT_VIEW_MATCH_WIDTH", "320"))),
        court_view_diagnostic_only=os.getenv("PICKLEBALL_COURT_VIEW_DIAGNOSTIC_ONLY", "false").lower()
        in {"1", "true", "yes"},
        court_view_skip_non_court_frames=os.getenv("PICKLEBALL_COURT_VIEW_SKIP_NON_COURT_FRAMES", "true").lower()
        in {"1", "true", "yes"},
        enable_detection_roi_filter=os.getenv("PICKLEBALL_ENABLE_DETECTION_ROI_FILTER", "true").lower()
        in {"1", "true", "yes"},
        detection_roi_padding_ratio=max(0.0, float(os.getenv("PICKLEBALL_DETECTION_ROI_PADDING_RATIO", "0.15"))),
        detection_roi_min_padding_px=max(0, int(os.getenv("PICKLEBALL_DETECTION_ROI_MIN_PADDING_PX", "24"))),
        # CORS 来源：把环境变量里逗号分隔的字符串拆成列表；未设置则用默认值
        cors_origins=[origin.strip() for origin in cors_origins.split(",")]
        if cors_origins
        else Settings.model_fields["cors_origins"].default_factory(),
    )
    # 构造完成后，确保各数据目录都已存在
    settings.ensure_data_dirs()
    return settings


# 把字符串环境变量解析成布尔值（"1"/"true"/"yes" 视为真，其余为假）
def _env_bool(value: str | None) -> bool:
    return (value or "").lower() in {"1", "true", "yes"}


# 把字符串转成浮点数，并限制在 [minimum, maximum] 区间内（防止配置越界）
def _clamp_float(value: str, minimum: float, maximum: float) -> float:
    return min(max(float(value), minimum), maximum)


# 在 base 目录下按 relative_paths 顺序找第一个真实存在的文件，返回其绝对路径字符串；都找不到返回 None
def _first_existing_path(base: Path, relative_paths: list[str]) -> str | None:
    for relative_path in relative_paths:
        candidate = base / relative_path
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        if candidate.exists():
            return str(candidate)
    return None
