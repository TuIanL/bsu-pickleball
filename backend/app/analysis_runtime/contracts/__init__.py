"""可独立导入的版本化合同，不依赖视觉或 Worker。"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

NodeStatus = Literal["pending", "running", "cached", "completed", "failed", "blocked", "canceled", "skipped"]
Availability = Literal["available", "location_unavailable", "missing", "corrupt"]
Quality = Literal["sufficient", "insufficient_evidence", "truncated", "no_candidates"]
FailurePolicy = Literal["all_targets", "best_effort"]
Selector = Literal["sample_time.v1", "contact_time.v1", "interval_intersects.v1"]


def now() -> str:
    return datetime.now(UTC).isoformat()


class Contract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Window(Contract):
    start_ms: int
    end_ms: int

    @model_validator(mode="after")
    def positive_range(self):
        if self.end_ms <= self.start_ms:
            raise ValueError("window must have positive duration")
        return self


class Sampling(Contract):
    stride: int = Field(default=1, ge=1)
    phase: int = Field(default=0, ge=0)
    anchor: Literal["source_frame_0", "window_start"] = "source_frame_0"
    initialization: Literal["window_reset"] = "window_reset"

    @model_validator(mode="after")
    def valid_phase(self):
        if self.phase >= self.stride:
            raise ValueError("sampling phase must be smaller than stride")
        return self


class ContextBudget(Contract):
    before_ms: int = Field(default=2000, ge=0)
    after_ms: int = Field(default=2000, ge=0)


class ArtifactRef(Contract):
    artifact_id: str
    artifact_type: str
    schema_version: str = "1"


class InputSpec(Contract):
    name: str
    capability_id: str
    artifact_type: str
    schema_version: str = "1"
    required: bool = True


class ImplementationSpec(Contract):
    implementation_id: str
    capability_id: str
    version: str = "1"
    output_type: str
    output_schema: str = "1"
    coordinate_system: Literal["image_px", "normalized_image", "court_m", "world_3d"] = "image_px"
    units: str = "px"
    inputs: tuple[InputSpec, ...] = ()
    parameter_defaults: dict[str, Any] = Field(default_factory=dict)
    parameter_schema: dict[str, Any] = Field(default_factory=dict)
    output_required_fields: tuple[str, ...] = ("observations",)
    consumed_context: tuple[str, ...] = ("media", "frame_time")
    pre_roll_ms: int = Field(default=0, ge=0)
    post_roll_ms: int = Field(default=0, ge=0)
    selector: Selector = "sample_time.v1"
    resources: tuple[str, ...] = ("decode",)
    secondary_failure_policy: Literal["fail", "degrade"] = "fail"
    progress_weight: float = Field(default=1.0, gt=0, allow_inf_nan=False)
    max_retries: int = Field(default=0, ge=0, le=3)
    taxonomy_version: str | None = None


class CapabilitySpec(Contract):
    capability_id: str
    contract_version: str = "1"
    status: Literal["planned", "implemented"] = "planned"
    implementations: tuple[str, ...] = ()
    output_types: tuple[str, ...] = ()
    schema_path: str | None = None


class ModelAsset(Contract):
    path: str
    sha256: str


class ModelSnapshot(Contract):
    implementation_id: str
    assets: dict[str, ModelAsset] = Field(default_factory=dict)
    configuration: dict[str, Any] = Field(default_factory=dict)


class SourceSnapshot(Contract):
    source_id: str
    video_id: str | None = None
    view_id: str
    camera_id: str
    media_path: str
    media_sha256: str
    sidecar_path: str | None = None
    sidecar_sha256: str | None = None
    timing_path: str
    timing_sha256: str
    timing_authority: Literal["source_pts", "legacy_nominal_fps"]
    frame_count: int = Field(ge=1)
    fps: float = Field(gt=0)
    duration_ms: int = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class CalibrationContext(Contract):
    calibration_id: str
    revision: str
    valid_window: Window
    view_ids: tuple[str, ...]
    coordinate_system: Literal["court_m", "world_3d"]
    units: Literal["m"] = "m"
    transform: dict[str, Any] = Field(default_factory=dict)


class ContextSnapshot(Contract):
    values: dict[str, Any] = Field(default_factory=dict)

    def project(self, fields: tuple[str, ...]) -> dict[str, Any]:
        return {key: self.values[key] for key in sorted(fields) if key in self.values}


class SourceBinding(Contract):
    take_id: str
    sync_revision: int = Field(ge=0)
    provenance_fingerprint: str


class AnalysisRequest(Contract):
    source_binding: SourceBinding | None = None
    source_ids: tuple[str, ...] = Field(min_length=1, max_length=2)
    targets: tuple[str, ...] = Field(min_length=1)
    window: Window
    sampling: Sampling = Field(default_factory=Sampling)
    context_budget: ContextBudget = Field(default_factory=ContextBudget)
    failure_policy: FailurePolicy = "all_targets"
    implementations: dict[str, str] = Field(default_factory=dict)
    parameters: dict[str, dict[str, Any]] = Field(default_factory=dict)
    fixed_inputs: dict[str, ArtifactRef] = Field(default_factory=dict)
    optional_inputs: tuple[str, ...] = ()
    context: ContextSnapshot = Field(default_factory=ContextSnapshot)
    sync: dict[str, Any] | None = None
    reference_view_id: str | None = None
    new_version: bool = False

    @model_validator(mode="after")
    def local_request(self):
        if self.window.start_ms < 0:
            raise ValueError("requested window must be nonnegative")
        if len(set(self.targets)) != len(self.targets):
            raise ValueError("duplicate targets")
        return self


class PlanNode(Contract):
    node_key: str
    capability_id: str
    capability_version: str
    implementation: ImplementationSpec
    parameters: dict[str, Any]
    model: ModelSnapshot
    inputs: dict[str, str | ArtifactRef]
    required_inputs: tuple[str, ...]
    missing_optional: tuple[str, ...] = ()
    compute_window: Window
    effective_window: Window
    output_window: Window
    output_selector: Selector
    consumed_context: dict[str, Any]
    window_reasons: tuple[str, ...] = ()
    truncated: bool = False


class AnalysisPlan(Contract):
    schema_version: Literal["analysis-plan.v1"] = "analysis-plan.v1"
    analysis_engine: Literal["modular_v1"] = "modular_v1"
    plan_id: str = Field(default_factory=lambda: "plan-" + uuid4().hex)
    created_at: str = Field(default_factory=now)
    plan_hash: str
    sources: tuple[SourceSnapshot, ...]
    requested_window: Window
    sampling: Sampling
    context_budget: ContextBudget
    failure_policy: FailurePolicy
    targets: tuple[str, ...]
    nodes: tuple[PlanNode, ...]
    sync: dict[str, Any] | None = None
    reference_view_id: str
    cache_hints: dict[str, Any] = Field(default_factory=dict)


class ArtifactManifest(Contract):
    schema_version: Literal["analysis-artifact.v1"] = "analysis-artifact.v1"
    ref: ArtifactRef
    cache_key: str
    content_sha256: str
    storage_id: str
    relative_key: str
    created_at: str = Field(default_factory=now)
    created_by_job_id: str
    node_key: str
    implementation_id: str
    implementation_version: str
    provenance: dict[str, Any]
    inputs: tuple[ArtifactRef, ...] = ()
    quality: Quality = "sufficient"
    coordinates: Literal["image_px", "normalized_image", "court_m", "world_3d"] = "image_px"
    units: str = "px"
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class NodeRun(Contract):
    node_key: str
    capability_id: str
    implementation_id: str | None = None
    implementation_version: str | None = None
    configuration_digest: str | None = None
    status: NodeStatus = "pending"
    node_attempt: int = 0
    artifact: ArtifactRef | None = None
    error_code: str | None = None
    failure_class: str | None = None
    message: str | None = None
    internal_message: str | None = None
    counters: dict[str, Any] = Field(default_factory=dict)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class ModularRunManifest(Contract):
    schema_version: Literal["modular-run.v1"] = "modular-run.v1"
    result_kind: Literal["modular"] = "modular"
    analysis_engine: Literal["modular_v1"] = "modular_v1"
    job_id: str
    plan_id: str
    plan_hash: str
    status: Literal["queued", "running", "succeeded", "failed", "canceled", "interrupted"]
    completeness: Literal["complete", "partial", "none"]
    targets: tuple[str, ...]
    nodes: tuple[NodeRun, ...]
    artifacts: tuple[ArtifactRef, ...]
    created_at: str = Field(default_factory=now)


class ObjectRef(Contract):
    artifact_id: str
    object_type: str
    local_id: str
    view_id: str | None = None
    epoch: str | None = None
    subject_scope: Literal["observation", "local_track", "global_player", "event"] = "event"

    @model_validator(mode="after")
    def scoped_subject(self):
        if self.subject_scope in {"observation", "local_track"} and (not self.view_id or not self.epoch):
            raise ValueError("view-local subject requires view_id and epoch")
        return self


class AssociationCandidate(Contract):
    source: ObjectRef
    target: ObjectRef
    score: float = Field(ge=0, le=1)
    temporal_delta_ms: int
    constraints: dict[str, Any] = Field(default_factory=dict)


class Association(Contract):
    schema_version: Literal["analysis-association.v1"] = "analysis-association.v1"
    relation_type: str
    implementation_id: str
    implementation_version: str
    status: Literal["confirmed", "missing", "ambiguous", "insufficient_evidence"]
    candidates: tuple[AssociationCandidate, ...] = ()


class StrokeAttributes(Contract):
    taxonomy_version: str
    stage: str | None = None
    stroke_form: str | None = None
    semantic: str | None = None
    is_volley: bool | None = None
    confidence: float = Field(ge=0, le=1)
    evidence_sufficiency: Quality
    evidence: tuple[ObjectRef, ...] = ()
