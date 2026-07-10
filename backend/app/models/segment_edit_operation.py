"""SegmentEditOperation SQLAlchemy ORM model —— 编辑操作审计记录。"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Integer, String, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class EditOperationType(str, enum.Enum):
    boundary_correction = "boundary_correction"
    rename = "rename"
    split = "split"
    merge = "merge"
    archive = "archive"
    restore = "restore"


class SegmentEditOperation(Base):
    __tablename__ = "segment_edit_operations"
    __table_args__ = (
        Index("idx_edit_ops_take", "capture_take_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    capture_take_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("capture_takes.id", ondelete="RESTRICT"), nullable=False
    )
    operation_type: Mapped[EditOperationType] = mapped_column(
        Enum(EditOperationType), nullable=False
    )
    input_segment_ids: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    output_segment_ids: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
