"""SessionTimelineEvent SQLAlchemy ORM model —— 时间轴事件，记录比赛/录制过程中的各类事件。"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# 时间轴事件类型枚举
class TimelineEventType(enum.StrEnum):
    session_note = "session_note"  # 会话备注
    non_play_start = "non_play_start"  # 非比赛时段开始（休息/暂停等）
    non_play_end = "non_play_end"  # 非比赛时段结束
    game_start = "game_start"  # 局开始
    game_end = "game_end"  # 局结束
    set_start = "set_start"  # 盘开始
    set_end = "set_end"  # 盘结束
    rally_start = "rally_start"  # 回合开始
    rally_end = "rally_end"  # 回合结束
    score_update = "score_update"  # 比分更新
    score_correction = "score_correction"  # 比分修正
    side_change = "side_change"  # 换边
    timeout_start = "timeout_start"  # 暂停开始
    timeout_end = "timeout_end"  # 暂停结束
    drill_start = "drill_start"  # 训练开始
    drill_end = "drill_end"  # 训练结束
    custom_marker = "custom_marker"  # 自定义标记


# 事件来源枚举
class TimelineEventSource(enum.StrEnum):
    manual = "manual"  # 人工标注
    algorithm = "algorithm"  # 算法自动生成
    corrected = "corrected"  # 人工修正
    vidat_import = "vidat_import"  # Vidat 确认导入


# 时间轴事件模型，映射 session_timeline_events 表
class SessionTimelineEvent(Base):
    __tablename__ = "session_timeline_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # 主键ID
    field_session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("field_sessions.id"),
        nullable=False,
        index=True,  # 所属场次ID（外键）
    )
    recording_session_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)  # 录制会话ID
    capture_take_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)  # 录制单元ID

    timestamp_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 事件时间戳（毫秒，相对于录制起点）
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),  # 事件发生的UTC时间
    )

    event_type: Mapped[TimelineEventType] = mapped_column(
        Enum(TimelineEventType),
        nullable=False,  # 事件类型
    )
    source: Mapped[TimelineEventSource] = mapped_column(
        Enum(TimelineEventSource),
        nullable=False,
        default=TimelineEventSource.manual,  # 事件来源
    )

    label: Mapped[str] = mapped_column(String(256), nullable=False, default="")  # 标签（简短描述）
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")  # 备注详情
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")  # 附加数据（JSON格式）
    is_undone: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # 是否已撤销
    annotation_package_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    vidat_import_audit_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),  # 创建时间
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),  # 更新时间
        onupdate=lambda: datetime.now(UTC),
    )
