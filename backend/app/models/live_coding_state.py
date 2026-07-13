"""LiveCodingState SQLAlchemy ORM model —— 当前编码状态快照，可从命令日志重建。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# 实时编码状态快照模型，映射 live_coding_states 表
class LiveCodingState(Base):
    __tablename__ = "live_coding_states"

    capture_take_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("capture_takes.id", ondelete="CASCADE"), primary_key=True   # 所属录制单元ID（主键/外键，级联删除）
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)              # 版本号（用于乐观锁/重建）
    set_ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)           # 当前盘序号
    game_ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)          # 当前局序号
    rally_ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)         # 当前回合序号
    non_play: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)         # 是否为非比赛时段
    match_phase: Mapped[str] = mapped_column(String(32), nullable=False, default="idle")  # 比赛阶段（idle/playing/break 等）
    intermission_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)       # 间歇类型（如 timeout/break）

    current_set_segment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 当前盘区间ID
    current_game_segment_id: Mapped[str | None] = mapped_column(String(64), nullable=True) # 当前局区间ID
    current_rally_segment_id: Mapped[str | None] = mapped_column(String(64), nullable=True) # 当前回合区间ID

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),                                      # 更新时间
        onupdate=lambda: datetime.now(timezone.utc),
    )
