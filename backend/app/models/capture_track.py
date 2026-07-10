"""CaptureTrack SQLAlchemy ORM model —— 录制单轨，含时间偏移与同步质量标记。"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Integer, String, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TrackRole(str, enum.Enum):
    primary = "primary"
    secondary = "secondary"


class OffsetSource(str, enum.Enum):
    measured = "measured"
    assumed = "assumed"
    corrected = "corrected"


class SyncQuality(str, enum.Enum):
    good = "good"
    degraded = "degraded"
    unknown = "unknown"


class CaptureTrack(Base):
    __tablename__ = "capture_tracks"
    __table_args__ = (
        UniqueConstraint("capture_take_id", "role", name="uq_track_take_role"),
        Index("idx_track_take", "capture_take_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    capture_take_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("capture_takes.id", ondelete="RESTRICT"), nullable=False
    )
    camera_id: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[TrackRole] = mapped_column(Enum(TrackRole), nullable=False)
    video_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    offset_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    offset_source: Mapped[OffsetSource] = mapped_column(
        Enum(OffsetSource), nullable=False, default=OffsetSource.assumed
    )
    sync_quality: Mapped[SyncQuality] = mapped_column(
        Enum(SyncQuality), nullable=False, default=SyncQuality.unknown
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
