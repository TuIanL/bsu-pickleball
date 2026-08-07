"""CameraLease SQLAlchemy ORM model —— 摄像机录制占用租约。"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LeaseStatus(enum.StrEnum):
    active = "active"
    released = "released"


class CameraLease(Base):
    __tablename__ = "camera_leases"
    __table_args__ = (
        Index("idx_lease_status", "status"),
        Index("idx_lease_take", "capture_take_id"),
    )

    camera_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    capture_take_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_session_id: Mapped[str] = mapped_column(String(128), nullable=False)
    owner_instance_id: Mapped[str] = mapped_column(String(128), nullable=False, default="default")
    status: Mapped[LeaseStatus] = mapped_column(Enum(LeaseStatus), nullable=False, default=LeaseStatus.active)
    acquired_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
