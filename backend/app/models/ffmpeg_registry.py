"""FFmpegProcessRegistry SQLAlchemy ORM model —— FFmpeg 进程登记。"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class FFmpegProcessRegistry(Base):
    __tablename__ = "ffmpeg_registry"
    __table_args__ = (
        Index("idx_ffmpeg_take", "capture_take_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    capture_take_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    track_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pid: Mapped[int] = mapped_column(Integer, nullable=False)
    pgid: Mapped[int] = mapped_column(Integer, nullable=False)
    command_fingerprint: Mapped[str] = mapped_column(String(32), nullable=False)
    output_path: Mapped[str] = mapped_column(String(512), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
