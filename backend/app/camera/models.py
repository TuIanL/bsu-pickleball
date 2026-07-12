"""
摄像头接入与录制控制的 Pydantic 数据模型。

Pydantic 是 Python 里用来"定义数据长什么样"的库：
- 它会在接口收到请求时自动校验字段类型和必填项；
- 也能把对象方便地转成 / 转自 JSON。
这里的模型被 camera 模块和对应的 API 路由（routes_camera / routes_recording）共同使用。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


# 摄像头信息：登记后在系统里保存的一条摄像头记录
class CameraInfo(BaseModel):
    camera_id: str          # 摄像头唯一 ID（用于后续查询 / 录制）
    name: str               # 显示名称（给人看的）
    stream_url: str         # 视频流地址，如 rtsp://... 或 http://...
    protocol: Literal["rtsp", "rtmp", "http"]  # 流协议，只能是这三种之一
    username: Optional[str] = None   # 登录用户名（可选）
    password: Optional[str] = None   # 登录密码（可选，属敏感信息）
    created_at: datetime    # 创建时间（UTC）


# 创建摄像头的请求：前端提交"新增摄像头"时携带的数据
class CameraCreateRequest(BaseModel):
    camera_id: str
    name: str
    stream_url: str
    protocol: Literal["rtsp", "rtmp", "http"] = "rtsp"  # 默认协议为 rtsp
    username: Optional[str] = None
    password: Optional[str] = None


class CameraUpdateRequest(BaseModel):
    camera_id: str
    name: str


# 删除摄像头的响应：只返回是否删除成功
class CameraDeleteResponse(BaseModel):
    deleted: bool


# 探测结果：调用 /probe 接口后返回摄像头是否在线、分辨率、延迟等
class ProbeResult(BaseModel):
    camera_id: str
    online: bool                      # 是否在线（能连上并读到画面）
    latency_ms: Optional[int] = None  # 连上并读到第一帧的延迟（毫秒）
    resolution: Optional[str] = None  # 分辨率，如 "1920x1080"
    detected_at: datetime             # 探测发生的时间（UTC）
    error_message: Optional[str] = None  # 若不在线，记录失败原因


# 录制会话的状态：只能是下面四种之一
RecordingSessionStatus = Literal["recording", "completed", "failed", "canceled"]


# 开始录制的请求：前端点击"开始录制"时携带的参数
class RecordingStartRequest(BaseModel):
    camera_id: str                          # 要录制的摄像头 id
    field_session_id: Optional[str] = None  # 关联的 Field Session id（可选）
    court_name: str = ""                    # 球场名称（备注用）；可从 Field Session 继承
    match_format: Optional[Literal["singles", "doubles"]] = None  # 单打/双打；None 时从 Field Session 继承，否则默认 doubles
    camera_angle: str = "baseline_high"     # 机位角度标识
    fps: int = Field(default=60, ge=1, le=60)  # 帧率，限制 1~60
    resolution: str = "1920x1080"           # 录制分辨率
    auto_analyze_after_stop: bool = True    # 停止后是否自动创建分析任务


# 录制会话：一次录制的完整记录（会持久化到磁盘）
class RecordingSession(BaseModel):
    session_id: str                 # 会话唯一 ID
    camera_id: str                  # 对应的摄像头 id
    field_session_id: Optional[str] = None   # 关联的 Field Session id（可选）
    court_name: str
    match_format: str
    camera_angle: str
    fps: int
    resolution: str
    auto_analyze_after_stop: bool
    status: RecordingSessionStatus  # 当前状态（recording / completed / failed / canceled）
    started_at: datetime
    stopped_at: Optional[datetime] = None        # 停止时间（未停止则为空）
    duration_sec: Optional[float] = None         # 录制时长（秒）
    video_path: Optional[str] = None             # 生成的视频文件位置
    video_id: Optional[str] = None               # 注册到视频系统后的 id
    auto_analysis_job_id: Optional[str] = None   # 自动创建的分析任务 id
    error_message: Optional[str] = None          # 失败时的错误信息
    capture_take_id: Optional[str] = None         # 关联的 CaptureTake ID


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
    field_session_id: Optional[str] = None
    court_name: str = ""
    match_format: Optional[Literal["singles", "doubles"]] = None
    cam_1_angle: str = "baseline_high"
    cam_2_angle: str = "baseline_high"
    fps: int = Field(default=60, ge=1, le=60)
    resolution: str = "1920x1080"
    auto_analyze_after_stop: bool = True

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
    ffmpeg_log_path: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    error_message: Optional[str] = None


class SyncSegment(BaseModel):
    """一个同步分段（两路同时录制的一个片段）"""
    segment_index: int
    status: SyncSegmentStatus = "recording"
    files: list[SyncSegmentFile] = []
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    restart_count: int = 0  # 该分段的同步重启次数
    error_message: Optional[str] = None


class SyncTestResult(BaseModel):
    """双摄短录测试结果"""
    success: bool
    cam_1_id: str
    cam_2_id: str
    duration_sec: float
    cam_1_online: bool = False
    cam_2_online: bool = False
    cam_1_first_frame_url: Optional[str] = None
    cam_2_first_frame_url: Optional[str] = None
    cam_1_first_frame_exists: bool = False
    cam_2_first_frame_exists: bool = False
    cam_1_file_size: int = 0
    cam_2_file_size: int = 0
    cam_1_error: Optional[str] = None
    cam_2_error: Optional[str] = None
    test_completed_at: Optional[datetime] = None


class SyncRecordingSession(BaseModel):
    """双摄同步录制会话"""
    session_id: str
    field_session_id: Optional[str] = None
    status: SyncRecordingStatus = "recording"
    camera_slots: dict[str, CameraSlotConfig] = {}  # "cam_1" / "cam_2"
    segments: list[SyncSegment] = []
    output_dir: str = ""
    default_analysis_video_id: Optional[str] = None
    registered_video_ids: dict[CameraSlotRole, str] = {}
    associated_video_paths: list[str] = []
    court_name: str = ""
    match_format: str = "doubles"
    fps: int = 30
    resolution: str = "1920x1080"
    auto_analyze_after_stop: bool = True
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    duration_sec: Optional[float] = None
    error_message: Optional[str] = None
    total_restarts: int = 0
    capture_take_id: Optional[str] = None


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
    default_analysis_video_id: Optional[str] = None
    analysis_available: bool = False
    analysis_blocked_reason: Optional[str] = None
