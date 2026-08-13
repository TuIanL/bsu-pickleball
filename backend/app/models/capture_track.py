"""CaptureTrack SQLAlchemy ORM model —— 录制单轨，含时间偏移与同步质量标记。"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# 轨道角色枚举
class TrackRole(enum.StrEnum):
    primary = "primary"  # 主视角
    secondary = "secondary"  # 次视角


# 摄像头插槽枚举
class CaptureTrackSlot(enum.StrEnum):
    cam_1 = "cam_1"  # 摄像头1
    cam_2 = "cam_2"  # 摄像头2


# 分析角色枚举
class AnalysisRole(enum.StrEnum):
    default = "default"  # 默认
    supplementary = "supplementary"  # 补充


# 时间偏移来源枚举
class OffsetSource(enum.StrEnum):
    measured = "measured"  # 实测
    assumed = "assumed"  # 假设
    corrected = "corrected"  # 修正


# 同步质量枚举
class SyncQuality(enum.StrEnum):
    good = "good"  # 良好
    degraded = "degraded"  # 降级
    unknown = "unknown"  # 未知


# 单摄轨道模型，映射 capture_tracks 表
class CaptureTrack(Base):
    __tablename__ = "capture_tracks"
    __table_args__ = (
        UniqueConstraint("capture_take_id", "slot", name="uq_track_take_slot"),  # 同一录制单元内插槽唯一
        Index("idx_track_take", "capture_take_id"),  # 按录制单元索引
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # 主键ID
    capture_take_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("capture_takes.id", ondelete="RESTRICT"),
        nullable=False,  # 所属录制单元ID（外键，禁止级联删除）
    )
    camera_id: Mapped[str] = mapped_column(String(128), nullable=False)  # 摄像头ID
    role: Mapped[TrackRole] = mapped_column(Enum(TrackRole), nullable=False)  # 轨道角色
    slot: Mapped[CaptureTrackSlot] = mapped_column(
        Enum(CaptureTrackSlot),
        nullable=False,
        default=CaptureTrackSlot.cam_1,  # 插槽位置
    )
    analysis_role: Mapped[AnalysisRole] = mapped_column(
        Enum(AnalysisRole),
        nullable=False,
        default=AnalysisRole.default,  # 分析角色
    )
    video_id: Mapped[str | None] = mapped_column(String(128), nullable=True)  # 视频文件ID
    offset_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 时间偏移量（毫秒，相对于主轨）
    offset_source: Mapped[OffsetSource] = mapped_column(
        Enum(OffsetSource),
        nullable=False,
        default=OffsetSource.assumed,  # 偏移来源
    )
    sync_quality: Mapped[SyncQuality] = mapped_column(
        Enum(SyncQuality),
        nullable=False,
        default=SyncQuality.unknown,  # 同步质量
    )
    # Local source timing is independent from cross-camera sync quality.
    timing_authority: Mapped[str] = mapped_column(
        String(32), nullable=False, default="missing", server_default="missing"
    )
    timing_sidecar_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    timing_failure_reason: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),  # 创建时间
    )
