"""LiveCodingState SQLAlchemy ORM model —— 当前编码状态快照，可从命令日志重建。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LiveCodingState(Base):
    __tablename__ = "live_coding_states"

    capture_take_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("capture_takes.id", ondelete="CASCADE"), primary_key=True
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    set_ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    game_ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rally_ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    non_play: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    current_set_segment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    current_game_segment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    current_rally_segment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
