"""
场地标定相关的 Pydantic 数据模型 —— 图像/球场坐标点、单应性矩阵、标定结果等。

"标定"是把"视频画面里的像素坐标"映射到"真实球场的尺寸坐标"。
本文件定义了标定的输入（用户点出的角点）、中间产物（单应性矩阵）和最终结果。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ImagePoint(BaseModel):
    """图像坐标系中的二维点（像素坐标）。"""

    x: float
    y: float


class CourtPoint2D(BaseModel):
    """真实球场坐标系中的二维点（单位英尺）。
    匹克球单打球场宽 20 英尺、长 44 英尺，因此坐标范围被限制在这个区间内。"""

    x: float = Field(ge=0, le=20)
    y: float = Field(ge=0, le=44)


class CalibrationKeypoint(BaseModel):
    """一个标定点：把图像上的点（image）和它在球场上的真实位置（court）对应起来。"""

    name: str
    image: ImagePoint
    court: CourtPoint2D


class HomographyMatrix(BaseModel):
    """单应性矩阵（3x3），用于图像坐标与球场坐标互转。"""

    values: list[list[float]] = Field(min_length=3, max_length=3)  # 必须是 3 行 3 列


class CourtCoordinateSystem(BaseModel):
    """球场坐标系定义：单位、宽度、长度。"""

    unit: Literal["feet"] = "feet"  # 单位（目前固定英尺）
    width: float = 20.0  # 球场宽（英尺）
    length: float = 44.0  # 球场长（英尺）


class CalibrationQuality(BaseModel):
    """标定质量：重投影误差越小越好；status 给出 ok / warning 提示。"""

    reprojection_error: float = Field(ge=0.0)
    status: Literal["ok", "warning"] = "ok"


class CalibrationCreate(BaseModel):
    """创建标定的基础请求：一组标定点 + 方法（手工 / 半自动）。"""

    video_id: str | None = None
    keypoints: list[CalibrationKeypoint] = Field(min_length=4)  # 至少 4 个点才能求解
    method: Literal["manual", "semi-automatic"] = "manual"


class CalibrationResult(BaseModel):
    """一次标定的完整结果（内部存储用）。"""

    id: str
    video_id: str | None = None
    keypoints: list[CalibrationKeypoint]
    homography: HomographyMatrix  # 正向矩阵：图像→球场
    inverse_homography: HomographyMatrix | None = None  # 逆向矩阵：球场→图像
    court_coordinate_system: CourtCoordinateSystem = Field(default_factory=CourtCoordinateSystem)
    quality: CalibrationQuality = Field(default_factory=lambda: CalibrationQuality(reprojection_error=0.0, status="ok"))
    method: Literal["manual", "semi-automatic"]
    created_at: datetime


class ManualImageKeypoints(BaseModel):
    """手工标定时用户点出的四个角点（图像像素坐标）。"""

    top_left: tuple[float, float]
    top_right: tuple[float, float]
    bottom_right: tuple[float, float]
    bottom_left: tuple[float, float]

    def as_named_points(self) -> dict[str, tuple[float, float]]:
        # 转成 {角点名: (x, y)} 的字典，方便后续处理
        return {
            "top_left": (float(self.top_left[0]), float(self.top_left[1])),
            "top_right": (float(self.top_right[0]), float(self.top_right[1])),
            "bottom_right": (float(self.bottom_right[0]), float(self.bottom_right[1])),
            "bottom_left": (float(self.bottom_left[0]), float(self.bottom_left[1])),
        }


class ManualKeypointCalibrationRequest(BaseModel):
    """手工四角标定的请求：视频 id + 四个角点。"""

    video_id: str | None = None
    image_points: ManualImageKeypoints


class ManualCalibrationResponse(BaseModel):
    """手工标定的响应：返回标定 id 与矩阵等，供前端直接使用。"""

    calibration_id: str
    homography: list[list[float]]
    inverse_homography: list[list[float]]
    court_coordinate_system: CourtCoordinateSystem
    quality: CalibrationQuality


class CalibrationReadResponse(ManualCalibrationResponse):
    """读取标定的响应：在手工响应基础上补充视频 id、角点列表、创建时间。"""

    video_id: str | None = None
    keypoints: list[CalibrationKeypoint] = Field(default_factory=list)
    created_at: datetime


class CalibrationPreviewRequest(BaseModel):
    """生成场地 overlay 预览图的请求：可选指定用哪一帧画面。"""

    frame_path: str | None = None


class CalibrationPreviewResponse(BaseModel):
    """预览图响应：返回预览图路径。"""

    calibration_id: str
    preview_image_path: str


# 自动标定建议的状态
AutomaticCalibrationStatus = Literal["available", "accepted", "rejected", "unavailable", "error"]


class AutomaticCalibrationRequest(BaseModel):
    """请求生成自动标定建议：指定视频 + 用哪一帧（按索引或时间）。"""

    video_id: str
    frame_index: int | None = Field(default=None, ge=0)
    timestamp_seconds: float | None = Field(default=None, ge=0.0)


class AutomaticCalibrationFrame(BaseModel):
    """自动标定所选用的帧信息。"""

    video_id: str
    frame_index: int
    timestamp_seconds: float
    width: int = Field(ge=0)
    height: int = Field(ge=0)


class AutomaticCalibrationMaskDiagnostics(BaseModel):
    """场地线分割掩码的诊断信息（模型是否就绪、置信度、面积占比、线数量等）。"""

    model_configured: bool = False
    model_path: str | None = None
    confidence: float | None = None
    mask_area_ratio: float | None = None
    line_count: int = 0
    detail: str


class AutomaticCalibrationKeypoints(BaseModel):
    """自动标定检测出的四个角点（图像坐标）。"""

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


class ReferenceLineDiagnostics(BaseModel):
    """基于标准球场线投影的一致性诊断（判断自动标定是否靠谱）。"""

    reference_score: float = Field(ge=0.0, le=1.0)  # 综合参考分
    coverage: float = Field(ge=0.0, le=1.0)  # 线覆盖度
    supported_lines: int = Field(ge=0)  # 支持的线数
    total_lines: int = Field(ge=0)  # 总参考线数
    tolerance_px: float = Field(ge=0.0)  # 容差（像素）
    line_count_supported: int = Field(ge=0)
    passing_line_names: list[str] = Field(default_factory=list)
    rejection_reason: str | None = None  # 若被拒，记录原因
    summary: str = ""


class ConfidenceBreakdown(BaseModel):
    """组合置信度拆解，暴露 segmentation（分割）、geometry（几何）、reference（参考）三类来源。"""

    segmentation: float = Field(ge=0.0, le=1.0)
    geometry: float = Field(ge=0.0, le=1.0)
    reference: float = Field(ge=0.0, le=1.0)
    combined: float = Field(ge=0.0, le=1.0)


class AutomaticCalibrationResponse(BaseModel):
    """自动标定建议的完整响应。"""

    status: AutomaticCalibrationStatus
    detail: str
    suggestion_id: str | None = None  # 建议 id（接受时用来保存）
    selected_frame: AutomaticCalibrationFrame | None = None
    keypoints: AutomaticCalibrationKeypoints | None = None
    confidence: float | None = None
    quality: CalibrationQuality | None = None
    mask: AutomaticCalibrationMaskDiagnostics  # 掩码诊断（必填）
    preview_image_url: str | None = None  # 预览图地址
    calibration_id: str | None = None  # 接受后生成的正式标定 id
    reference: ReferenceLineDiagnostics | None = None
    confidence_breakdown: ConfidenceBreakdown | None = None


class SemiAutomaticCalibrationAcceptRequest(BaseModel):
    """半自动标定"接受"请求：用户在建议基础上微调角点后确认。"""

    video_id: str | None = None
    image_points: ManualImageKeypoints
    source: Literal["automatic", "corrected"] = "automatic"  # 直接接受建议 / 已修正


class ProjectionRequest(BaseModel):
    """坐标投影请求：给出标定 id 与图像坐标点，求球场坐标。"""

    calibration_id: str
    image_point: ImagePoint


class ProjectionResult(BaseModel):
    """坐标投影结果：返回对应的球场坐标点。"""

    calibration_id: str
    image_point: ImagePoint
    court_point: CourtPoint2D
