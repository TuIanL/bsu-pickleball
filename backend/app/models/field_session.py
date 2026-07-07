"""FieldSession SQLAlchemy ORM model."""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CaptureMode(str, enum.Enum):
    practice = "practice"
    match = "match"
    engineering = "engineering"


class MatchFormat(str, enum.Enum):
    singles = "singles"
    doubles = "doubles"


class CameraSetup(str, enum.Enum):
    single = "single"
    dual = "dual"
    debug_single = "debug_single"


class FieldSessionStatus(str, enum.Enum):
    planned = "planned"
    live = "live"
    completed = "completed"
    archived = "archived"


class FieldSession(Base):
    __tablename__ = "field_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    venue: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    court_name: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    capture_mode: Mapped[CaptureMode] = mapped_column(Enum(CaptureMode), nullable=False, default=CaptureMode.practice)
    match_format: Mapped[MatchFormat] = mapped_column(Enum(MatchFormat), nullable=False, default=MatchFormat.doubles)
    camera_setup: Mapped[CameraSetup] = mapped_column(Enum(CameraSetup), nullable=False, default=CameraSetup.single)
    status: Mapped[FieldSessionStatus] = mapped_column(Enum(FieldSessionStatus), nullable=False, default=FieldSessionStatus.planned)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")

    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
