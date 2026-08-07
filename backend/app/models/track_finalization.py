"""TrackFinalization ORM —— 片段合并记录（幂等信息持久化）"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class FinalizationStatus(enum.StrEnum):
    running = "running"
    completed = "completed"
    failed = "failed"


class TrackFinalization(Base):
    __tablename__ = "track_finalizations"
    __table_args__ = (UniqueConstraint("capture_track_id", "manifest_hash", name="uq_finalization_track_hash"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    capture_track_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    status: Mapped[FinalizationStatus] = mapped_column(
        Enum(FinalizationStatus), nullable=False, default=FinalizationStatus.running
    )
    output_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    video_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
