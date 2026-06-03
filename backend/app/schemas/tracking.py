"""球员跟踪相关的 Pydantic 数据模型 —— 检测框、轨迹、脚点投影、球员身份等。"""

from __future__ import annotations

from math import isfinite
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.schemas.calibration import ImagePoint

# 脚点估计方法：检测框底部中点 / 姿态脚踝均值 / 分割掩码底部
FootpointMethod = Literal["bbox_bottom_center", "pose_ankle_average", "segmentation_mask_bottom"]
PositionValidity = Literal["valid", "invalid"]
CourtUnit = Literal["m", "ft"]
PlayerTrackingStatus = Literal["detected", "interpolated", "lost", "inactive", "unmatched"]
PlayerSelectionMode = Literal["rule", "attention", "fallback"]
PlayerCandidateLabel = Literal["target_player", "neighbor_court_player", "spectator", "uncertain"]


def _validate_point(values: list[float], label: str) -> list[float]:
    if len(values) != 2:
        raise ValueError(f"{label} must contain exactly 2 numeric values")
    point = [float(value) for value in values]
    if not all(isfinite(value) for value in point):
        raise ValueError(f"{label} must contain only finite numeric values")
    return point


def _validate_bbox(values: list[float]) -> list[float]:
    if len(values) != 4:
        raise ValueError("bbox must contain exactly 4 numeric values")
    bbox = [float(value) for value in values]
    if not all(isfinite(value) for value in bbox):
        raise ValueError("bbox must contain only finite numeric values")
    return bbox


class Detection(BaseModel):
    bbox: list[float] = Field(min_length=4, max_length=4)
    confidence: float = Field(ge=0, le=1)
    class_name: Literal["person"] = "person"

    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, value: list[float]) -> list[float]:
        return _validate_bbox(value)


class Track(BaseModel):
    track_id: int = Field(ge=1)
    bbox: list[float] = Field(min_length=4, max_length=4)
    confidence: float = Field(ge=0, le=1)
    lost: bool = False

    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, value: list[float]) -> list[float]:
        return _validate_bbox(value)


class SourceFrameSize(BaseModel):
    width: int = Field(ge=1)
    height: int = Field(ge=1)


class FrameDetection(BaseModel):
    frame_index: int = Field(ge=0)
    timestamp_seconds: float = Field(ge=0)
    bbox: list[float] = Field(min_length=4, max_length=4)
    confidence: float = Field(ge=0, le=1)
    class_name: Literal["person"] = "person"
    track_id: Optional[str] = None
    player_id: Optional[str] = None
    label: Optional[str] = None
    source_width: int = Field(ge=1)
    source_height: int = Field(ge=1)

    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, value: list[float]) -> list[float]:
        return _validate_bbox(value)


class DetectionOverlayFrame(BaseModel):
    frame_index: int = Field(ge=0)
    timestamp_seconds: float = Field(ge=0)
    detections: list[FrameDetection] = Field(default_factory=list)


class TrackingOverlayArtifact(BaseModel):
    job_id: str
    video_id: Optional[str] = None
    status: Literal["available", "no_detections", "unavailable"] = "unavailable"
    detail: str
    source: SourceFrameSize
    fps: float = Field(default=0.0, ge=0)
    frame_count: int = Field(default=0, ge=0)
    processed_frame_count: int = Field(default=0, ge=0)
    frame_stride: int = Field(default=1, ge=1)
    frames: list[DetectionOverlayFrame] = Field(default_factory=list)


class FootpointEstimate(BaseModel):
    image_footpoint: list[float] = Field(min_length=2, max_length=2)
    method: FootpointMethod = "bbox_bottom_center"

    @field_validator("image_footpoint")
    @classmethod
    def validate_image_footpoint(cls, value: list[float]) -> list[float]:
        return _validate_point(value, "image_footpoint")


