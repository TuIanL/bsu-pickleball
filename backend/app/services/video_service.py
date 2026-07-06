"""视频上传服务 —— 保存上传视频文件并在内存中维护 MVP 元数据。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.schemas.video import VideoMetadata
from app.services.storage_service import StorageService


SUPPORTED_VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}
VIDEOS: dict[str, VideoMetadata] = {}


class UnsupportedVideoError(ValueError):
    pass


class VideoService:
    """Stores uploaded source videos and keeps MVP metadata in memory."""

    def __init__(self, storage: StorageService | None = None) -> None:
        self.storage = storage or StorageService()

    async def save_upload(self, upload: UploadFile) -> VideoMetadata:
        original_name = upload.filename or "uploaded-video"
        suffix = Path(original_name).suffix.lower()

        if suffix not in SUPPORTED_VIDEO_SUFFIXES:
            raise UnsupportedVideoError(f"Unsupported video type: {suffix or 'unknown'}")

        video_id = f"video-{uuid4().hex[:10]}"
        destination = self.storage.uploads_dir / f"{video_id}{suffix}"
        size = 0

        with destination.open("wb") as output:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                output.write(chunk)

        metadata = VideoMetadata(
            id=video_id,
            original_filename=original_name,
            content_type=upload.content_type,
            size_bytes=size,
            path=str(destination),
            uploaded_at=datetime.now(timezone.utc),
        )
        VIDEOS[video_id] = metadata
        self.storage.write_json(
            self.storage.video_metadata_path(video_id),
            metadata.model_dump(mode="json"),
        )
        return metadata

    def register_recording(self, file_path: Path, original_filename: str, file_size: int) -> str:
        video_id = f"rec-{uuid4().hex[:10]}"
        metadata = VideoMetadata(
            id=video_id,
            original_filename=original_filename,
            content_type="video/mp4",
            size_bytes=file_size,
            path=str(file_path),
            uploaded_at=datetime.now(timezone.utc),
            source="recording",
        )
        VIDEOS[video_id] = metadata
        self.storage.write_json(
            self.storage.video_metadata_path(video_id),
            metadata.model_dump(mode="json"),
        )
        return video_id

    def get_video(self, video_id: str) -> VideoMetadata | None:
        cached = VIDEOS.get(video_id)
        if cached is not None:
            return cached

        path = self.storage.video_metadata_path(video_id)
        if not path.exists():
            return None

        metadata = VideoMetadata.model_validate(self.storage.read_json(path))
        VIDEOS[video_id] = metadata
        return metadata


video_service = VideoService()
