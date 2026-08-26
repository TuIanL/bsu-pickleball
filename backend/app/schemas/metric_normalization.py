"""Metric normalization and scoring-reference contracts.

This module deliberately stops before dimension or overall scoring.  It turns
the descriptive ``metric-snapshot.v1`` artifact into an auditable intermediate
artifact with explicit value semantics and score eligibility.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.shot_rally_events import ArtifactStatus, MetricScope

MetricDirection = Literal[
    "higher_better",
    "lower_better",
    "target_range",
    "context_dependent",
    "descriptive_only",
]
ReferenceMode = Literal["expert_threshold", "target_range", "empirical_percentile"]
ScoreEligibility = Literal[
    "eligible",
    "display_only",
    "insufficient_evidence",
    "not_applicable",
    "unsupported",
    "failed",
]
MatchFormat = Literal["singles", "doubles"]
SemanticLevel = Literal["descriptive", "derived", "confirmed", "candidate"]


class MetricDefinition(BaseModel):
    """Definition of one metric that the normalization layer is allowed to see."""

    metric_key: str
    unit: str
    source_metric_key: str
    scopes: list[MetricScope] = Field(min_length=1)
    match_formats: list[MatchFormat] = Field(default_factory=lambda: ["singles", "doubles"])
    metric_direction: MetricDirection
    descriptive_only: bool = False
    required_semantic_level: SemanticLevel = "descriptive"
    min_sample_count: int = Field(default=1, ge=0)
    min_denominator: int | None = Field(default=None, ge=0)
    context_keys: list[str] = Field(default_factory=list)
    definition_detail: str | None = None

    @model_validator(mode="after")
    def validate_definition(self) -> MetricDefinition:
        if self.metric_direction == "descriptive_only" and not self.descriptive_only:
            raise ValueError("descriptive_only direction requires descriptive_only=true")
        if self.metric_direction != "descriptive_only" and self.descriptive_only:
            raise ValueError("descriptive_only=true requires descriptive_only direction")
        if self.metric_direction == "context_dependent" and not self.context_keys:
            raise ValueError("context_dependent metrics require context_keys")
        if not self.match_formats:
            raise ValueError("metric definition must declare at least one match format")
        return self


class MetricDefinitionProfile(BaseModel):
    schema_version: Literal["metric-definition-profile.v1"] = "metric-definition-profile.v1"
    profile_version: str = "metric-definition-profile.v1"
    metrics: list[MetricDefinition] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_metrics(self) -> MetricDefinitionProfile:
        keys = [item.metric_key for item in self.metrics]
        if len(keys) != len(set(keys)):
            raise ValueError("metric_key must be unique in MetricDefinitionProfile")
        return self

    def by_key(self) -> dict[str, MetricDefinition]:
        return {item.metric_key: item for item in self.metrics}


class SufficiencyRule(BaseModel):
    min_sample_count: int = Field(default=1, ge=0)
    min_denominator: int | None = Field(default=None, ge=0)
    min_coverage: float | None = Field(default=None, ge=0, le=1)
    zero_denominator_status: Literal["not_applicable", "insufficient_evidence"] = "not_applicable"


class EvidenceSufficiencyProfile(BaseModel):
    schema_version: Literal["evidence-sufficiency-profile.v1"] = "evidence-sufficiency-profile.v1"
    profile_version: str = "evidence-sufficiency-profile.v1"
    default_rule: SufficiencyRule = Field(default_factory=SufficiencyRule)
    rules: dict[str, SufficiencyRule] = Field(default_factory=dict)

    def rule_for(self, metric_key: str) -> SufficiencyRule:
        return self.rules.get(metric_key, self.default_rule)


class MetricReference(BaseModel):
    metric_key: str
    reference_mode: ReferenceMode
    metric_direction: MetricDirection
    reference_source: str
    reference_detail: str
    lower_bound: float | None = None
    upper_bound: float | None = None
    target_min: float | None = None
    target_max: float | None = None
    context_selector: dict[str, str] = Field(default_factory=dict)
    population: str | None = None
    cohort: str | None = None
    population_sample_count: int | None = Field(default=None, ge=0)
    reference_distribution: list[float] = Field(default_factory=list)
    fallback: Literal["none", "display_only", "unsupported"] = "unsupported"

    @model_validator(mode="after")
    def validate_reference(self) -> MetricReference:
        if self.metric_direction == "descriptive_only":
            raise ValueError("descriptive_only metrics cannot have a scoring reference")
        if self.reference_mode in {"expert_threshold", "empirical_percentile"}:
            if self.lower_bound is not None and self.upper_bound is not None and self.lower_bound >= self.upper_bound:
                raise ValueError("lower_bound must be less than upper_bound")
        if self.reference_mode == "target_range":
            if self.target_min is None or self.target_max is None:
                raise ValueError("target_range reference requires target_min and target_max")
            if self.target_min > self.target_max:
                raise ValueError("target_min must be less than or equal to target_max")
            if self.lower_bound is not None and self.lower_bound > self.target_min:
                raise ValueError("lower_bound must not exceed target_min")
            if self.upper_bound is not None and self.upper_bound < self.target_max:
                raise ValueError("upper_bound must not be below target_max")
        if self.reference_mode == "empirical_percentile":
            if self.population_sample_count is not None and self.population_sample_count < len(
                self.reference_distribution
            ):
                raise ValueError("population_sample_count cannot be below distribution sample count")
        if self.metric_direction == "context_dependent" and not self.context_selector:
            raise ValueError("context_dependent reference requires context_selector")
        return self


class ScoringReferenceProfile(BaseModel):
    schema_version: Literal["scoring-reference-profile.v1"] = "scoring-reference-profile.v1"
    reference_version: str = "scoring-reference-profile.v1"
    reference_mode: ReferenceMode
    reference_source: str
    reference_detail: str
    metrics: list[MetricReference] = Field(default_factory=list)
    generated_at: str | None = None

    @model_validator(mode="after")
    def validate_unique_references(self) -> ScoringReferenceProfile:
        keys = [item.metric_key for item in self.metrics]
        if len(keys) != len(set(keys)):
            raise ValueError("metric_key must be unique in ScoringReferenceProfile")
        return self

    def by_key(self) -> dict[str, MetricReference]:
        return {item.metric_key: item for item in self.metrics}


class NormalizedMetricEntry(BaseModel):
    metric_id: str
    source_metric_id: str
    metric_key: str
    scope: MetricScope
    subject_id: str
    source_status: ArtifactStatus
    raw_value: float | int | None = None
    canonical_value: float | int | None = None
    unit: str
    metric_direction: MetricDirection
    reference_mode: ReferenceMode | None = None
    utility_score: float | None = Field(default=None, ge=0, le=1)
    percentile: float | None = Field(default=None, ge=0, le=100)
    numerator: float | int | None = Field(default=None, ge=0)
    denominator: float | int | None = Field(default=None, ge=0)
    sample_count: int = Field(default=0, ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)
    score_eligibility: ScoreEligibility
    eligibility_reasons: list[str] = Field(default_factory=list)
    provenance: str
    source_artifact: str
    evidence_ids: list[str] = Field(default_factory=list)
    definition_version: str
    evidence_sufficiency_version: str
    reference_version: str | None = None
    calculation_version: str = "metric-normalization.v1"

    @model_validator(mode="after")
    def validate_entry_semantics(self) -> NormalizedMetricEntry:
        if self.score_eligibility == "eligible" and self.utility_score is None:
            raise ValueError("eligible normalized metric requires utility_score")
        if self.score_eligibility != "eligible" and self.utility_score is not None:
            raise ValueError("non-eligible normalized metric cannot expose utility_score")
        if self.numerator is not None and self.denominator is not None and self.numerator > self.denominator:
            raise ValueError("numerator cannot be greater than denominator")
        if self.source_status == "available" and self.raw_value is None and self.score_eligibility == "eligible":
            raise ValueError("eligible metric requires raw_value")
        return self


class NormalizedMetricCoverage(BaseModel):
    metric_count: int = Field(default=0, ge=0)
    eligible_metric_count: int = Field(default=0, ge=0)
    display_only_metric_count: int = Field(default=0, ge=0)
    insufficient_metric_count: int = Field(default=0, ge=0)
    not_applicable_metric_count: int = Field(default=0, ge=0)
    unsupported_metric_count: int = Field(default=0, ge=0)
    failed_metric_count: int = Field(default=0, ge=0)
    eligible_metric_keys: list[str] = Field(default_factory=list)
    missing_metric_keys: list[str] = Field(default_factory=list)


class NormalizedMetricArtifact(BaseModel):
    schema_version: Literal["normalized-metric-snapshot.v1"] = "normalized-metric-snapshot.v1"
    job_id: str
    video_id: str | None = None
    status: ArtifactStatus
    detail: str
    generated_at: str
    input_artifact: Literal["metric-snapshot.v1"] = "metric-snapshot.v1"
    metric_definition_version: str
    evidence_sufficiency_version: str
    scoring_reference_version: str | None = None
    scoring_reference_hash: str | None = None
    metrics: list[NormalizedMetricEntry] = Field(default_factory=list)
    score_coverage: NormalizedMetricCoverage = Field(default_factory=NormalizedMetricCoverage)
    diagnostics: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> NormalizedMetricArtifact:
        ids = [metric.metric_id for metric in self.metrics]
        if len(ids) != len(set(ids)):
            raise ValueError("metric_id must be unique within a normalized artifact")
        return self


class MetricNormalizationContext(BaseModel):
    """Runtime context used to select definitions and context-dependent references."""

    match_format: MatchFormat | None = None
    role: str | None = None
    stage: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