class PlayerFramePosition(BaseModel):
    frame_index: int = Field(ge=0)
    timestamp: float = Field(ge=0)
    track_id: int = Field(ge=1)
    bbox: list[float] = Field(min_length=4, max_length=4)
    image_footpoint: list[float] = Field(min_length=2, max_length=2)
    court_position: Optional[list[float]] = Field(default=None, min_length=2, max_length=2)
    court_unit: CourtUnit = "ft"
    confidence: float = Field(ge=0, le=1)
    valid: bool = True
    validity: PositionValidity = "valid"
    footpoint_method: FootpointMethod = "bbox_bottom_center"

    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, value: list[float]) -> list[float]:
        return _validate_bbox(value)

    @field_validator("image_footpoint")
    @classmethod
    def validate_image_footpoint(cls, value: list[float]) -> list[float]:
        return _validate_point(value, "image_footpoint")

    @field_validator("court_position")
    @classmethod
    def validate_court_position(cls, value: Optional[list[float]]) -> Optional[list[float]]:
        if value is None:
            return None
        return _validate_point(value, "court_position")


class TrackingResult(BaseModel):
    video_id: Optional[str] = None
    calibration_id: Optional[str] = None
    fps: float = Field(default=0.0, ge=0)
    frame_count: int = Field(default=0, ge=0)
    frame_width: int = Field(default=0, ge=0)
    frame_height: int = Field(default=0, ge=0)
    processed_frame_count: int = Field(default=0, ge=0)
    frame_stride: int = Field(default=1, ge=1)
    detections: list[Detection] = Field(default_factory=list)
    overlay_frames: list[DetectionOverlayFrame] = Field(default_factory=list)
    tracks: list[Track] = Field(default_factory=list)
    positions: list[PlayerFramePosition] = Field(default_factory=list)


class PlayerTrackletFeature(BaseModel):
    track_id: int = Field(ge=1)
    frame_start: int = Field(ge=0)
    frame_end: int = Field(ge=0)
    first_timestamp_seconds: float = Field(ge=0)
    last_timestamp_seconds: float = Field(ge=0)
    appearances: int = Field(ge=1)
    valid_positions: int = Field(default=0, ge=0)
    mean_confidence: float = Field(default=0.0, ge=0, le=1)
    latest_confidence: float = Field(default=0.0, ge=0, le=1)
    mean_bbox_area_ratio: float = Field(default=0.0, ge=0)
    court_position: Optional[list[float]] = Field(default=None, min_length=2, max_length=2)
    mean_court_position: Optional[list[float]] = Field(default=None, min_length=2, max_length=2)
    court_unit: CourtUnit = "ft"
    target_court_occupancy: float = Field(default=0.0, ge=0, le=1)
    mean_target_court_distance: float = Field(default=0.0, ge=0)
    max_target_court_distance: float = Field(default=0.0, ge=0)
    mean_speed: float = Field(default=0.0, ge=0)
    continuity: float = Field(default=0.0, ge=0, le=1)
    bbox: list[float] = Field(min_length=4, max_length=4)
    image_footpoint: list[float] = Field(min_length=2, max_length=2)

    @field_validator("bbox")
    @classmethod
    def validate_tracklet_bbox(cls, value: list[float]) -> list[float]:
        return _validate_bbox(value)

    @field_validator("image_footpoint")
    @classmethod
    def validate_tracklet_image_footpoint(cls, value: list[float]) -> list[float]:
        return _validate_point(value, "image_footpoint")

    @field_validator("court_position", "mean_court_position")
    @classmethod
    def validate_tracklet_court_position(cls, value: Optional[list[float]]) -> Optional[list[float]]:
        if value is None:
            return None
        return _validate_point(value, "court_position")


