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

    @property
    def filename(self) -> str:
        # 从完整路径里取出纯文件名（不含目录）
        return Path(self.path).name


class VideoUploadResponse(BaseModel):
    """上传视频接口的响应：把整条视频元数据包在 video 字段里返回。"""

    video: VideoMetadata


class VideoReadError(BaseModel):
    """读取视频出错时的统一错误结构。"""

    code: str  # 错误代码（机器可读）
    message: str  # 错误描述（给人看）
