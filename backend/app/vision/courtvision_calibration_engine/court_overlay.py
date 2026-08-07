"""
球场叠加绘制（court_overlay）—— 把标准匹克球场线"投影回"原始视频帧上画出来。

标定完成后，我们就有了"球场→图像"的单应性矩阵 H。
用它可以把标准球场的每条线（来自 court_geometry）投影到当前画面上，
然后画在视频帧上，让人一眼看到"AI 认出的球场位置准不准"。
"""

# `from __future__ import annotations`：兼容较新类型写法。
from __future__ import annotations

# Any：泛指"一张图（numpy array）"，这里用来放宽参数类型。
from typing import Any

# numpy：数值计算库。
import numpy as np

# 标准球场几何的各类数据结构（点/线/多边形/球场对象）。
from app.vision.courtvision_calibration_engine.court_geometry import (
    CourtLine,
    CourtPoint,
    CourtPolygon,
    PickleballCourtGeometry,
    standard_court,
)

# 球场坐标 → 像素坐标 的投影函数。
from app.vision.courtvision_calibration_engine.homography import court_to_image


def court_line_image_points(
    court_to_image_homography: list[list[float]] | np.ndarray,
    court: PickleballCourtGeometry | None = None,
) -> list[tuple[str, tuple[int, int], tuple[int, int]]]:
    """
    返回所有球场线在"图像像素"上的起止点。

    返回格式：[(线名, (起点x,起点y), (终点x,终点y)), ...]，
    方便上层直接拿去画线或做其它处理。
    """
    court = court or standard_court()
    lines = []

    for line in court.lines:
        start, end = _project_line(line, court_to_image_homography)
        lines.append((line.name, start, end))

    return lines


def court_polygon_image_points(
    court_to_image_homography: list[list[float]] | np.ndarray,
    court: PickleballCourtGeometry | None = None,
) -> list[tuple[str, np.ndarray]]:
    """返回所有"要填充的多边形"（厨房区、发球区）在图像像素上的点集合。"""
    court = court or standard_court()
    polygons = []
    for polygon in court.overlay_fill_polygons:
        polygons.append((polygon.name, _project_polygon(polygon, court_to_image_homography)))
    return polygons


def draw_court_overlay(
    frame: Any,
    court_to_image_homography: list[list[float]] | np.ndarray,
    court: PickleballCourtGeometry | None = None,
) -> Any:
    """
    在视频帧上画出投影后的球场线 + 半透明区域填充。

    - 若没装 OpenCV，直接原样返回原帧（不出错、不画）。
    - 区域（厨房区、发球区）用半透明色块填充，再叠加上清晰的球场线。
    返回：画好叠加层的新帧。
    """

    try:
        import cv2  # type: ignore
    except ImportError:
        return frame

    court = court or standard_court()
    output = frame.copy()  # 复制一份，避免改到原图
    fill_layer = output.copy()  # 单独一层用来画填充色块

    # 各区域的填充颜色（BGR 顺序，OpenCV 里颜色是蓝-绿-红）
    fill_colors = {
        "near_kitchen": (64, 196, 255),
        "far_kitchen": (64, 196, 255),
        "near_left_service": (76, 220, 136),
        "near_right_service": (76, 220, 136),
        "far_left_service": (76, 220, 136),
        "far_right_service": (76, 220, 136),
    }
    # 先在每个区域多边形上填充半透明色块
    for name, points in court_polygon_image_points(court_to_image_homography, court):
        cv2.fillPoly(fill_layer, [points], fill_colors.get(name, (76, 220, 136)))

    # 把填充层以 0.24 的权重与原图 0.76 叠加，得到"淡色半透明"效果
    output = cv2.addWeighted(fill_layer, 0.24, output, 0.76, 0)

    # 再画球场线（不同线用不同颜色/粗细区分）
    for line in court.lines:
        start, end = _project_line(line, court_to_image_homography)
        color = (68, 255, 120)  # 默认线颜色（绿）
        thickness = 2  # 默认线宽
        if line.name == "net":
            color = (50, 70, 255)  # 球网用偏蓝色、更粗
            thickness = 3
        elif "kitchen" in line.name:
            color = (35, 190, 255)  # 厨房线用蓝色
        cv2.line(output, start, end, color, thickness)

    return output


def _project_line(
    line: CourtLine, homography: list[list[float]] | np.ndarray
) -> tuple[tuple[int, int], tuple[int, int]]:
    """把一条球场线的起点、终点分别投影到图像像素坐标（取整）。"""
    start = _project_point(line.start, homography)
    end = _project_point(line.end, homography)
    return start, end


def _project_polygon(polygon: CourtPolygon, homography: list[list[float]] | np.ndarray) -> np.ndarray:
    """把一个多边形的所有顶点投影成图像像素坐标（int32 数组，供 cv2 填充用）。"""
    points = [_project_point(point, homography) for point in polygon.points]
    return np.asarray(points, dtype=np.int32)


def _project_point(point: CourtPoint, homography: list[list[float]] | np.ndarray) -> tuple[int, int]:
    """把单个球场点投影成图像像素坐标，并四舍五入成整数像素。"""
    projected = court_to_image((point.x, point.y), homography)
    if isinstance(projected, list):
        projected = projected[0]
    return round(projected[0]), round(projected[1])
