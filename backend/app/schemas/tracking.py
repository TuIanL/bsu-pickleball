from __future__ import annotations

from math import isfinite
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.schemas.calibration import CourtPoint2D, ImagePoint

FootpointMethod = Literal["bbox_bottom_center", "pose_ankle_average", "segmentation_mask_bottom"]
PositionValidity = Literal["valid", "invalid"]


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
    processed_frame_count: int = Field(default=0, ge=0)
    frame_stride: int = Field(default=1, ge=1)
    detections: list[Detection] = Field(default_factory=list)
    tracks: list[Track] = Field(default_factory=list)
    positions: list[PlayerFramePosition] = Field(default_factory=list)


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
