from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ImagePoint(BaseModel):
    x: float
    y: float


class CourtPoint2D(BaseModel):
    x: float = Field(ge=0, le=20)
    y: float = Field(ge=0, le=44)


class CalibrationKeypoint(BaseModel):
    name: str
    image: ImagePoint
    court: CourtPoint2D


class HomographyMatrix(BaseModel):
    values: List[List[float]] = Field(min_length=3, max_length=3)


class CalibrationCreate(BaseModel):
    video_id: Optional[str] = None
    keypoints: List[CalibrationKeypoint] = Field(min_length=4)
    method: Literal["manual", "semi-automatic"] = "manual"


class CalibrationResult(BaseModel):
    id: str
    video_id: Optional[str] = None
    keypoints: List[CalibrationKeypoint]
    homography: HomographyMatrix
    method: Literal["manual", "semi-automatic"]
    created_at: datetime


class ProjectionRequest(BaseModel):
    calibration_id: str
    image_point: ImagePoint


class ProjectionResult(BaseModel):
    calibration_id: str
    image_point: ImagePoint
    court_point: CourtPoint2D
