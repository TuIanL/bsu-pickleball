"""未来域的数据合同。只定义证据形状，生产 Registry 仍标记 planned。"""
from __future__ import annotations

from typing import Literal
from pydantic import Field, model_validator
from app.analysis_runtime.contracts import Contract, ObjectRef, Quality, StrokeAttributes, Window


class FrameAddress(Contract):
    media_revision: str
    view_id: str
    source_frame_index: int = Field(ge=0)
    source_pts_ms: float
    canonical_time_ms: float = Field(ge=0)


class RacketObservation(Contract):
    local_id: str
    frame: FrameAddress
    bbox_xyxy: tuple[float, float, float, float]
    confidence: float = Field(ge=0, le=1)
    coordinates: Literal["image_px"] = "image_px"


class MotionEvidence(Contract):
    local_id: str
    actor: ObjectRef
    window: Window
    evidence: tuple[ObjectRef, ...]
    values: dict[str, float | None]
    units: dict[str, str]  # 例如 displacement=px、speed=px/s；不推断生物力学量。
    coordinates: Literal["image_px", "normalized_image", "court_m", "world_3d"]
    quality: Quality


class SwingPhase(Contract):
    name: Literal["setup", "backswing", "forward_swing", "contact", "follow_through", "recovery", "unknown"]
    window: Window
    confidence: float = Field(ge=0, le=1)


class SwingSequence(Contract):
    local_id: str
    actor: ObjectRef | None = None
    window: Window
    contact_ms: int | None = None
    phases: tuple[SwingPhase, ...] = ()
    evidence: tuple[ObjectRef, ...]
    quality: Quality

    @model_validator(mode="after")
    def phase_bounds(self):
        if any(p.window.start_ms < self.window.start_ms or p.window.end_ms > self.window.end_ms for p in self.phases):
            raise ValueError("phase outside swing interval")
        return self


class ContactCandidate(Contract):
    local_id: str
    time_ms: int = Field(ge=0)
    actor: ObjectRef | None = None
    ball: ObjectRef | None = None
    racket: ObjectRef | None = None
    confidence: float = Field(ge=0, le=1)
    quality: Quality
    evidence: tuple[ObjectRef, ...]


class BallEventCandidate(ContactCandidate):
    event_kind: Literal["contact", "bounce", "net", "loss"]


class SubjectTrack(Contract):
    local_id: str
    subject_scope: Literal["local_track", "global_player"]
    view_id: str | None = None
    epoch: str
    window: Window
    observations: tuple[ObjectRef, ...]
    quality: Quality

    @model_validator(mode="after")
    def local_view(self):
        if self.subject_scope == "local_track" and not self.view_id:
            raise ValueError("local track requires a view")
        return self


class BallTrackEvidence(Contract):
    local_id: str
    phase: Literal["observed_2d", "cleaned_2d", "event_constrained_3d"]
    window: Window
    coordinates: Literal["image_px", "court_m", "world_3d"]
    samples: tuple[dict[str, float | int | None], ...]
    evidence: tuple[ObjectRef, ...]
    quality: Quality

    @model_validator(mode="after")
    def reconstruction_coordinates(self):
        if self.phase == "event_constrained_3d" and self.coordinates != "world_3d":
            raise ValueError("3D reconstruction requires world_3d coordinates")
        return self


class ShotEvidence(Contract):
    local_id: str
    window: Window
    contact: ObjectRef
    source_segment: ObjectRef
    start_event: ObjectRef
    end_event: ObjectRef | None = None
    stage: str | None = None
    quality: Quality

    @model_validator(mode="after")
    def complete_end(self):
        if self.quality == "sufficient" and self.end_event is None:
            raise ValueError("complete shot requires an end event")
        return self


class LandingEvidence(Contract):
    local_id: str
    shot: ObjectRef
    source_segment: ObjectRef
    source_event: ObjectRef  # 必须是严格引用，缺失时输出缺证据状态，不猜最近事件。
    time_ms: int = Field(ge=0)
    coordinates: Literal["image_px", "court_m", "world_3d"]
    position: tuple[float, ...]
    calibration_revision: str | None = None
    quality: Quality


class RallyContext(Contract):
    local_id: str
    window: Window
    roster_snapshot_hash: str | None = None
    score_snapshot_hash: str | None = None
    stage: str | None = None
    evidence: tuple[ObjectRef, ...] = ()


class SemanticCandidate(Contract):
    label: str
    confidence: float = Field(ge=0, le=1)
    evidence_sufficiency: Quality
    missing_evidence: tuple[str, ...] = ()


class ShotSemantics(Contract):
    local_id: str
    shot: ObjectRef
    taxonomy_version: str
    attributes: StrokeAttributes | None = None
    candidates: tuple[SemanticCandidate, ...]
    evidence: tuple[ObjectRef, ...]


class TacticalInterpretation(Contract):
    local_id: str
    rally: ObjectRef
    taxonomy_version: str
    candidates: tuple[SemanticCandidate, ...]
    evidence: tuple[ObjectRef, ...]


class EvaluationEvidence(Contract):
    local_id: str
    window: Window
    metrics: dict[str, float | None]
    reasons: tuple[str, ...] = ()
    evidence: tuple[ObjectRef, ...]
