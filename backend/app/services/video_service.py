"""视频上传服务 —— 保存上传视频文件并在内存中维护 MVP 元数据。

职责：
- 接收前端传来的上传视频，流式写入磁盘（支持大文件，分块读写）；
- 用一个全局字典 `VIDEOS` 在内存里缓存"video_id → 元数据"；
- 同时把元数据落到磁盘 JSON，便于程序重启后还能找回。

这里只管"视频文件本身和它的基本信息"，不负责分析。
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.schemas.video import VideoMetadata
from app.services.storage_service import StorageService

# 允许上传的视频后缀白名单（不在里面的直接报错，避免乱传文件）
SUPPORTED_VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}
# 内存中的视频元数据缓存：video_id -> VideoMetadata
VIDEOS: dict[str, VideoMetadata] = {}


class UnsupportedVideoError(ValueError):
    # 自定义异常：用于表示"视频格式不支持"。继承自 ValueError，方便上层捕获。
    pass


class VideoService:
    """保存上传的源视频，并在内存中维护 MVP 阶段的元数据。"""

    def __init__(self, storage: StorageService | None = None) -> None:
        # 没传存储服务就新建一个
        self.storage = storage or StorageService()

    async def save_upload(self, upload: UploadFile) -> VideoMetadata:
        # 异步保存前端上传的视频文件。
        # UploadFile 是 FastAPI 提供的类型，表示一个上传的文件流。
        # 1) 取原始文件名，转小写得到后缀（如 .mp4）
        original_name = upload.filename or "uploaded-video"
        suffix = Path(original_name).suffix.lower()

        # 2) 后缀不在白名单就抛异常
        if suffix not in SUPPORTED_VIDEO_SUFFIXES:
            raise UnsupportedVideoError(f"Unsupported video type: {suffix or 'unknown'}")

        # 3) 生成一个唯一的 video_id，拼出目标文件路径
        video_id = f"video-{uuid4().hex[:10]}"
        destination = self.storage.uploads_dir / f"{video_id}{suffix}"
        size = 0

        # 4) 以二进制写模式打开目标文件，按 1MB 一块从上传流里读，边读边写（避免一次性加载到内存）
        with destination.open("wb") as output:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                output.write(chunk)

        # 5) 组装元数据对象（记录 id、原始文件名、类型、大小、路径、上传时间）
        metadata = VideoMetadata(
            id=video_id,
            original_filename=original_name,
            content_type=upload.content_type,
            size_bytes=size,
            path=str(destination),
            uploaded_at=datetime.now(UTC),
        )
        # 6) 写入内存缓存 + 落盘 JSON
        VIDEOS[video_id] = metadata
        self.storage.write_json(
            self.storage.video_metadata_path(video_id),
            metadata.model_dump(mode="json"),
        )
        return metadata

    def register_recording(self, file_path: Path, original_filename: str, file_size: int) -> str:
        # 登记一个"由摄像头录制产生"的视频（不是前端上传的）。
        # 与 save_upload 的区别：文件已经在磁盘上，这里只是登记元数据。
        video_id = f"rec-{uuid4().hex[:10]}"
        metadata = VideoMetadata(
            id=video_id,
            original_filename=original_filename,
            content_type="video/mp4",
            size_bytes=file_size,
            path=str(file_path),
            uploaded_at=datetime.now(UTC),
            source="recording",  # 标记来源为"录制"
        )
        VIDEOS[video_id] = metadata
        self.storage.write_json(
            self.storage.video_metadata_path(video_id),
            metadata.model_dump(mode="json"),
        )
        return video_id

    def get_video(self, video_id: str) -> VideoMetadata | None:
        # 按 video_id 取元数据：先查内存缓存，缓存没有再读磁盘 JSON。
        cached = VIDEOS.get(video_id)
        if cached is not None:
            return cached

        path = self.storage.video_metadata_path(video_id)
        if not path.exists():
            return None

        # model_validate：把普通 dict 还原成 Pydantic 模型对象
        metadata = VideoMetadata.model_validate(self.storage.read_json(path))
        VIDEOS[video_id] = metadata
        return metadata


# 全局单例：整个进程共用一个 VideoService（MVP 阶段足够）
video_service = VideoService()
