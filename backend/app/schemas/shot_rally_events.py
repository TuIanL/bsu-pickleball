"""Canonical Rally/Shot 事件与 Metric Snapshot 契约。

这一层只承载可追溯事实和描述性聚合，不承载未经校准的技能评分。
事件来源由既有 reconstructed_ball_trajectory、serve events 和 timeline
产物组合而来；缺失字段保持为空并通过 status/detail 表达原因。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

ArtifactStatus = Literal[
    "available",
    "skipped",
    "insufficient_evidence",
    "not_applicable",
    "unavailable",
    "failed",
]
OwnershipStatus = Literal["confirmed", "ambiguous", "unassigned", "not_applicable"]
QualityBand = Literal["high", "medium", "low", "none"]
MetricScope = Literal["match", "team", "player"]


# 首版只提供门槛配置，不把门槛解释为技能评分校准。
PRODUCT_REFERENCE_V1: dict[str, int] = {
    "min_rallies": 3,
    "min_shots": 8,
    "min_serve_opportunities": 3,
    "min_quality_samples": 3,
}

METRIC_DICTIONARY_V1: dict[str, dict[str, Any]] = {
    "shot_count": {"unit": "count", "scopes": ["match", "team", "player"], "denominator": "shot_events"},
    "rally_count": {"unit": "count", "scopes": ["match"], "denominator": "rally_events"},
    "serve_count": {"unit": "count", "scopes": ["match", "team", "player"], "denominator": "serve_events"},
    "return_count": {"unit": "count", "scopes": ["match", "team", "player"], "denominator": "return_events"},
    "third_shot_count": {"unit": "count", "scopes": ["match", "team", "player"], "denominator": "third_shot_events"},
    "shot_quality_mean": {"unit": "ratio", "scopes": ["match", "player"], "denominator": "quality_scored_shots"},
    "doubles_cooperation": {"unit": "ratio", "scopes": ["match", "team"], "denominator": "doubles_team_events"},
}


class EvidenceWindow(BaseModel):
    """可回跳视频的毫秒时间窗。"""

    id: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    source_artifact: str
    detail: str | None = None

    @model_validator(mode="after")
    def validate_order(self) -> EvidenceWindow:
        if self.end_ms < self.start_ms:
            raise ValueError("end_ms must be greater than or equal to start_ms")
        return self


class CanonicalPlayer(BaseModel):
    player_id: str
    render_slot: str | None = None
    initial_side: Literal["near", "far", "unknown"] | None = None

    @field_validator("player_id")
    @classmethod
    def validate_player_id(cls, value: str) -> str:
        if not value.startswith("Player_") or not value[len("Player_"):].isdigit():
            raise ValueError("player_id must be canonical Player_N")
        return value


class ShotQuality(BaseModel):
    score: float | None = Field(default=None, ge=0, le=1)
    band: QualityBand = "none"
    reasons: list[str] = Field(default_factory=list)


class ShotTrajectorySummary(BaseModel):
    available: bool = False
    source: str | None = None
    segment_ids: list[str] = Field(default_factory=list)
    sample_count: int = Field(default=0, ge=0)
    path_distance_ft: float | None = Field(default=None, ge=0)


class ShotSpatialSummary(BaseModel):
    coordinate_system: Literal["court_ft", "image_px"]
    start_xy: list[float] | None = Field(default=None, min_length=2, max_length=2)
    end_xy: list[float] | None = Field(default=None, min_length=2, max_length=2)


class ShotEvent(BaseModel):
    """一个去重后的 canonical Shot 事实。"""

    shot_id: str
    rally_id: str | None = None
    ordinal_in_rally: int | None = Field(default=None, ge=1)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    contact_ms: int | None = Field(default=None, ge=0)
    hitter_player_id: str | None = None
    team_id: str | None = None
    ownership_status: OwnershipStatus = "unassigned"
    ownership_confidence: float | None = Field(default=None, ge=0, le=1)
    ownership_source: str | None = None
    stage: Literal["serve", "return", "third", "rally_shot"] | None = None
    shot_type: str | None = None
    stroke_type: str | None = None
    is_volley: bool | None = None
    result: str | None = None
    error_type: str | None = None
    quality: ShotQuality = Field(default_factory=ShotQuality)
    trajectory: ShotTrajectorySummary = Field(default_factory=ShotTrajectorySummary)
    spatial: ShotSpatialSummary | None = None
    evidence_windows: list[EvidenceWindow] = Field(default_factory=list)
    source_event_id: str | None = None
    source_artifacts: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    diagnostics: list[str] = Field(default_factory=list)

    @field_validator("hitter_player_id")
    @classmethod
    def validate_hitter_player_id(cls, value: str | None) -> str | None:
        if value is not None and (not value.startswith("Player_") or not value[len("Player_"):].isdigit()):
            raise ValueError("hitter_player_id must be canonical Player_N")
        return value

    @model_validator(mode="after")
    def validate_time_window(self) -> ShotEvent:
        if self.end_ms < self.start_ms:
            raise ValueError("end_ms must be greater than or equal to start_ms")
        if self.ownership_status == "confirmed" and self.hitter_player_id is None:
            raise ValueError("confirmed shot ownership requires hitter_player_id")
        if self.ordinal_in_rally is None and self.stage in {"return", "third", "rally_shot"}:
            raise ValueError("non-serve stage requires ordinal_in_rally")
        return self


class RallyEvent(BaseModel):
    rally_id: str
    ordinal: int = Field(ge=1)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    shot_ids: list[str] = Field(default_factory=list)
    source_artifacts: list[str] = Field(default_factory=list)
    provenance: str
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence_windows: list[EvidenceWindow] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_time_window(self) -> RallyEvent:
        if self.end_ms < self.start_ms:
            raise ValueError("end_ms must be greater than or equal to start_ms")
        return self


class ShotRallyDiagnostics(BaseModel):
    duplicate_shot_ids: list[str] = Field(default_factory=list)
    missing_shot_ids: list[str] = Field(default_factory=list)
    unassigned_shot_count: int = Field(default=0, ge=0)
    ambiguous_shot_count: int = Field(default=0, ge=0)
    rally_boundary_status: Literal["available", "unavailable"] = "unavailable"
    warnings: list[str] = Field(default_factory=list)


class ShotRallyEventsArtifact(BaseModel):
    schema_version: Literal["shot-rally-events.v1"] = "shot-rally-events.v1"
    job_id: str
    video_id: str | None = None
    status: ArtifactStatus
    detail: str
    generated_at: str
    time_unit: Literal["ms"] = "ms"
    coordinate_system: dict[str, str] = Field(
        default_factory=lambda: {"court": "ft", "image": "px", "origin": "court_corner"}
    )
    players: list[CanonicalPlayer] = Field(default_factory=list)
    rallies: list[RallyEvent] = Field(default_factory=list)
    shots: list[ShotEvent] = Field(default_factory=list)
    diagnostics: ShotRallyDiagnostics = Field(default_factory=ShotRallyDiagnostics)
    source_artifacts: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> ShotRallyEventsArtifact:
        ids = [shot.shot_id for shot in self.shots]
        if len(ids) != len(set(ids)):
            raise ValueError("shot_id must be unique within a job")
        return self


class MetricSnapshotEntry(BaseModel):
    metric_id: str
    metric_key: str
    scope: MetricScope
    subject_id: str
    value: float | int | None = None
    unit: str
    numerator: float | int | None = Field(default=None, ge=0)
    denominator: float | int | None = Field(default=None, ge=0)
    sample_count: int = Field(default=0, ge=0)
    status: ArtifactStatus
    reason: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    provenance: str
    evidence_ids: list[str] = Field(default_factory=list)
    calculation_version: Literal["product_reference_v1"] = "product_reference_v1"

    @model_validator(mode="after")
    def validate_status_value(self) -> MetricSnapshotEntry:
        if self.status == "available" and self.value is None:
            raise ValueError("available metric requires value")
        if self.status != "available" and self.value is not None:
            raise ValueError("non-available metric must have null value")
        if self.numerator is not None and self.denominator is not None and self.numerator > self.denominator:
            raise ValueError("numerator cannot be greater than denominator")
        return self


class MetricSnapshotArtifact(BaseModel):
    schema_version: Literal["metric-snapshot.v1"] = "metric-snapshot.v1"
    job_id: str
    video_id: str | None = None
    status: ArtifactStatus
    detail: str
    generated_at: str
    product_reference_version: Literal["product_reference_v1"] = "product_reference_v1"
    thresholds: dict[str, int] = Field(default_factory=lambda: dict(PRODUCT_REFERENCE_V1))
    metrics: list[MetricSnapshotEntry] = Field(default_factory=list)
    source_artifact: str = "shot-rally-events.v1"

    @model_validator(mode="after")
    def validate_unique_metric_ids(self) -> MetricSnapshotArtifact:
        ids = [metric.metric_id for metric in self.metrics]
        if len(ids) != len(set(ids)):
            raise ValueError("metric_id must be unique within a snapshot")
        return self
