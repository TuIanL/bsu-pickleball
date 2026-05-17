from __future__ import annotations

from math import isfinite
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.schemas.multitarget import MultiTargetDetection, MultiTargetStatus
from app.schemas.tracking import SourceFrameSize


BallPointSource = Literal["observed", "predicted", "repaired"]


def _validate_point(values: list[float], label: str) -> list[float]:
    if len(values) != 2:
        raise ValueError(f"{label} must contain exactly 2 numeric values")
    point = [float(value) for value in values]
    if not all(isfinite(value) for value in point):
        raise ValueError(f"{label} must contain only finite numeric values")
    return point


class BallDetectionFrame(BaseModel):
    frame_index: int = Field(ge=0)
    timestamp_seconds: float = Field(ge=0)
    detections: list[MultiTargetDetection] = Field(default_factory=list)


class BallTrajectoryPoint(BaseModel):
    frame_index: int = Field(ge=0)
    timestamp_seconds: float = Field(ge=0)
    image_point: list[float] = Field(min_length=2, max_length=2)
    confidence: float = Field(ge=0, le=1)
    source: BallPointSource = "observed"
    segment_id: int = Field(default=1, ge=1)
    bbox: Optional[list[float]] = Field(default=None, min_length=4, max_length=4)

    @field_validator("image_point")
    @classmethod
    def validate_image_point(cls, value: list[float]) -> list[float]:
        return _validate_point(value, "image_point")


class BallOverlayFrame(BaseModel):
    frame_index: int = Field(ge=0)
    timestamp_seconds: float = Field(ge=0)
    points: list[BallTrajectoryPoint] = Field(default_factory=list)


class BallOverlayArtifact(BaseModel):
    job_id: str
    video_id: Optional[str] = None
    status: MultiTargetStatus = "unavailable"
    detail: str
    source: SourceFrameSize
    fps: float = Field(default=0.0, ge=0)
    frame_count: int = Field(default=0, ge=0)
    processed_frame_count: int = Field(default=0, ge=0)
    frame_stride: int = Field(default=1, ge=1)
    detector_status: MultiTargetStatus = "unavailable"
    frames: list[BallOverlayFrame] = Field(default_factory=list)
    detections: list[BallDetectionFrame] = Field(default_factory=list)
    diagnostic_counts: dict[str, int] = Field(default_factory=dict)