class PlayerSelectionDiagnostic(BaseModel):
    track_id: int = Field(ge=1)
    selected: bool
    selection_mode: PlayerSelectionMode = "rule"
    fallback_reason: Optional[str] = None
    target_court_score: float = Field(default=0.0, ge=0, le=1)
    tracklet_quality_score: float = Field(default=0.0, ge=0, le=1)
    group_consistency_score: float = Field(default=0.0, ge=0, le=1)
    attention_target_probability: Optional[float] = Field(default=None, ge=0, le=1)
    attention_non_target_probability: Optional[float] = Field(default=None, ge=0, le=1)
    final_score: float = Field(default=0.0, ge=0, le=1)
    candidate_label: PlayerCandidateLabel = "uncertain"
    reason: str
    frame_start: int = Field(ge=0)
    frame_end: int = Field(ge=0)
    components: dict[str, Any] = Field(default_factory=dict)


class PlayerSelectionArtifact(BaseModel):
    job_id: str
    video_id: Optional[str] = None
    status: Literal["available", "unavailable"] = "available"
    detail: str
    selection_mode: PlayerSelectionMode = "rule"
    fallback_reason: Optional[str] = None
    participant_limit: int = Field(default=4, ge=1)
    diagnostics: list[PlayerSelectionDiagnostic] = Field(default_factory=list)
    training_samples: list[PlayerTrackletFeature] = Field(default_factory=list)


class CourtDimensions(BaseModel):
    width: float = Field(gt=0)
    length: float = Field(gt=0)
    unit: CourtUnit


class CourtCoordinateMetadata(BaseModel):
    court_unit: CourtUnit = "m"
    canonical: CourtDimensions = Field(
        default_factory=lambda: CourtDimensions(width=6.10, length=13.41, unit="m")
    )
    imperial_reference: CourtDimensions = Field(
        default_factory=lambda: CourtDimensions(width=20.0, length=44.0, unit="ft")
    )
    feet_to_meters: float = Field(default=0.3048, gt=0)


class PlayerTrajectorySample(BaseModel):
    frame_index: int = Field(ge=0)
    timestamp_seconds: float = Field(ge=0)
    player_id: str
    track_id: Optional[int] = None
    bbox: Optional[list[float]] = Field(default=None, min_length=4, max_length=4)
    image_footpoint: Optional[list[float]] = Field(default=None, min_length=2, max_length=2)
    court_x: float
    court_y: float
    smoothed_court_x: Optional[float] = None
    smoothed_court_y: Optional[float] = None
    court_unit: CourtUnit = "m"
    confidence: float = Field(default=0.0, ge=0, le=1)
    tracking_status: PlayerTrackingStatus = "detected"
    is_interpolated: bool = False
    source: Literal["detector", "interpolation"] = "detector"

    @field_validator("bbox")
    @classmethod
    def validate_optional_bbox(cls, value: Optional[list[float]]) -> Optional[list[float]]:
        if value is None:
            return None
        return _validate_bbox(value)

    @field_validator("image_footpoint")
    @classmethod
    def validate_optional_image_footpoint(cls, value: Optional[list[float]]) -> Optional[list[float]]:
        if value is None:
            return None
        return _validate_point(value, "image_footpoint")


class PlayerTrajectoryState(BaseModel):
    player_id: str
    status: Literal["active", "lost", "inactive"] = "inactive"
    active_track_ids: list[int] = Field(default_factory=list)
    history_track_ids: list[int] = Field(default_factory=list)
    last_seen_frame: int = -1
    last_position_m: Optional[list[float]] = Field(default=None, min_length=2, max_length=2)
    last_velocity_mps: list[float] = Field(default_factory=lambda: [0.0, 0.0], min_length=2, max_length=2)
    confidence: float = Field(default=0.0, ge=0, le=1)

    @field_validator("last_position_m")
    @classmethod
    def validate_last_position(cls, value: Optional[list[float]]) -> Optional[list[float]]:
        if value is None:
            return None
        return _validate_point(value, "last_position_m")

    @field_validator("last_velocity_mps")
    @classmethod
    def validate_last_velocity(cls, value: list[float]) -> list[float]:
        return _validate_point(value, "last_velocity_mps")


