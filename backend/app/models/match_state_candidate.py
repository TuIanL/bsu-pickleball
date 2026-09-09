"""Durable provenance and review records for learned match-state candidates."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MatchStateCandidateArtifact(Base):
    __tablename__ = "match_state_candidate_artifacts"
    __table_args__ = (UniqueConstraint("capture_take_id", "artifact_version", name="uq_candidate_artifact_version"),)

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    capture_take_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("capture_takes.id", ondelete="RESTRICT"), nullable=False
    )
    artifact_version: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(UTC))


class MatchStateCandidateReview(Base):
    __tablename__ = "match_state_candidate_reviews"
    __table_args__ = (Index("idx_candidate_review_take_version", "capture_take_id", "artifact_version"),)

    capture_take_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("capture_takes.id", ondelete="RESTRICT"), primary_key=True
    )
    artifact_version: Mapped[str] = mapped_column(String(64), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(UTC))


class MatchStateCandidateDecision(Base):
    __tablename__ = "match_state_candidate_decisions"
    __table_args__ = (
        UniqueConstraint("request_id", name="uq_candidate_decision_request"),
        UniqueConstraint("capture_take_id", "artifact_version", "candidate_id", name="uq_candidate_decision_candidate"),
        Index("idx_candidate_decision_take_version", "capture_take_id", "artifact_version"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    capture_take_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("capture_takes.id", ondelete="RESTRICT"), nullable=False
    )
    artifact_version: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate_id: Mapped[str] = mapped_column(String(128), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    expected_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    original_start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    original_end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    reviewed_start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    reviewed_end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    operation_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    output_segment_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    provenance_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    request_payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
