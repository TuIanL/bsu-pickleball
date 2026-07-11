"""MediaFragment ORM —— 录制分片持久化"""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Integer, String, Text, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class FragmentStatus(str, enum.Enum):
    starting = "starting"
    recording = "recording"
    completed = "completed"
    failed = "failed"
    interrupted = "interrupted"
    discarded = "discarded"


class MediaFragment(Base):
    __tablename__ = "media_fragments"
    __table_args__ = (
        UniqueConstraint("capture_track_id", "fragment_index", name="uq_fragment_track_index"),
        Index("idx_fragment_take", "capture_take_id"),
        Index("idx_fragment_track", "capture_track_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    capture_take_id: Mapped[str] = mapped_column(String(64), nullable=False)
    capture_track_id: Mapped[str] = mapped_column(String(64), nullable=False)

    fragment_index: Mapped[int] = mapped_column(Integer, nullable=False)
    rotation_index: Mapped[int] = mapped_column(Integer, nullable=False)

    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[FragmentStatus] = mapped_column(
        Enum(FragmentStatus), nullable=False, default=FragmentStatus.starting
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    take_start_offset_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    take_end_offset_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    media_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    stop_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    return_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
