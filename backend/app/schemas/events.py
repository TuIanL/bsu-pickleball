"""事件分析相关的 Pydantic 数据模型。"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

ServeEventStatus = Literal["available", "no_candidates", "partial", "unavailable"]
ServeSignal = Literal["tracking", "pose", "trajectory", "roi", "video"]
ServeDetectionMode = Literal["pose", "roi", "trajectory", "tracking"]
ServeContextState = Literal["ready_to_serve", "candidate", "rejected", "unavailable"]


class ServeSignalScores(BaseModel):
    baseline_position_score: Optional[float] = Field(default=None, ge=0, le=1)
    pre_stillness_score: Optional[float] = Field(default=None, ge=0, le=1)
    arm_motion_peak_score: Optional[float] = Field(default=None, ge=0, le=1)
    roi_motion_peak_score: Optional[float] = Field(default=None, ge=0, le=1)
    rally_after_score: Optional[float] = Field(default=None, ge=0, le=1)
    receiver_waiting_score: Optional[float] = Field(default=None, ge=0, le=1)


class ServeCoverageDiagnostics(BaseModel):
    source_duration_seconds: Optional[float] = Field(default=None, ge=0)
    tracking_first_timestamp_seconds: Optional[float] = Field(default=None, ge=0)
    tracking_last_timestamp_seconds: Optional[float] = Field(default=None, ge=0)
    pose_first_timestamp_seconds: Optional[float] = Field(default=None, ge=0)
    pose_last_timestamp_seconds: Optional[float] = Field(default=None, ge=0)
    trajectory_first_timestamp_seconds: Optional[float] = Field(default=None, ge=0)
    trajectory_last_timestamp_seconds: Optional[float] = Field(default=None, ge=0)
    score_series_first_timestamp_seconds: Optional[float] = Field(default=None, ge=0)
    score_series_last_timestamp_seconds: Optional[float] = Field(default=None, ge=0)
    score_series_count: int = Field(default=0, ge=0)
    candidate_first_timestamp_seconds: Optional[float] = Field(default=None, ge=0)
    candidate_last_timestamp_seconds: Optional[float] = Field(default=None, ge=0)
    candidate_count: int = Field(default=0, ge=0)
    coverage_ratio: Optional[float] = Field(default=None, ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class ServeDebugArtifactRefs(BaseModel):
    candidates_url: Optional[str] = None
    score_series_url: Optional[str] = None
    clips_manifest_url: Optional[str] = None
    debug_overlay_url: Optional[str] = None
    status: Optional[str] = None
    detail: Optional[str] = None


class ServeEventCandidate(BaseModel):
    id: str
    timestamp_seconds: float = Field(ge=0)
    frame_index: int = Field(ge=0)
    confidence: float = Field(ge=0, le=1)
    seek_time_seconds: float = Field(ge=0)
    reason: str
    source_signals: list[ServeSignal] = Field(default_factory=list)
    track_id: Optional[str] = None
    player_id: Optional[str] = None
    start_time_seconds: Optional[float] = Field(default=None, ge=0)
    end_time_seconds: Optional[float] = Field(default=None, ge=0)
    detection_mode: Optional[ServeDetectionMode] = None
    context_state: Optional[ServeContextState] = None
    court_position: Optional[list[float]] = Field(default=None, min_length=2, max_length=2)
    court_unit: Optional[str] = None
    signals: Optional[ServeSignalScores] = None

    @model_validator(mode="after")
    def validate_seek_time(self) -> "ServeEventCandidate":
        if self.seek_time_seconds > self.timestamp_seconds:
            raise ValueError("seek_time_seconds must be less than or equal to timestamp_seconds")
        if self.start_time_seconds is not None and self.start_time_seconds > self.timestamp_seconds:
            raise ValueError("start_time_seconds must be less than or equal to timestamp_seconds")
        if self.end_time_seconds is not None and self.end_time_seconds < self.timestamp_seconds:
            raise ValueError("end_time_seconds must be greater than or equal to timestamp_seconds")
        return self

    @field_validator("source_signals")
    @classmethod
    def validate_source_signals(cls, value: list[ServeSignal]) -> list[ServeSignal]:
        return list(dict.fromkeys(value))


class ServeEventsArtifact(BaseModel):
    job_id: str
    video_id: Optional[str] = None
    status: ServeEventStatus = "unavailable"
    detail: str
    detector_version: str = "serve-start-mvp-v1"
    duration_seconds: Optional[float] = Field(default=None, ge=0)
    fps: float = Field(default=0.0, ge=0)
    frame_count: int = Field(default=0, ge=0)
    processed_frame_count: int = Field(default=0, ge=0)
    frame_stride: int = Field(default=1, ge=1)
    detection_mode: Optional[ServeDetectionMode] = None
    available_signals: list[ServeSignal] = Field(default_factory=list)
    debug_artifacts: Optional[ServeDebugArtifactRefs] = None
    coverage: Optional[ServeCoverageDiagnostics] = None
    events: list[ServeEventCandidate] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_status_events(self) -> "ServeEventsArtifact":
        if self.events and self.status not in {"available", "partial"}:
            raise ValueError("serve events require available or partial status")
        return self
