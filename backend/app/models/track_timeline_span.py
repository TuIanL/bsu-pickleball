"""TrackTimelineSpan ORM —— CaptureTake 时间到合并 MP4 时间的映射"""

from __future__ import annotations

from sqlalchemy import Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TrackTimelineSpan(Base):
    __tablename__ = "track_timeline_spans"
    __table_args__ = (
        Index("idx_span_finalization", "track_finalization_id"),
        Index("idx_span_fragment", "fragment_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    track_finalization_id: Mapped[str] = mapped_column(String(64), nullable=False)
    fragment_id: Mapped[str] = mapped_column(String(64), nullable=False)

    take_start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    take_end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    output_start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    output_end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    gap_before_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
