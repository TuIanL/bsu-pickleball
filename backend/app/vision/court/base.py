"""球场标定基础接口 —— 定义像素→球场坐标映射的抽象协议。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CourtCoordinate:
    """球场坐标系中的点（含置信度）。"""
    x: float
    y: float
    confidence: float


class CourtCalibrator:
    """球场标定器抽象基类。"""
    def map_pixel_to_court(self, x: float, y: float) -> CourtCoordinate:
        raise NotImplementedError("Court calibration will be implemented after real court-line detection is available.")
