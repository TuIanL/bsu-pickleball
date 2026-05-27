"""球员跟踪相关的 Pydantic 数据模型 —— 检测框、轨迹、脚点投影、球员身份等。"""

from __future__ import annotations

from math import isfinite
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.schemas.calibration import CourtPoint2D, ImagePoint

# 脚点估计方法：检测框底部中点 / 姿态脚踝均值 / 分割掩码底部
FootpointMethod = Literal["bbox_bottom_center", "pose_ankle_average", "segmentation_mask_bottom"]
PositionValidity = Literal["valid", "invalid"]
CourtUnit = Literal["m", "ft"]
PlayerTrackingStatus = Literal["detected", "interpolated", "lost", "inactive", "unmatched"]


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


class ProjectedTrackPoint(ImageTrackPoint):
    court_point: CourtPoint2D


class PlayerTrack(BaseModel):
    track_id: str
    side: Literal["near", "far", "unknown"] = "unknown"
    points: List[ProjectedTrackPoint]
