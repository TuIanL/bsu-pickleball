from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.calibration import CourtPoint2D, ImagePoint


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
