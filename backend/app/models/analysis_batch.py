"""AnalysisBatch & AnalysisBatchItem SQLAlchemy ORM models —— 批量分析任务管理。"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Integer, String, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BatchStatus(str, enum.Enum):
    creating = "creating"
    queued = "queued"
    running = "running"
    partial = "partial"
    completed = "completed"
    failed = "failed"


class BatchItemStatus(str, enum.Enum):
    pending = "pending"
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class AnalysisBatch(Base):
    __tablename__ = "analysis_batches"
    __table_args__ = (
        Index("idx_batch_take", "capture_take_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    capture_take_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("capture_takes.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[BatchStatus] = mapped_column(
        Enum(BatchStatus), nullable=False, default=BatchStatus.creating
    )
    analysis_profile: Mapped[str] = mapped_column(
        String(64), nullable=False, default="match_default"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )


class AnalysisBatchItem(Base):
    __tablename__ = "analysis_batch_items"
    __table_args__ = (
        Index("idx_batch_item_batch", "batch_id"),
        Index("idx_batch_item_segment", "segment_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    batch_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("analysis_batches.id", ondelete="CASCADE"), nullable=False
    )
    segment_id: Mapped[str] = mapped_column(String(64), nullable=False)
    analysis_job_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    segment_version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    track_id: Mapped[str] = mapped_column(String(64), nullable=False)
    video_id: Mapped[str] = mapped_column(String(128), nullable=False)

    status: Mapped[BatchItemStatus] = mapped_column(
        Enum(BatchItemStatus), nullable=False, default=BatchItemStatus.pending
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
