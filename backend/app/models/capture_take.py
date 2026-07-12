"""CaptureTake SQLAlchemy ORM model —— 统一单摄/双摄录制时间轴的逻辑录制单元。"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Integer, String, CheckConstraint, UniqueConstraint, Index, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CaptureTakeStatus(str, enum.Enum):
    starting = "starting"
    recording = "recording"
    completed = "completed"
    partial = "partial"
    failed = "failed"
    canceled = "canceled"


class CaptureMode(str, enum.Enum):
    single = "single"
    dual = "dual"


class SourceSessionType(str, enum.Enum):
    recording = "recording"
    sync_recording = "sync_recording"


class CaptureTake(Base):
    __tablename__ = "capture_takes"
    __table_args__ = (
        UniqueConstraint("source_session_type", "source_session_id", name="uq_take_source"),
        CheckConstraint("duration_ms IS NULL OR duration_ms >= 0", name="ck_take_duration_nonneg"),
        CheckConstraint("revision >= 0", name="ck_take_revision_nonneg"),
        Index("idx_take_field_session", "field_session_id", "started_at"),
        Index("idx_take_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    field_session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("field_sessions.id"), nullable=False, index=True
    )
    capture_mode: Mapped[CaptureMode] = mapped_column(
        Enum(CaptureMode), nullable=False
    )
    source_session_type: Mapped[SourceSessionType] = mapped_column(
        Enum(SourceSessionType), nullable=False
    )
    source_session_id: Mapped[str] = mapped_column(String(128), nullable=False)
    storage_root: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    session_dir: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    storage_status: Mapped[str] = mapped_column(String(32), nullable=False, default="available")

    status: Mapped[CaptureTakeStatus] = mapped_column(
        Enum(CaptureTakeStatus), nullable=False, default=CaptureTakeStatus.recording
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
