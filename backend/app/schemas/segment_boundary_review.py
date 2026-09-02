"""有效回合边界人工复核契约。"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator


BOUNDARY_REVIEW_SCHEMA_VERSION = "match-state-boundary-review.v1"


class BoundaryReviewDecision(str, Enum):
    confirmed = "confirmed"
    corrected = "corrected"
    excluded = "excluded"


class BoundaryReviewRequest(BaseModel):
    decision: BoundaryReviewDecision
    expected_version: int = Field(ge=0)
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_boundaries(self):
        if self.decision == BoundaryReviewDecision.corrected:
            if self.start_ms is None or self.end_ms is None:
                raise ValueError("修正边界时必须同时提交 start_ms 和 end_ms")
        return self
