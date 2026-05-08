from __future__ import annotations

from typing import Any

import numpy as np

from app.vision.courtvision_calibration_engine.court_geometry import (
    CourtLine,
    CourtPoint,
    CourtPolygon,
    PickleballCourtGeometry,
    standard_court,
)
from app.vision.courtvision_calibration_engine.homography import court_to_image


def court_line_image_points(
    court_to_image_homography: list[list[float]] | np.ndarray,
    court: PickleballCourtGeometry | None = None,
) -> list[tuple[str, tuple[int, int], tuple[int, int]]]:
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
    """Draw the projected court lines when OpenCV is installed.

    The function returns the original frame unchanged if OpenCV is not available.
    """

    try:
        import cv2  # type: ignore
    except ImportError:
        return frame

    court = court or standard_court()
    output = frame.copy()
    fill_layer = output.copy()

    fill_colors = {
        "near_kitchen": (64, 196, 255),
        "far_kitchen": (64, 196, 255),
        "near_left_service": (76, 220, 136),
        "near_right_service": (76, 220, 136),
        "far_left_service": (76, 220, 136),
        "far_right_service": (76, 220, 136),
    }
    for name, points in court_polygon_image_points(court_to_image_homography, court):
        cv2.fillPoly(fill_layer, [points], fill_colors.get(name, (76, 220, 136)))

    output = cv2.addWeighted(fill_layer, 0.24, output, 0.76, 0)

    for line in court.lines:
        start, end = _project_line(line, court_to_image_homography)
        color = (68, 255, 120)
        thickness = 2
        if line.name == "net":
            color = (50, 70, 255)
            thickness = 3
        elif "kitchen" in line.name:
            color = (35, 190, 255)
        cv2.line(output, start, end, color, thickness)

    return output


def _project_line(line: CourtLine, homography: list[list[float]] | np.ndarray) -> tuple[tuple[int, int], tuple[int, int]]:
    start = _project_point(line.start, homography)
    end = _project_point(line.end, homography)
    return start, end


def _project_polygon(polygon: CourtPolygon, homography: list[list[float]] | np.ndarray) -> np.ndarray:
    points = [_project_point(point, homography) for point in polygon.points]
    return np.asarray(points, dtype=np.int32)


def _project_point(point: CourtPoint, homography: list[list[float]] | np.ndarray) -> tuple[int, int]:
    projected = court_to_image((point.x, point.y), homography)
    if isinstance(projected, list):
        projected = projected[0]
    return round(projected[0]), round(projected[1])
