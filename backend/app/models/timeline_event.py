"""SessionTimelineEvent SQLAlchemy ORM model."""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TimelineEventType(str, enum.Enum):
    session_note = "session_note"
    non_play_start = "non_play_start"
    non_play_end = "non_play_end"
    game_start = "game_start"
    game_end = "game_end"
    set_start = "set_start"
    set_end = "set_end"
    rally_start = "rally_start"
    rally_end = "rally_end"
    score_update = "score_update"
    score_correction = "score_correction"
    side_change = "side_change"
    timeout_start = "timeout_start"
    timeout_end = "timeout_end"
    drill_start = "drill_start"
    drill_end = "drill_end"
    custom_marker = "custom_marker"


class TimelineEventSource(str, enum.Enum):
    manual = "manual"
    algorithm = "algorithm"
    corrected = "corrected"


class SessionTimelineEvent(Base):
    __tablename__ = "session_timeline_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    field_session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("field_sessions.id"), nullable=False, index=True
    )
    recording_session_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    capture_take_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    timestamp_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    event_type: Mapped[TimelineEventType] = mapped_column(
        Enum(TimelineEventType), nullable=False
    )
    source: Mapped[TimelineEventSource] = mapped_column(
        Enum(TimelineEventSource), nullable=False, default=TimelineEventSource.manual
    )

    label: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    is_undone: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
