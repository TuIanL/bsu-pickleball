"""评分校准标注包、人工事实和算法候选决定的持久化模型。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ScoringCalibrationPackage(Base):
    __tablename__ = "scoring_calibration_packages"
    __table_args__ = (
        UniqueConstraint("package_id", "revision", name="uq_scoring_calibration_package_revision"),
        Index("idx_scoring_calibration_take_status", "capture_take_id", "status", "revision"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    package_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    capture_take_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("capture_takes.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(96), nullable=False, default="scoring-calibration-annotation.v1")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", index=True)
    annotator: Mapped[str | None] = mapped_column(String(120), nullable=True)
    note: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    source_job_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    source_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    quality_summary_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    validation_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    artifact_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    supersedes_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("scoring_calibration_packages.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )


class ScoringCalibrationAnnotation(Base):
    __tablename__ = "scoring_calibration_annotations"
    __table_args__ = (
        Index("idx_scoring_calibration_annotation_package_time", "package_revision_id", "event_ms"),
        Index("idx_scoring_calibration_annotation_candidate", "package_revision_id", "candidate_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    package_revision_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("scoring_calibration_packages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")
    candidate_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    event_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    video_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    rally_segment_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    player_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    opportunity_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    landing_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    landing_zone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision: Mapped[str] = mapped_column(String(16), nullable=False, default="unreviewed")
    revoked: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )


class ScoringCalibrationCandidateDecision(Base):
    __tablename__ = "scoring_calibration_candidate_decisions"
    __table_args__ = (
        UniqueConstraint("package_revision_id", "candidate_id", name="uq_scoring_calibration_candidate_decision"),
        Index("idx_scoring_calibration_candidate_decision_package", "package_revision_id", "decision"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    package_revision_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("scoring_calibration_packages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    candidate_id: Mapped[str] = mapped_column(String(128), nullable=False)
    candidate_type: Mapped[str] = mapped_column(String(32), nullable=False, default="shot")
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="algorithm")
    source_job_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    candidate_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    decision: Mapped[str] = mapped_column(String(16), nullable=False, default="unreviewed")
    annotation_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )
