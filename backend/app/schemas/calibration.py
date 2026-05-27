"""场地标定相关的 Pydantic 数据模型 —— 图像/球场坐标点、单应性矩阵、标定结果等。"""

from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ImagePoint(BaseModel):
    """图像坐标系中的二维点（像素坐标）。"""
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


AutomaticCalibrationStatus = Literal["available", "accepted", "rejected", "unavailable", "error"]


class AutomaticCalibrationRequest(BaseModel):
    video_id: str
    frame_index: Optional[int] = Field(default=None, ge=0)
    timestamp_seconds: Optional[float] = Field(default=None, ge=0.0)


class AutomaticCalibrationFrame(BaseModel):
    video_id: str
    frame_index: int
    timestamp_seconds: float
    width: int = Field(ge=0)
    height: int = Field(ge=0)


class AutomaticCalibrationMaskDiagnostics(BaseModel):
    model_configured: bool = False
    model_path: Optional[str] = None
    confidence: Optional[float] = None
    mask_area_ratio: Optional[float] = None
    line_count: int = 0
    detail: str


class AutomaticCalibrationKeypoints(BaseModel):
    top_left: ImagePoint
    top_right: ImagePoint
    bottom_right: ImagePoint
    bottom_left: ImagePoint

    def as_named_points(self) -> dict[str, ImagePoint]:
        return {
            "top_left": self.top_left,
            "top_right": self.top_right,
            "bottom_right": self.bottom_right,
            "bottom_left": self.bottom_left,
        }


class AutomaticCalibrationResponse(BaseModel):
    status: AutomaticCalibrationStatus
    detail: str
    suggestion_id: Optional[str] = None
    selected_frame: Optional[AutomaticCalibrationFrame] = None
    keypoints: Optional[AutomaticCalibrationKeypoints] = None
    confidence: Optional[float] = None
    quality: Optional[CalibrationQuality] = None
    mask: AutomaticCalibrationMaskDiagnostics
    preview_image_url: Optional[str] = None
    calibration_id: Optional[str] = None


class SemiAutomaticCalibrationAcceptRequest(BaseModel):
    video_id: Optional[str] = None
    image_points: ManualImageKeypoints
    source: Literal["automatic", "corrected"] = "automatic"


class ProjectionRequest(BaseModel):
    calibration_id: str
    image_point: ImagePoint


class ProjectionResult(BaseModel):
    calibration_id: str
    image_point: ImagePoint
    court_point: CourtPoint2D
