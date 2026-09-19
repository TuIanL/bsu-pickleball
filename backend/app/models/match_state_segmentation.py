"""正式比赛状态切分运行与不可变窗口计划的持久化模型。"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MatchStateSegmentationRunStatus(enum.StrEnum):
    running = "running"
    succeeded = "succeeded"
    valid_no_rallies = "valid_no_rallies"
    low_evidence = "low_evidence"
    input_unavailable = "input_unavailable"
    sync_unavailable = "sync_unavailable"
    model_unavailable = "model_unavailable"
    inference_failed = "inference_failed"
    failed = "failed"
    canceled = "canceled"
    interrupted = "interrupted"
    superseded = "superseded"


class MatchStateSegmentationRun(Base):
    __tablename__ = "match_state_segmentation_runs"
    __table_args__ = (
        Index("idx_segmentation_run_take_status", "capture_take_id", "status"),
        Index("idx_segmentation_run_planning_job", "planning_job_id"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    capture_take_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("capture_takes.id", ondelete="RESTRICT"), nullable=False
    )
    planning_job_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[MatchStateSegmentationRunStatus] = mapped_column(
        Enum(MatchStateSegmentationRunStatus), nullable=False, default=MatchStateSegmentationRunStatus.running
    )
    profile: Mapped[str] = mapped_column(String(64), nullable=False, default="match_default")
    model_package_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_package_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    package_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    weights_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decoder_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sync_calibration_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timing_authority: Mapped[str | None] = mapped_column(String(32), nullable=True)
    artifact_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    artifact_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    window_plan_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    unknown_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    segment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    diagnostics_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    plan_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    supersedes_run_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
