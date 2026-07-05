"""Court-view gate and ROI artifact schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CourtViewRoiStatus = Literal["available", "partial", "skipped", "unavailable"]
CourtViewFrameReason = Literal[
    "court_view",
    "gated_non_court_view",
    "gate_unavailable",
    "diagnostic_only",
]


class CourtViewThresholds(BaseModel):
    match_threshold: float = Field(ge=0.0, le=1.0)
    start_frames: int = Field(ge=1)
    end_frames: int = Field(ge=1)
    diagnostic_only: bool = False
    skip_non_court_frames: bool = True


class CourtViewSegment(BaseModel):
    id: str
    kind: Literal["court_view_candidate"] = "court_view_candidate"
    start_frame_index: int = Field(ge=0)
    end_frame_index: int = Field(ge=0)
    start_timestamp_seconds: float = Field(ge=0.0)
    end_timestamp_seconds: float = Field(ge=0.0)
    duration_seconds: float = Field(ge=0.0)
    start_reason: str
    end_reason: str
    low_score_frame_count: int = Field(default=0, ge=0)
    average_score: float | None = Field(default=None, ge=0.0, le=1.0)


class DetectionRoiBounds(BaseModel):
    x1: int = Field(ge=0)
    y1: int = Field(ge=0)
    x2: int = Field(ge=0)
    y2: int = Field(ge=0)
    source_width: int = Field(ge=1)
    source_height: int = Field(ge=1)
    padding_ratio: float = Field(ge=0.0)
    clipped_to_frame: bool = False


class DetectionRoiArtifact(BaseModel):
    status: CourtViewRoiStatus
    detail: str
    bounds: DetectionRoiBounds | None = None
    calibration_id: str | None = None
    source: Literal["calibration_keypoints", "unavailable"] = "unavailable"
    full_frame_fallback_count: int = Field(default=0, ge=0)
    filtered_detection_count: int = Field(default=0, ge=0)
    disabled: bool = False
    diagnostics: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class CourtViewFrameSample(BaseModel):
    frame_index: int = Field(ge=0)
    timestamp_seconds: float = Field(ge=0.0)
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    is_court_view: bool | None = None
    reason: CourtViewFrameReason


class CourtViewRoiArtifact(BaseModel):
    job_id: str
    video_id: str | None = None
    calibration_id: str | None = None
    status: CourtViewRoiStatus
    detail: str
    detector_version: str = "court-view-template-v1"
    thresholds: CourtViewThresholds
    processed_frame_count: int = Field(default=0, ge=0)
    court_view_frame_count: int = Field(default=0, ge=0)
    non_court_view_frame_count: int = Field(default=0, ge=0)
    gated_frame_count: int = Field(default=0, ge=0)
    roi_filtered_detection_count: int = Field(default=0, ge=0)
    full_frame_fallback_count: int = Field(default=0, ge=0)
    candidate_segments: list[CourtViewSegment] = Field(default_factory=list)
    roi: DetectionRoiArtifact
    frame_samples: list[CourtViewFrameSample] = Field(default_factory=list)
    diagnostics: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
