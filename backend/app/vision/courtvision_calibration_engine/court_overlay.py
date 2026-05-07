from __future__ import annotations

from typing import Any

import numpy as np

from app.vision.courtvision_calibration_engine.court_geometry import StandardPickleballCourt, standard_court
from app.vision.courtvision_calibration_engine.homography import project_point


def court_line_image_points(
    image_to_court_homography: list[list[float]] | np.ndarray,
    court: StandardPickleballCourt | None = None,
) -> list[tuple[str, tuple[int, int], tuple[int, int]]]:
    court = court or standard_court()
    inverse = np.linalg.inv(np.asarray(image_to_court_homography, dtype=float))
    lines = []

    for line in court.lines:
        start = project_point(inverse, (line.start.x, line.start.y))
        end = project_point(inverse, (line.end.x, line.end.y))
        lines.append((line.name, (round(start[0]), round(start[1])), (round(end[0]), round(end[1]))))

    return lines


def draw_court_overlay(frame: Any, image_to_court_homography: list[list[float]] | np.ndarray) -> Any:
    """Draw the projected court lines when OpenCV is installed.

    The function returns the original frame unchanged if OpenCV is not available.
    """

    try:
        import cv2  # type: ignore
    except ImportError:
        return frame

    output = frame.copy()
    for _, start, end in court_line_image_points(image_to_court_homography):
        cv2.line(output, start, end, (68, 255, 120), 2)
    return output
