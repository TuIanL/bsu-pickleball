"""摄像头接入与录制控制的 Pydantic 数据模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class CameraInfo(BaseModel):
    camera_id: str
    name: str
    stream_url: str
    protocol: Literal["rtsp", "rtmp", "http"]
    username: Optional[str] = None
    password: Optional[str] = None
    created_at: datetime


class CameraCreateRequest(BaseModel):
    camera_id: str
    name: str
    stream_url: str
    protocol: Literal["rtsp", "rtmp", "http"] = "rtsp"
    username: Optional[str] = None
    password: Optional[str] = None


class CameraDeleteResponse(BaseModel):
    deleted: bool


class ProbeResult(BaseModel):
    camera_id: str
    online: bool
    latency_ms: Optional[int] = None
    resolution: Optional[str] = None
    detected_at: datetime
    error_message: Optional[str] = None


RecordingSessionStatus = Literal["recording", "completed", "failed", "canceled"]


class RecordingStartRequest(BaseModel):
    camera_id: str
    court_name: str = ""
    match_format: Literal["singles", "doubles"] = "doubles"
    camera_angle: str = "baseline_high"
    fps: int = Field(default=30, ge=1, le=120)
    resolution: str = "1920x1080"
    auto_analyze_after_stop: bool = True


class RecordingSession(BaseModel):
    session_id: str
    camera_id: str
    court_name: str
    match_format: str
    camera_angle: str
    fps: int
    resolution: str
    auto_analyze_after_stop: bool
    status: RecordingSessionStatus
    started_at: datetime
    stopped_at: Optional[datetime] = None
    duration_sec: Optional[float] = None
    video_path: Optional[str] = None
    video_id: Optional[str] = None
    auto_analysis_job_id: Optional[str] = None
    error_message: Optional[str] = None
