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


class CourtCoordinateSystem(BaseModel):
    unit: Literal["feet"] = "feet"
    width: float = 20.0
    length: float = 44.0


class CalibrationQuality(BaseModel):
    reprojection_error: float = Field(ge=0.0)
    status: Literal["ok", "warning"] = "ok"


class CalibrationCreate(BaseModel):
    video_id: Optional[str] = None
    keypoints: List[CalibrationKeypoint] = Field(min_length=4)
    method: Literal["manual", "semi-automatic"] = "manual"


class CalibrationResult(BaseModel):
    id: str
    video_id: Optional[str] = None
    keypoints: List[CalibrationKeypoint]
    homography: HomographyMatrix
    inverse_homography: Optional[HomographyMatrix] = None
    court_coordinate_system: CourtCoordinateSystem = Field(default_factory=CourtCoordinateSystem)
    quality: CalibrationQuality = Field(
        default_factory=lambda: CalibrationQuality(reprojection_error=0.0, status="ok")
    )
    method: Literal["manual", "semi-automatic"]
    created_at: datetime


class ManualImageKeypoints(BaseModel):
    top_left: tuple[float, float]
    top_right: tuple[float, float]
    bottom_right: tuple[float, float]
    bottom_left: tuple[float, float]

    def as_named_points(self) -> dict[str, tuple[float, float]]:
        return {
            "top_left": (float(self.top_left[0]), float(self.top_left[1])),
            "top_right": (float(self.top_right[0]), float(self.top_right[1])),
            "bottom_right": (float(self.bottom_right[0]), float(self.bottom_right[1])),
            "bottom_left": (float(self.bottom_left[0]), float(self.bottom_left[1])),
        }


class ManualKeypointCalibrationRequest(BaseModel):
    video_id: Optional[str] = None
    image_points: ManualImageKeypoints


class ManualCalibrationResponse(BaseModel):
    calibration_id: str
    homography: List[List[float]]
    inverse_homography: List[List[float]]
    court_coordinate_system: CourtCoordinateSystem
    quality: CalibrationQuality


class CalibrationReadResponse(ManualCalibrationResponse):
    video_id: Optional[str] = None
    keypoints: List[CalibrationKeypoint] = Field(default_factory=list)
    created_at: datetime


class CalibrationPreviewRequest(BaseModel):
    frame_path: Optional[str] = None


class CalibrationPreviewResponse(BaseModel):
    calibration_id: str
    preview_image_path: str


class ProjectionRequest(BaseModel):
    calibration_id: str
    image_point: ImagePoint


class ProjectionResult(BaseModel):
    calibration_id: str
    image_point: ImagePoint
    court_point: CourtPoint2D
