"""CaptureCodingAction SQLAlchemy ORM model —— 持久化命令日志，支撑幂等、undo、审计。"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CodingActionStatus(enum.StrEnum):
    executed = "executed"
    undone = "undone"
    rejected = "rejected"


class CaptureCodingAction(Base):
    __tablename__ = "capture_coding_actions"
    __table_args__ = (
        UniqueConstraint("capture_take_id", "client_action_id", name="uq_coding_client_action"),
        Index("idx_coding_take_revision", "capture_take_id", "revision_before"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    capture_take_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("capture_takes.id", ondelete="RESTRICT"), nullable=False
    )
    client_action_id: Mapped[str] = mapped_column(String(128), nullable=False)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    timestamp_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    request_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[CodingActionStatus] = mapped_column(
        Enum(CodingActionStatus), nullable=False, default=CodingActionStatus.executed
    )
    revision_before: Mapped[int] = mapped_column(Integer, nullable=False)
    revision_after: Mapped[int | None] = mapped_column(Integer, nullable=True)

    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)

    reverses_action_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    annotation_package_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    vidat_import_audit_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
