"""CaptureSegment SQLAlchemy ORM model —— 区间投影，支持人工修正和非破坏式编辑。"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, Integer, String, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SegmentType(str, enum.Enum):
    set = "set"
    game = "game"
    rally = "rally"
    custom = "custom"


class SegmentStatus(str, enum.Enum):
    open = "open"
    closed = "closed"
    inferred = "inferred"
    corrected = "corrected"


class SegmentSource(str, enum.Enum):
    manual = "manual"
    algorithm = "algorithm"
    corrected = "corrected"


class EditStatus(str, enum.Enum):
    active = "active"
    superseded = "superseded"
    archived = "archived"


class CaptureSegment(Base):
    __tablename__ = "capture_segments"
    __table_args__ = (
        CheckConstraint("end_ms IS NULL OR end_ms >= start_ms", name="ck_segment_end_after_start"),
        Index("idx_segment_take_type", "capture_take_id", "segment_type", "start_ms"),
        Index("idx_segment_parent", "parent_segment_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    capture_take_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("capture_takes.id", ondelete="RESTRICT"), nullable=False
    )
    segment_type: Mapped[SegmentType] = mapped_column(Enum(SegmentType), nullable=False)
    parent_segment_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("capture_segments.id", ondelete="SET NULL"), nullable=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    label: Mapped[str] = mapped_column(String(256), nullable=False, default="")

    start_event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    end_event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 人工修正边界（不覆盖原始 start_ms/end_ms）
    corrected_start_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    corrected_end_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    edit_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    corrected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # 非破坏式编辑状态
    edit_status: Mapped[EditStatus] = mapped_column(
        Enum(EditStatus), nullable=False, default=EditStatus.active
    )
    superseded_by_operation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by_operation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    status: Mapped[SegmentStatus] = mapped_column(
        Enum(SegmentStatus), nullable=False, default=SegmentStatus.open
    )
    close_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source: Mapped[SegmentSource] = mapped_column(
        Enum(SegmentSource), nullable=False, default=SegmentSource.manual
    )
    is_highlight: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    @property
    def effective_start_ms(self) -> int:
        return self.corrected_start_ms if self.corrected_start_ms is not None else self.start_ms

    @property
    def effective_end_ms(self) -> int | None:
        return self.corrected_end_ms if self.corrected_end_ms is not None else self.end_ms
