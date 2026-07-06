"""视频上传与元数据管理的 Pydantic 数据模型。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class VideoMetadata(BaseModel):
    id: str
    original_filename: str
    content_type: Optional[str] = None
    size_bytes: int = Field(ge=0)
    path: str
    uploaded_at: datetime
    source: str = "upload"

    @property
    def filename(self) -> str:
        return Path(self.path).name


class VideoUploadResponse(BaseModel):
    video: VideoMetadata


class VideoReadError(BaseModel):
    code: str
    message: str
