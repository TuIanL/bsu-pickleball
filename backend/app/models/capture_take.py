"""CaptureTake SQLAlchemy ORM model —— 统一单摄/双摄录制时间轴的逻辑录制单元。"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Integer, String, CheckConstraint, UniqueConstraint, Index, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# 录制单元状态枚举
class CaptureTakeStatus(str, enum.Enum):
    starting = "starting"      # 开始中
    recording = "recording"    # 录制中
    completed = "completed"    # 已完成
    partial = "partial"        # 部分完成
    failed = "failed"          # 失败
    canceled = "canceled"      # 已取消


# 录制模式枚举
class CaptureMode(str, enum.Enum):
    single = "single"  # 单摄
    dual = "dual"      # 双摄


# 源会话类型枚举
class SourceSessionType(str, enum.Enum):
    recording = "recording"              # 普通录制
    sync_recording = "sync_recording"    # 同步录制


# 录制单元模型，映射 capture_takes 表
class CaptureTake(Base):
    __tablename__ = "capture_takes"
    __table_args__ = (
        UniqueConstraint("source_session_type", "source_session_id", name="uq_take_source"),  # 源会话唯一约束
        CheckConstraint("duration_ms IS NULL OR duration_ms >= 0", name="ck_take_duration_nonneg"),  # 时长非负
        CheckConstraint("revision >= 0", name="ck_take_revision_nonneg"),                     # 版本号非负
        Index("idx_take_field_session", "field_session_id", "started_at"),                    # 按场次+开始时间索引
        Index("idx_take_status", "status"),                                                    # 按状态索引
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)                             # 主键ID
    field_session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("field_sessions.id"), nullable=False, index=True                # 所属场次ID（外键）
    )
    capture_mode: Mapped[CaptureMode] = mapped_column(
        Enum(CaptureMode), nullable=False                                                      # 录制模式
    )
    source_session_type: Mapped[SourceSessionType] = mapped_column(
        Enum(SourceSessionType), nullable=False                                                # 源会话类型
    )
    source_session_id: Mapped[str] = mapped_column(String(128), nullable=False)                # 源会话ID
    storage_root: Mapped[str | None] = mapped_column(String(1024), nullable=True)              # 存储根目录
    session_dir: Mapped[str | None] = mapped_column(String(1024), nullable=True)               # 会话目录
    storage_status: Mapped[str] = mapped_column(String(32), nullable=False, default="available")  # 存储状态

    status: Mapped[CaptureTakeStatus] = mapped_column(
        Enum(CaptureTakeStatus), nullable=False, default=CaptureTakeStatus.recording           # 录制状态
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)                    # 开始时间
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)                 # 结束时间
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)                    # 持续时间（毫秒）
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)                  # 版本号

    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)              # 归档时间

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)                    # 创建时间
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),                                             # 更新时间
        onupdate=lambda: datetime.now(timezone.utc),
    )
