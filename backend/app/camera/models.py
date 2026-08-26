"""
摄像头接入与录制控制的 Pydantic 数据模型。

Pydantic 是 Python 里用来"定义数据长什么样"的库：
- 它会在接口收到请求时自动校验字段类型和必填项；
- 也能把对象方便地转成 / 转自 JSON。
这里的模型被 camera 模块和对应的 API 路由（routes_camera / routes_recording）共同使用。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


# 摄像头信息：登记后在系统里保存的一条摄像头记录
class CameraInfo(BaseModel):
    camera_id: str  # 摄像头唯一 ID（用于后续查询 / 录制）
    name: str  # 显示名称（给人看的）
    stream_url: str  # 视频流地址，如 rtsp://... 或 http://...
    protocol: Literal["rtsp", "rtmp", "http"]  # 流协议，只能是这三种之一
    username: str | None = None  # 登录用户名（可选）
    password: str | None = None  # 登录密码（可选，属敏感信息）
    created_at: datetime  # 创建时间（UTC）


# 创建摄像头的请求：前端提交"新增摄像头"时携带的数据
class CameraCreateRequest(BaseModel):
    camera_id: str
    name: str
    stream_url: str
    protocol: Literal["rtsp", "rtmp", "http"] = "rtsp"  # 默认协议为 rtsp
    username: str | None = None
    password: str | None = None


class CameraUpdateRequest(BaseModel):
    camera_id: str
    name: str


# 删除摄像头的响应：只返回是否删除成功
class CameraDeleteResponse(BaseModel):
    deleted: bool


# 探测结果：调用 /probe 接口后返回摄像头是否在线、分辨率、延迟等
class ProbeResult(BaseModel):
    camera_id: str
    online: bool  # 是否在线（能连上并读到画面）
    latency_ms: int | None = None  # 连上并读到第一帧的延迟（毫秒）
    resolution: str | None = None  # 分辨率，如 "1920x1080"
    detected_at: datetime  # 探测发生的时间（UTC）
    error_message: str | None = None  # 若不在线，记录失败原因


# 录制会话的状态：只能是下面四种之一
RecordingSessionStatus = Literal["recording", "completed", "failed", "canceled"]


# 开始录制的请求：前端点击"开始录制"时携带的参数
class RecordingStartRequest(BaseModel):
    camera_id: str  # 要录制的摄像头 id
    field_session_id: str | None = None  # 关联的 Field Session id（可选）
    court_name: str = ""  # 球场名称（备注用）；可从 Field Session 继承
    match_format: Literal["singles", "doubles"] | None = (
        None  # 单打/双打；None 时从 Field Session 继承，否则默认 doubles
    )
    camera_angle: str = "baseline_high"  # 机位角度标识
    fps: int = Field(default=60, ge=1, le=60)  # 帧率，限制 1~60
    resolution: str = "1920x1080"  # 录制分辨率
    auto_analyze_after_stop: bool = True  # 停止后是否自动创建分析任务
    storage_root: str | None = None  # 本次录制临时使用的本地存储根目录


# 录制会话：一次录制的完整记录（会持久化到磁盘）
class RecordingSession(BaseModel):
    session_id: str  # 会话唯一 ID
    camera_id: str  # 对应的摄像头 id
    field_session_id: str | None = None  # 关联的 Field Session id（可选）
    court_name: str
    match_format: str
    camera_angle: str
    fps: int
    resolution: str
    auto_analyze_after_stop: bool
    status: RecordingSessionStatus  # 当前状态（recording / completed / failed / canceled）
    started_at: datetime
    stopped_at: datetime | None = None  # 停止时间（未停止则为空）
    duration_sec: float | None = None  # 录制时长（秒）
    video_path: str | None = None  # 生成的视频文件位置
    video_id: str | None = None  # 注册到视频系统后的 id
    auto_analysis_job_id: str | None = None  # 自动创建的分析任务 id
    error_message: str | None = None  # 失败时的错误信息
    capture_take_id: str | None = None  # 关联的 CaptureTake ID
    storage_root: str | None = None
    session_dir: str | None = None
    storage_status: str = "available"
    display_mode: Literal["standard", "showcase"] = "standard"
    display_title: str | None = None  # 用户自定义显示标题（Library 卡片优先采用；缺省回退派生标题）
    display_date: datetime | None = None  # 用户自定义比赛日期（Library 卡片优先采用；缺省回退 started_at）


# 删除录制会话的结果
RecordingDeleteStatus = Literal["deleted", "blocked", "not_found"]


class RecordingDeleteResult(BaseModel):
    session_id: str
    status: RecordingDeleteStatus
    detail: str = ""


# ═══════════════════════════════════════════════════════════════════════════
# 双摄同步录制模型（add-dual-camera-sync-recording）
# ═══════════════════════════════════════════════════════════════════════════

# 机位标识（两个摄像头的槽位 key，平等命名）
CameraSlotRole = Literal["cam_1", "cam_2"]

# 双摄录制会话状态
SyncRecordingStatus = Literal["recording", "completed", "failed", "canceled"]
SyncMergeStatus = Literal["pending", "running", "completed", "failed"]

# 分段状态
SyncSegmentStatus = Literal["recording", "completed", "failed"]


class CameraSlotConfig(BaseModel):
    """一个机位槽位的配置（摄像头 + 机位角度）"""

    role: CameraSlotRole
    camera_id: str
    camera_angle: str = ""  # baseline_high / sideline 等
    stream_url_snapshot: str = ""  # 开始录制时的流地址快照


class SyncStartRequest(BaseModel):
    """开始双摄同步录制请求"""

    cam_1_id: str = ""
    cam_2_id: str = ""
    field_session_id: str | None = None
    court_name: str = ""
    match_format: Literal["singles", "doubles"] | None = None
    cam_1_angle: str = "baseline_high"
    cam_2_angle: str = "baseline_high"
    fps: int = Field(default=60, ge=1, le=60)
    resolution: str = "1920x1080"
    auto_analyze_after_stop: bool = True
    storage_root: str | None = None

    # 临时兼容旧字段：允许前端使用 primary_camera_id / secondary_camera_id
    @model_validator(mode="before")
    @classmethod
    def _compat_old_fields(cls, data: any) -> any:
        if isinstance(data, dict):
            if data.get("primary_camera_id") and not data.get("cam_1_id"):
                data["cam_1_id"] = data["primary_camera_id"]
            if data.get("secondary_camera_id") and not data.get("cam_2_id"):
                data["cam_2_id"] = data["secondary_camera_id"]
            if data.get("primary_angle") and not data.get("cam_1_angle"):
                data["cam_1_angle"] = data["primary_angle"]
            if data.get("secondary_angle") and not data.get("cam_2_angle"):
                data["cam_2_angle"] = data["secondary_angle"]
        return data


class SyncSegmentFile(BaseModel):
    """一个分段中的单路文件信息"""

    camera_id: str
    role: CameraSlotRole
    file_path: str
    file_size: int = 0
    packet_count: int = 0
    media_duration_sec: float = 0.0
    effective_fps: float = 0.0
    ffmpeg_log_path: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    error_message: str | None = None
    input_start_time: float | None = None  # FFmpeg 读取 RTSP 输入时的共同时间基起点
    media_start_time_sec: float | None = None  # 输出文件首帧在媒体时间轴中的时间


class SyncSegment(BaseModel):
    """一个同步分段（两路同时录制的一个片段）"""

    segment_index: int
    status: SyncSegmentStatus = "recording"
    files: list[SyncSegmentFile] = []
    started_at: datetime | None = None
    ended_at: datetime | None = None
    restart_count: int = 0  # 该分段的同步重启次数
    error_message: str | None = None


class SyncTestResult(BaseModel):
    """双摄短录测试结果"""

    success: bool
    cam_1_id: str
    cam_2_id: str
    duration_sec: float
    cam_1_online: bool = False
    cam_2_online: bool = False
    cam_1_first_frame_url: str | None = None
    cam_2_first_frame_url: str | None = None
    cam_1_first_frame_exists: bool = False
    cam_2_first_frame_exists: bool = False
    cam_1_file_size: int = 0
    cam_2_file_size: int = 0
    cam_1_error: str | None = None
    cam_2_error: str | None = None
    test_completed_at: datetime | None = None


class SyncRecordingSession(BaseModel):
    """双摄同步录制会话"""

    session_id: str
    field_session_id: str | None = None
    status: SyncRecordingStatus = "recording"
    camera_slots: dict[str, CameraSlotConfig] = {}  # "cam_1" / "cam_2"
    segments: list[SyncSegment] = []
    output_dir: str = ""
    default_analysis_video_id: str | None = None
    registered_video_ids: dict[CameraSlotRole, str] = {}
    # 运行时可用性不是视频引用本身；外置存储暂时不可访问时保留 ID，
    # 仅更新这里的状态，待存储恢复后再自动重新检查。
    video_availability: dict[CameraSlotRole, Literal["available", "unavailable", "pending"]] = Field(
        default_factory=dict
    )
    associated_video_paths: list[str] = []
    court_name: str = ""
    match_format: str = "doubles"
    fps: int = 30
    resolution: str = "1920x1080"
    auto_analyze_after_stop: bool = True
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    duration_sec: float | None = None
    error_message: str | None = None
    total_restarts: int = 0
    capture_take_id: str | None = None
    storage_root: str | None = None
    session_dir: str | None = None
    storage_status: str = "available"
    display_mode: Literal["standard", "showcase"] = "standard"
    showcase_runtime_id: str | None = None
    merge_status: SyncMergeStatus = "pending"
    merge_error: str | None = None
    merge_started_at: datetime | None = None
    merge_completed_at: datetime | None = None
    merge_results: dict[str, dict[str, object]] = Field(default_factory=dict)
    display_title: str | None = None  # 用户自定义显示标题（Library 卡片优先采用；缺省回退派生标题）
    display_date: datetime | None = None  # 用户自定义比赛日期（Library 卡片优先采用；缺省回退 started_at）

    @model_validator(mode="before")
    @classmethod
    def _compat_merge_status(cls, data: object) -> object:
        if isinstance(data, dict) and "merge_status" not in data:
            registered = data.get("registered_video_ids") or {}
            slots = data.get("camera_slots") or {}
            data = dict(data)
            data["merge_status"] = "completed" if slots and len(registered) >= len(slots) else "pending"
        return data


class SyncTestRequest(BaseModel):
    """双摄短录测试请求"""

    cam_1_id: str = ""
    cam_2_id: str = ""
    duration: int = Field(default=5, ge=3, le=30)  # 测试时长 3~30 秒

    # 临时兼容旧字段
    @model_validator(mode="before")
    @classmethod
    def _compat_old_fields(cls, data: any) -> any:
        if isinstance(data, dict):
            if data.get("primary_camera_id") and not data.get("cam_1_id"):
                data["cam_1_id"] = data["primary_camera_id"]
            if data.get("secondary_camera_id") and not data.get("cam_2_id"):
                data["cam_2_id"] = data["secondary_camera_id"]
        return data


class SyncStopResponse(BaseModel):
    """停止双摄同步录制响应"""

    session: SyncRecordingSession
    default_analysis_video_id: str | None = None
    analysis_available: bool = False
    analysis_blocked_reason: str | None = None


# 录制/双摄素材的用户自定义显示元数据（Library 卡片内联编辑的兜底真源）。
# 空值表示撤销覆盖（回退到派生标题 / started_at）。
class SessionDisplayUpdateRequest(BaseModel):
    display_title: str | None = None
    display_date: datetime | None = None
