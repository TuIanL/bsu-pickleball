"""掩码→关键点转换 —— 从球场线分割掩码中提取四个角点用于标定。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.schemas.calibration import AutomaticCalibrationKeypoints, ImagePoint


@dataclass(frozen=True)
class LineCandidate:
    rho: float
    theta: float
    points: tuple[tuple[int, int], tuple[int, int]]
    orientation: str


@dataclass(frozen=True)
class MaskToKeypointsResult:
    keypoints: AutomaticCalibrationKeypoints
    confidence: float
    mask_area_ratio: float
    line_count: int
    lines: list[LineCandidate]


class MaskGeometryError(ValueError):
    pass


def mask_to_court_keypoints(
    mask: np.ndarray,
    min_area_ratio: float = 0.03,
) -> MaskToKeypointsResult:
    clean_mask = clean_court_line_mask(mask)
    height, width = clean_mask.shape[:2]
    if height <= 0 or width <= 0:
        raise MaskGeometryError("Mask has invalid dimensions")

    mask_area_ratio = float(np.count_nonzero(clean_mask)) / float(width * height)
    if mask_area_ratio < min_area_ratio:
        raise MaskGeometryError("Court-line mask is too sparse")

    lines = extract_line_candidates(clean_mask)
    if len(lines) < 4:
        keypoints = _contour_keypoints(clean_mask)
        confidence = _quadrilateral_confidence(keypoints, width, height, mask_area_ratio, line_count=len(lines))
        return MaskToKeypointsResult(
            keypoints=keypoints,
            confidence=confidence,
            mask_area_ratio=mask_area_ratio,
            line_count=len(lines),
            lines=lines,
        )

    horizontal = sorted([line for line in lines if line.orientation == "horizontal"], key=lambda line: line.rho)
    vertical = sorted([line for line in lines if line.orientation == "vertical"], key=lambda line: line.rho)
    if len(horizontal) < 2 or len(vertical) < 2:
        keypoints = _contour_keypoints(clean_mask)
        confidence = _quadrilateral_confidence(keypoints, width, height, mask_area_ratio, line_count=len(lines))
        return MaskToKeypointsResult(
            keypoints=keypoints,
            confidence=confidence,
            mask_area_ratio=mask_area_ratio,
            line_count=len(lines),
            lines=lines,
        )

    top_line = horizontal[0]
    bottom_line = horizontal[-1]
    left_line = vertical[0]
    right_line = vertical[-1]
    corners = [
        _intersect(left_line, top_line),
        _intersect(right_line, top_line),
        _intersect(right_line, bottom_line),
        _intersect(left_line, bottom_line),
    ]
    if any(point is None for point in corners):
        keypoints = _contour_keypoints(clean_mask)
    else:
        keypoints = _ordered_points_to_keypoints([(float(point[0]), float(point[1])) for point in corners if point])

    confidence = _quadrilateral_confidence(keypoints, width, height, mask_area_ratio, line_count=len(lines))
    return MaskToKeypointsResult(
        keypoints=keypoints,
        confidence=confidence,
        mask_area_ratio=mask_area_ratio,
        line_count=len(lines),
        lines=lines,
    )


def clean_court_line_mask(mask: np.ndarray) -> np.ndarray:
    binary = _as_binary_mask(mask)
    try:
        import cv2  # type: ignore
    except ImportError:
        return binary

    kernel = np.ones((5, 5), dtype=np.uint8)
    cleaned = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
    cleaned = cv2.dilate(cleaned, kernel, iterations=1)
    return cleaned


def extract_line_candidates(mask: np.ndarray) -> list[LineCandidate]:
    try:
        import cv2  # type: ignore
    except ImportError:
        return []

    edges = cv2.Canny(mask, 50, 150, apertureSize=3)
    min_length = max(24, int(min(mask.shape[:2]) * 0.15))
    raw_lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=max(24, min_length // 2),
        minLineLength=min_length,
        maxLineGap=max(10, min_length // 3),
    )
    if raw_lines is None:
        return []

    candidates: list[LineCandidate] = []
    for raw in raw_lines[:, 0, :]:
        x1, y1, x2, y2 = [int(value) for value in raw]
        dx = x2 - x1
        dy = y2 - y1
        length = float(np.hypot(dx, dy))
        if length < min_length:
            continue
        orientation = "horizontal" if abs(dx) >= abs(dy) else "vertical"
        if orientation == "horizontal":
            rho = float((y1 + y2) / 2.0)
            theta = float(np.arctan2(dy, dx))
        else:
            rho = float((x1 + x2) / 2.0)
            theta = float(np.arctan2(dy, dx))
        candidates.append(LineCandidate(rho=rho, theta=theta, points=((x1, y1), (x2, y2)), orientation=orientation))

    return _dedupe_lines(candidates, mask.shape)


def _dedupe_lines(lines: list[LineCandidate], shape: tuple[int, ...]) -> list[LineCandidate]:
    tolerance = max(8.0, min(shape[:2]) * 0.035)
    result: list[LineCandidate] = []
    for orientation in ("horizontal", "vertical"):
        oriented = sorted([line for line in lines if line.orientation == orientation], key=lambda line: line.rho)
        groups: list[list[LineCandidate]] = []
        for line in oriented:
            if groups and abs(groups[-1][-1].rho - line.rho) <= tolerance:
                groups[-1].append(line)
            else:
                groups.append([line])
        for group in groups:
            longest = max(group, key=lambda line: _line_length(line))
            result.append(longest)
    return result


def _line_length(line: LineCandidate) -> float:
    (x1, y1), (x2, y2) = line.points
    return float(np.hypot(x2 - x1, y2 - y1))


def _intersect(line_a: LineCandidate, line_b: LineCandidate) -> tuple[float, float] | None:
    (x1, y1), (x2, y2) = line_a.points
    (x3, y3), (x4, y4) = line_b.points
    denominator = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(float(denominator)) < 1e-9:
        return None
    px = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / denominator
    py = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / denominator
    return float(px), float(py)


def _contour_keypoints(mask: np.ndarray) -> AutomaticCalibrationKeypoints:
    try:
        import cv2  # type: ignore
    except ImportError as exc:
        raise MaskGeometryError("OpenCV is required for mask geometry extraction") from exc

    contours, _hierarchy = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise MaskGeometryError("Court-line mask has no contours")

    points = np.vstack(contours).reshape(-1, 2).astype(np.float32)
    rect = cv2.minAreaRect(points)
    box = cv2.boxPoints(rect)
    return _ordered_points_to_keypoints([(float(x), float(y)) for x, y in box])


def _ordered_points_to_keypoints(points: list[tuple[float, float]]) -> AutomaticCalibrationKeypoints:
    if len(points) != 4:
        raise MaskGeometryError("Exactly four points are required")
    ordered = _order_points(points)
    return AutomaticCalibrationKeypoints(
        top_left=ImagePoint(x=ordered[0][0], y=ordered[0][1]),
        top_right=ImagePoint(x=ordered[1][0], y=ordered[1][1]),
        bottom_right=ImagePoint(x=ordered[2][0], y=ordered[2][1]),
        bottom_left=ImagePoint(x=ordered[3][0], y=ordered[3][1]),
    )


def _order_points(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    array = np.asarray(points, dtype=float)
    sums = array.sum(axis=1)
    diffs = np.diff(array, axis=1).reshape(-1)
    top_left = array[int(np.argmin(sums))]
    bottom_right = array[int(np.argmax(sums))]
    top_right = array[int(np.argmin(diffs))]
    bottom_left = array[int(np.argmax(diffs))]
    return [
        (float(top_left[0]), float(top_left[1])),
        (float(top_right[0]), float(top_right[1])),
        (float(bottom_right[0]), float(bottom_right[1])),
        (float(bottom_left[0]), float(bottom_left[1])),
    ]


def _quadrilateral_confidence(
    keypoints: AutomaticCalibrationKeypoints,
    width: int,
    height: int,
    mask_area_ratio: float,
    line_count: int,
) -> float:
    points = np.asarray(
        [
            [keypoints.top_left.x, keypoints.top_left.y],
            [keypoints.top_right.x, keypoints.top_right.y],
            [keypoints.bottom_right.x, keypoints.bottom_right.y],
            [keypoints.bottom_left.x, keypoints.bottom_left.y],
        ],
        dtype=float,
    )
    if not np.isfinite(points).all():
        raise MaskGeometryError("Detected keypoints contain non-finite coordinates")
    if (points[:, 0] < -width * 0.1).any() or (points[:, 0] > width * 1.1).any():
        raise MaskGeometryError("Detected court corners are outside plausible frame bounds")
    if (points[:, 1] < -height * 0.1).any() or (points[:, 1] > height * 1.1).any():
        raise MaskGeometryError("Detected court corners are outside plausible frame bounds")

    polygon_area = _polygon_area(points)
    frame_area = float(width * height)
    area_ratio = polygon_area / frame_area if frame_area > 0 else 0.0
    if area_ratio < 0.08:
        raise MaskGeometryError("Detected court quadrilateral is too small")

    top_width = float(np.linalg.norm(points[1] - points[0]))
    bottom_width = float(np.linalg.norm(points[2] - points[3]))
    left_height = float(np.linalg.norm(points[3] - points[0]))
    right_height = float(np.linalg.norm(points[2] - points[1]))
    if min(top_width, bottom_width, left_height, right_height) <= 1:
        raise MaskGeometryError("Detected court quadrilateral has degenerate edges")

    opposite_balance = min(top_width, bottom_width) / max(top_width, bottom_width)
    height_balance = min(left_height, right_height) / max(left_height, right_height)
    line_score = min(line_count / 4.0, 1.0)
    area_score = min(max(area_ratio / 0.35, 0.0), 1.0)
    mask_score = min(max(mask_area_ratio / 0.08, 0.0), 1.0)
    return float(max(0.0, min(1.0, 0.35 * opposite_balance + 0.2 * height_balance + 0.2 * line_score + 0.15 * area_score + 0.1 * mask_score)))


def _polygon_area(points: np.ndarray) -> float:
    x = points[:, 0]
    y = points[:, 1]
    return float(abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2.0)


def _as_binary_mask(mask: np.ndarray) -> np.ndarray:
    array = np.asarray(mask)
    if array.ndim == 3:
        array = array.max(axis=2)
    return (array > 0).astype(np.uint8) * 255