class PlayerIdentityDiagnostic(BaseModel):
    frame_index: int = Field(ge=0)
    event: Literal["created", "assigned", "reconnected", "lost", "inactive", "unmatched", "filtered"]
    player_id: Optional[str] = None
    track_id: Optional[int] = None
    score: Optional[float] = None
    reason: str
    court_position_m: Optional[list[float]] = Field(default=None, min_length=2, max_length=2)

    @field_validator("court_position_m")
    @classmethod
    def validate_diagnostic_position(cls, value: Optional[list[float]]) -> Optional[list[float]]:
        if value is None:
            return None
        return _validate_point(value, "court_position_m")


class PlayerTrajectoryCoverage(BaseModel):
    player_id: str
    sample_count: int = Field(default=0, ge=0)
    detected_count: int = Field(default=0, ge=0)
    interpolated_count: int = Field(default=0, ge=0)
    first_timestamp_seconds: Optional[float] = Field(default=None, ge=0)
    last_timestamp_seconds: Optional[float] = Field(default=None, ge=0)
    first_frame_index: Optional[int] = Field(default=None, ge=0)
    last_frame_index: Optional[int] = Field(default=None, ge=0)
    status_counts: dict[str, int] = Field(default_factory=dict)
    history_track_ids: list[int] = Field(default_factory=list)


class PlayerTrajectoryCoverageDiagnostics(BaseModel):
    source_duration_seconds: Optional[float] = Field(default=None, ge=0)
    tracking_last_timestamp_seconds: Optional[float] = Field(default=None, ge=0)
    trajectory_first_timestamp_seconds: Optional[float] = Field(default=None, ge=0)
    trajectory_last_timestamp_seconds: Optional[float] = Field(default=None, ge=0)
    coverage_ratio: Optional[float] = Field(default=None, ge=0, le=1)
    players: list[PlayerTrajectoryCoverage] = Field(default_factory=list)
    diagnostic_event_counts: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class PlayerTrajectoryArtifact(BaseModel):
    job_id: str
    video_id: Optional[str] = None
    fps: float = Field(default=0.0, ge=0)
    frame_count: int = Field(default=0, ge=0)
    processed_frame_count: int = Field(default=0, ge=0)
    frame_stride: int = Field(default=1, ge=1)
    court: CourtCoordinateMetadata = Field(default_factory=CourtCoordinateMetadata)
    players: dict[str, list[PlayerTrajectorySample]] = Field(default_factory=dict)
    states: dict[str, PlayerTrajectoryState] = Field(default_factory=dict)
    diagnostics: list[PlayerIdentityDiagnostic] = Field(default_factory=list)
    coverage: Optional[PlayerTrajectoryCoverageDiagnostics] = None


class BoundingBox(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float


class PersonDetection(BaseModel):
    frame_index: int = Field(ge=0)
    label: Literal["person"] = "person"
    confidence: float = Field(ge=0, le=1)
    bbox: BoundingBox
    track_hint: Optional[str] = None


class ImageTrackPoint(BaseModel):
    frame_index: int = Field(ge=0)
    timestamp_seconds: float = Field(ge=0)
    track_id: str
    image_point: ImagePoint
    confidence: float = Field(ge=0, le=1)
    side: Literal["near", "far", "unknown"] = "unknown"


class ProjectedCourtPoint2D(BaseModel):
    """Observed court-space projection point; may sit outside the standard court."""

    x: float
    y: float

    @field_validator("x", "y")
    @classmethod
    def validate_coordinate(cls, value: float) -> float:
        coordinate = float(value)
        if not isfinite(coordinate):
            raise ValueError("projected court coordinate must be finite")
        return coordinate


class ProjectedTrackPoint(ImageTrackPoint):
    court_point: ProjectedCourtPoint2D


class PlayerTrack(BaseModel):
    track_id: str
    side: Literal["near", "far", "unknown"] = "unknown"
    points: List[ProjectedTrackPoint]
