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

from pydantic import BaseModel, Field


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
    fps: int = Field(default=30, ge=1, le=120)  # 帧率，限制 1~120
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


# 删除录制会话的结果
RecordingDeleteStatus = Literal["deleted", "blocked", "not_found"]


class RecordingDeleteResult(BaseModel):
    session_id: str
    status: RecordingDeleteStatus
    detail: str = ""
