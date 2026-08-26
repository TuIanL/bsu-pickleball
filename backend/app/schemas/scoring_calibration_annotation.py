"""评分校准人工标注契约。"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


SCORING_CALIBRATION_SCHEMA_VERSION = "scoring-calibration-annotation.v1"


class AnnotationPackageStatus(str, Enum):
    draft = "draft"
    reviewed = "reviewed"
    locked = "locked"


class AnnotationSource(str, Enum):
    manual = "manual"
    algorithm = "algorithm"


class AnnotationDecision(str, Enum):
    accepted = "accepted"
    corrected = "corrected"
    rejected = "rejected"
    unreviewed = "unreviewed"


class ShotStage(str, Enum):
    serve = "serve"
    return_ = "return"
    other = "other"
    unknown = "unknown"


class OpportunityStatus(str, Enum):
    eligible = "eligible"
    not_applicable = "not_applicable"
    unobservable = "unobservable"


class ShotOutcome(str, Enum):
    in_play = "in_play"
    net = "net"
    out = "out"
    unknown = "unknown"


class LandingStatus(str, Enum):
    measured = "measured"
    not_applicable = "not_applicable"
    unobservable = "unobservable"


class LandingZone(str, Enum):
    short = "short"
    middle = "middle"
    deep = "deep"
    unknown = "unknown"


class AnnotationCandidate(BaseModel):
    model_config = ConfigDict(extra="allow")

    candidate_id: str
    candidate_type: str = "shot"
    source: str = "algorithm"
    source_job_id: str | None = None
    timestamp_ms: int = Field(ge=0)
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)
    player_id: str | None = None
    rally_id: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    artifact_name: str | None = None
    detector_version: str | None = None
    coverage_warning: str | None = None
    coverage: dict[str, Any] = Field(default_factory=dict)
    decision: AnnotationDecision = AnnotationDecision.unreviewed
    annotation_id: str | None = None


class AnnotationPackageCreateRequest(BaseModel):
    annotator: str | None = None
    note: str | None = None
    source_job_id: str | None = None


class AnnotationPackageRevisionRequest(BaseModel):
    annotator: str | None = None
    note: str | None = None


class AnnotationUpsertRequest(BaseModel):
    event_ms: int = Field(ge=0)
    evidence_start_ms: int = Field(ge=0)
    evidence_end_ms: int = Field(ge=0)
    video_id: str | None = None
    rally_segment_id: str | None = None
    player_id: str | None = None
    stage: ShotStage | None = None
    opportunity_status: OpportunityStatus | None = None
    outcome: ShotOutcome | None = None
    landing_status: LandingStatus | None = None
    landing_zone: LandingZone | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    note: str | None = None
    candidate_id: str | None = None
    decision: AnnotationDecision = AnnotationDecision.unreviewed


class AnnotationUpdateRequest(BaseModel):
    event_ms: int | None = Field(default=None, ge=0)
    evidence_start_ms: int | None = Field(default=None, ge=0)
    evidence_end_ms: int | None = Field(default=None, ge=0)
    video_id: str | None = None
    rally_segment_id: str | None = None
    player_id: str | None = None
    stage: ShotStage | None = None
    opportunity_status: OpportunityStatus | None = None
    outcome: ShotOutcome | None = None
    landing_status: LandingStatus | None = None
    landing_zone: LandingZone | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    note: str | None = None
    candidate_id: str | None = None
    decision: AnnotationDecision | None = None


class CandidateDecisionRequest(BaseModel):
    decision: AnnotationDecision
    annotation_id: str | None = None


class ValidationIssue(BaseModel):
    code: str
    message: str
    annotation_id: str | None = None
    severity: str = "error"


class QualitySummary(BaseModel):
    total_count: int = 0
    confirmed_count: int = 0
    unknown_or_unobservable_count: int = 0
    unmatched_candidate_count: int = 0
    conflict_count: int = 0
    evidence_complete_rate: float = 0
    blocking_error_count: int = 0
    warning_count: int = 0


class AnnotationRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    package_revision_id: str
    source: AnnotationSource
    candidate_id: str | None = None
    event_ms: int
    evidence_start_ms: int
    evidence_end_ms: int
    video_id: str | None = None
    rally_segment_id: str | None = None
    player_id: str | None = None
    stage: ShotStage | None = None
    opportunity_status: OpportunityStatus | None = None
    outcome: ShotOutcome | None = None
    landing_status: LandingStatus | None = None
    landing_zone: LandingZone | None = None
    confidence: float | None = None
    note: str | None = None
    decision: AnnotationDecision = AnnotationDecision.unreviewed
    revoked: bool = False
    created_at: datetime
    updated_at: datetime


class AnnotationPackageSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    package_id: str
    capture_take_id: str
    revision: int
    schema_version: str
    status: AnnotationPackageStatus
    annotator: str | None = None
    note: str | None = None
    source_job_id: str | None = None
    supersedes_id: str | None = None
    quality: QualitySummary
    validation_issues: list[ValidationIssue] = Field(default_factory=list)
    annotations: list[AnnotationRecord] = Field(default_factory=list)
    candidates: list[AnnotationCandidate] = Field(default_factory=list)
    candidate_status: str = "unavailable"
    candidate_message: str | None = None
    candidate_coverage_warning: str | None = None
    created_at: datetime
    updated_at: datetime
    locked_at: datetime | None = None


class GoldSetResponse(BaseModel):
    schema_version: str
    package_id: str
    revision: int
    capture_take_id: str
    status: AnnotationPackageStatus
    provenance: dict[str, Any]
    annotations: list[AnnotationRecord]
    quality: QualitySummary


def annotation_semantic_issues(annotation: AnnotationUpsertRequest | AnnotationRecord) -> list[ValidationIssue]:
    """返回跨字段语义问题；draft 可保存，locked 时由服务层阻止。"""

    issues: list[ValidationIssue] = []
    annotation_id = getattr(annotation, "id", None)
    opportunity = annotation.opportunity_status
    outcome = annotation.outcome
    landing_status = annotation.landing_status
    landing_zone = annotation.landing_zone

    if opportunity == OpportunityStatus.not_applicable and outcome not in (None, ShotOutcome.unknown):
        issues.append(ValidationIssue(code="not_applicable_outcome", message="not_applicable 机会不得填写具体击球结果", annotation_id=annotation_id))
    if opportunity == OpportunityStatus.unobservable and outcome not in (None, ShotOutcome.unknown):
        issues.append(ValidationIssue(code="unobservable_outcome", message="unobservable 机会不得填写确定的击球结果", annotation_id=annotation_id))
    if landing_status == LandingStatus.measured and landing_zone is None:
        issues.append(ValidationIssue(code="missing_landing_zone", message="已测量落点必须选择落点区域", annotation_id=annotation_id))
    if landing_status in (LandingStatus.not_applicable, LandingStatus.unobservable) and landing_zone not in (None, LandingZone.unknown):
        issues.append(ValidationIssue(code="invalid_landing_zone", message="不可测落点不得填写具体落点区域", annotation_id=annotation_id))
    if outcome in (ShotOutcome.net, ShotOutcome.out) and landing_status == LandingStatus.measured:
        issues.append(ValidationIssue(code="failed_shot_landing", message="下网或出界击球不得作为已测量有效落点", annotation_id=annotation_id))
    return issues
