"""
视频上传与元数据管理的 Pydantic 数据模型。

这些模型描述"一个上传的视频"在系统里如何表示：它的基本信息（文件名、大小、路径、上传时间），
以及上传接口返回给前端的数据结构。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field


class VideoMetadata(BaseModel):
    """单个视频的元数据（描述信息，不含视频画面本身）。"""

    id: str  # 视频唯一 ID
    original_filename: str  # 用户上传时的原始文件名
    content_type: str | None = None  # MIME 类型，如 "video/mp4"
    size_bytes: int = Field(ge=0)  # 文件大小（字节），ge=0 表示不能为负
    path: str  # 视频在服务器磁盘上的存储路径
    uploaded_at: datetime  # 上传时间
    source: str = "upload"  # 来源标识（upload=用户上传，也可能是录制等）
    display_title: str | None = None  # 用户自定义显示标题（Library 卡片优先采用；缺省回退 original_filename）
    display_date: datetime | None = None  # 用户自定义比赛日期（Library 卡片优先采用；缺省回退 uploaded_at）

    @property
    def filename(self) -> str:
        # 从完整路径里取出纯文件名（不含目录）
        return Path(self.path).name


class VideoUploadResponse(BaseModel):
    """上传视频接口的响应：把整条视频元数据包在 video 字段里返回。"""

    video: VideoMetadata


class VideoUpdateRequest(BaseModel):
    """更新视频显示元数据的请求体（Library 卡片内联编辑）。"""

    display_title: str | None = None
    display_date: datetime | None = None


class VideoCatalogResponse(BaseModel):
    """视频目录接口（GET /api/videos）的响应：只读枚举全部已注册视频元数据。"""

    videos: list[VideoMetadata]


class VideoReadError(BaseModel):
    """读取视频出错时的统一错误结构。"""

    code: str  # 错误代码（机器可读）
    message: str  # 错误描述（给人看）


class VideoTimingFrame(BaseModel):
    """A source-frame timing row exposed to the calibration workbench."""

    frame_index: int = Field(ge=0)
    pts_seconds: float
    dts_seconds: float | None = None
    keyframe: bool = False


class VideoTimingResponse(BaseModel):
    """Validated source PTS mapping for one registered video."""

    schema_version: str = "frame_timing_provider.v1"
    authority: str
    frame_count: int = Field(ge=0)
    fps: float | None = None
    first_pts_seconds: float | None = None
    last_pts_seconds: float | None = None
    frames: list[VideoTimingFrame]


class VideoTimingMaterializeResponse(BaseModel):
    """Result of synchronously materializing a registered video's PTS sidecar.

    Mirrors the sidecar summary returned by the materialization pipeline; on a
    reuse fast path ``reused`` is true and the media was never touched.
    """

    schema_version: str = "frame_timing_provider.v1"
    authority: str  # "source_pts" | "missing"
    status: str  # "ready" | "failed"
    reused: bool = False
    frame_count: int = Field(ge=0)
    fps: float | None = None
    first_pts_seconds: float | None = None
    last_pts_seconds: float | None = None
    sidecar_path: str | None = None
    reason: str | None = None
