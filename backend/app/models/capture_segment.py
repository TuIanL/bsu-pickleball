"""CaptureSegment SQLAlchemy ORM model —— 区间投影，支持人工修正和非破坏式编辑。"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# 区间类型枚举：盘/局/回合/自定义
class SegmentType(enum.StrEnum):
    set = "set"  # 盘
    game = "game"  # 局
    rally = "rally"  # 回合
    custom = "custom"  # 自定义


# 区间状态枚举
class SegmentStatus(enum.StrEnum):
    open = "open"  # 开放中（未结束）
    closed = "closed"  # 已关闭（正常结束）
    inferred = "inferred"  # 算法推断
    corrected = "corrected"  # 人工修正


# 区间来源枚举
class SegmentSource(enum.StrEnum):
    manual = "manual"  # 人工标注
    algorithm = "algorithm"  # 算法生成
    corrected = "corrected"  # 人工修正
    vidat_import = "vidat_import"


# 编辑状态枚举（支持非破坏式编辑）
class EditStatus(enum.StrEnum):
    active = "active"  # 当前有效
    superseded = "superseded"  # 已被替代
    archived = "archived"  # 已归档


# 区间模型，映射 capture_segments 表
class CaptureSegment(Base):
    __tablename__ = "capture_segments"
    __table_args__ = (
        CheckConstraint(
            "end_ms IS NULL OR end_ms >= start_ms", name="ck_segment_end_after_start"
        ),  # 结束时间不能早于开始时间
        Index("idx_segment_take_type", "capture_take_id", "segment_type", "start_ms"),  # 按录制单元+类型+起始时间索引
        Index("idx_segment_parent", "parent_segment_id"),  # 父区间索引
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # 主键ID
    capture_take_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("capture_takes.id", ondelete="RESTRICT"),
        nullable=False,  # 所属录制单元ID（外键，禁止级联删除）
    )
    segment_type: Mapped[SegmentType] = mapped_column(Enum(SegmentType), nullable=False)  # 区间类型
    parent_segment_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("capture_segments.id", ondelete="SET NULL"),
        nullable=True,  # 父区间ID（用于层级结构，如盘→局→回合）
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # 同一层级内的序号
    label: Mapped[str] = mapped_column(String(256), nullable=False, default="")  # 标签

    start_event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 开始事件ID
    end_event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 结束事件ID
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)  # 起始毫秒偏移
    end_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 结束毫秒偏移

    # 人工修正边界（不覆盖原始 start_ms/end_ms）
    corrected_start_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 修正后的起始偏移
    corrected_end_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 修正后的结束偏移
    edit_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 编辑版本号
    corrected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # 修正时间

    # 非破坏式编辑状态
    edit_status: Mapped[EditStatus] = mapped_column(
        Enum(EditStatus),
        nullable=False,
        default=EditStatus.active,  # 编辑状态
    )
    superseded_by_operation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 被哪个操作ID替代
    created_by_operation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 由哪个操作ID创建

    status: Mapped[SegmentStatus] = mapped_column(
        Enum(SegmentStatus),
        nullable=False,
        default=SegmentStatus.open,  # 区间状态
    )
    close_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 关闭原因
    source: Mapped[SegmentSource] = mapped_column(
        Enum(SegmentSource),
        nullable=False,
        default=SegmentSource.manual,  # 数据来源
    )
    is_highlight: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # 是否为高亮片段
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

    # 获取有效起始时间（优先使用修正值）
    @property
    def effective_start_ms(self) -> int:
        return self.corrected_start_ms if self.corrected_start_ms is not None else self.start_ms

    # 获取有效结束时间（优先使用修正值）
    @property
    def effective_end_ms(self) -> int | None:
        return self.corrected_end_ms if self.corrected_end_ms is not None else self.end_ms
