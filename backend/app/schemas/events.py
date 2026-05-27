"""事件分析相关的 Pydantic 数据模型。"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

ServeEventStatus = Literal["available", "no_candidates", "partial", "unavailable"]
ServeSignal = Literal["tracking", "pose", "trajectory"]


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

    @model_validator(mode="after")
    def validate_seek_time(self) -> "ServeEventCandidate":
        if self.seek_time_seconds > self.timestamp_seconds:
            raise ValueError("seek_time_seconds must be less than or equal to timestamp_seconds")
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
    events: list[ServeEventCandidate] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_status_events(self) -> "ServeEventsArtifact":
        if self.events and self.status not in {"available", "partial"}:
            raise ValueError("serve events require available or partial status")
        return self
