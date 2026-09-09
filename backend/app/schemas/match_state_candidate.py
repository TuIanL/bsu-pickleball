"""Learned match-state candidate review API schemas."""

from __future__ import annotations

from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

CANDIDATE_REVIEW_SCHEMA_VERSION = "match-state-candidate-review.v1"


class CandidateDecision(StrEnum):
    accepted = "accepted"
    corrected = "corrected"
    rejected = "rejected"


class MatchStateCandidateDecisionRequest(BaseModel):
    decision: CandidateDecision
    expected_revision: int
    artifact_version: str | None = None
    request_id: str = Field(default_factory=lambda: f"candidate-review-{uuid4().hex}", min_length=8, max_length=128)
    start_ms: int | None = None
    end_ms: int | None = None
    note: str | None = None

    @model_validator(mode="after")
    def validate_boundary(self) -> MatchStateCandidateDecisionRequest:
        if self.expected_revision < 0:
            raise ValueError("expected_revision 不能为负数")
        if self.decision == CandidateDecision.corrected:
            if self.start_ms is None or self.end_ms is None:
                raise ValueError("修正候选必须同时提交 start_ms 和 end_ms")
        return self
