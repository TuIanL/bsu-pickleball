"""厨房线到位产物契约（kitchen-arrival.v1）。

该契约只描述“发球队在该回合是否曾经稳定到达己方厨房线”的原始事实，
不把结果解释为技术评分，也不使用可变的当前发球队状态。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.shot_rally_events import ArtifactStatus

KitchenArrivalState = Literal["already_present", "arrived", "not_arrived", "excluded"]


class KitchenArrivalReference(BaseModel):
    schema_version: Literal["kitchen-arrival-reference.v1"] = "kitchen-arrival-reference.v1"
    arrival_band_m: float = Field(gt=0)
    stable_ms: int = Field(gt=0)
    arrival_min_detected_support_ms: int = Field(gt=0)
    not_arrived_min_coverage_ratio: float = Field(gt=0, le=1)
    not_arrived_max_gap_ms: int = Field(gt=0)
    min_sample_count: int = Field(gt=0)
    calibration_status: Literal["locked_reference", "requires_calibration"] = "locked_reference"
    provenance: dict[str, Any] = Field(default_factory=dict)


class KitchenArrivalRallyResult(BaseModel):
    rally_id: str
    ordinal: int = Field(ge=1)
    player_id: str
    display_name: str | None = None
    team_id: Literal["A", "B"]
    server_team: Literal["A", "B"]
    state: KitchenArrivalState
    eligible: bool
    already_present: bool = False
    arrived: bool = False
    arrival_time_ms: int | None = Field(default=None, ge=0)
    coverage_ratio: float | None = Field(default=None, ge=0, le=1)
    max_gap_ms: int | None = Field(default=None, ge=0)
    detected_support_ms: int = Field(default=0, ge=0)
    excluded_reason: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


class KitchenArrivalPlayerResult(BaseModel):
    player_id: str
    display_name: str | None = None
    team_id: Literal["A", "B"]
    arrived_count: int = Field(default=0, ge=0)
    eligible_count: int = Field(default=0, ge=0)
    sample_count: int = Field(default=0, ge=0)
    excluded_count: int = Field(default=0, ge=0)
    arrival_rate: float | None = Field(default=None, ge=0, le=1)
    status: ArtifactStatus
    reason: str | None = None
    rally_ids: list[str] = Field(default_factory=list)


class KitchenArrivalDiagnostics(BaseModel):
    total_rallies: int = Field(default=0, ge=0)
    eligible_samples: int = Field(default=0, ge=0)
    excluded_samples: int = Field(default=0, ge=0)
    excluded_reasons: dict[str, int] = Field(default_factory=dict)
    coverage_ratios: dict[str, float] = Field(default_factory=dict)
    max_gaps_ms: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class KitchenArrivalArtifact(BaseModel):
    schema_version: Literal["kitchen-arrival.v1"] = "kitchen-arrival.v1"
    job_id: str
    video_id: str | None = None
    status: ArtifactStatus
    detail: str
    generated_at: str
    aggregation_scope: Literal["match", "formal_rally_batch"] = "formal_rally_batch"
    reference: KitchenArrivalReference
    players: list[KitchenArrivalPlayerResult] = Field(default_factory=list)
    rallies: list[KitchenArrivalRallyResult] = Field(default_factory=list)
    diagnostics: KitchenArrivalDiagnostics = Field(default_factory=KitchenArrivalDiagnostics)
    source_artifacts: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
