"""单应性矩阵（Homography）计算与坐标变换 —— 图像像素 ↔ 球场英尺坐标。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import List, Tuple, Union

import numpy as np

PointLike = Union[Tuple[float, float], List[float]]
PointInput = Union[PointLike, Sequence[PointLike]]


class HomographyError(ValueError):
    pass


def _as_points(points: Sequence[PointLike], label: str) -> np.ndarray:
    array = np.asarray(points, dtype=float)
    if array.ndim != 2 or array.shape[1] != 2:
        raise HomographyError(f"{label} must be a sequence of 2D points")
    if not np.isfinite(array).all():
        raise HomographyError(f"{label} must contain only finite numeric coordinates")
    return array


def _as_homography(homography: Sequence[Sequence[float]] | np.ndarray) -> np.ndarray:
    matrix = np.asarray(homography, dtype=float)
    if matrix.shape != (3, 3):
        raise HomographyError("homography must be a 3x3 matrix")
    if not np.isfinite(matrix).all():
        raise HomographyError("homography must contain only finite numeric values")
    return matrix


def _normalize_homography(homography: np.ndarray) -> np.ndarray:
    if abs(float(homography[2, 2])) < 1e-12:
        raise HomographyError("homography normalization failed")
    return homography / homography[2, 2]


def compute_homography(image_points: Sequence[PointLike], court_points: Sequence[PointLike]) -> np.ndarray:
    """Compute an image-pixel to court-coordinate homography with OpenCV RANSAC."""

    src = _as_points(image_points, "image_points").astype(np.float32)
    dst = _as_points(court_points, "court_points").astype(np.float32)

    if len(src) != len(dst):
        raise HomographyError("image_points and court_points must have the same length")
    if len(src) < 4:
        raise HomographyError("at least four point correspondences are required")
    if np.unique(src, axis=0).shape[0] < 4 or np.unique(dst, axis=0).shape[0] < 4:
        raise HomographyError("point correspondences must include at least four unique points")

    try:
        import cv2  # type: ignore
    except ImportError as exc:
        raise HomographyError("OpenCV is required to compute homography") from exc

    matrix, inlier_mask = cv2.findHomography(src, dst, cv2.RANSAC)
    if matrix is None or matrix.shape != (3, 3):
        raise HomographyError("point correspondences are degenerate")
    if inlier_mask is not None and int(inlier_mask.sum()) < 4:
        raise HomographyError("homography requires at least four inlier correspondences")

    return _normalize_homography(np.asarray(matrix, dtype=float))


def _coerce_point_input(point_or_points: PointInput) -> tuple[np.ndarray, bool]:
    array = np.asarray(point_or_points, dtype=float)
    if array.ndim == 1:
        if array.shape[0] != 2:
            raise HomographyError("point must be a 2D coordinate")
        array = array.reshape(1, 2)
        is_single = True
    elif array.ndim == 2:
        if array.shape[1] != 2:
            raise HomographyError("points must be 2D coordinates")
        is_single = False
    else:
        raise HomographyError("point_or_points must be a 2D point or a sequence of 2D points")

    if not np.isfinite(array).all():
        raise HomographyError("point coordinates must be finite numbers")
    return array, is_single


def _transform_points(point_or_points: PointInput, homography: Sequence[Sequence[float]] | np.ndarray) -> tuple[float, float] | list[tuple[float, float]]:
    matrix = _as_homography(homography)
    points, is_single = _coerce_point_input(point_or_points)
    homogeneous = np.column_stack([points, np.ones(len(points), dtype=float)])
    projected = (matrix @ homogeneous.T).T

    invalid = np.isclose(projected[:, 2], 0.0, atol=1e-12)
    if bool(invalid.any()):
        raise HomographyError("projected point has invalid homogeneous coordinate")

    transformed = projected[:, :2] / projected[:, 2:3]
    result = [(float(x), float(y)) for x, y in transformed]
    return result[0] if is_single else result


def image_to_court(
    point_or_points: PointInput,
    homography: Sequence[Sequence[float]] | np.ndarray,
) -> tuple[float, float] | list[tuple[float, float]]:
    return _transform_points(point_or_points, homography)


def court_to_image(
    point_or_points: PointInput,
    inverse_homography: Sequence[Sequence[float]] | np.ndarray,
) -> tuple[float, float] | list[tuple[float, float]]:
    return _transform_points(point_or_points, inverse_homography)


def project_point(homography: Sequence[Sequence[float]], point: PointLike) -> tuple[float, float]:
    result = _transform_points(point, homography)
    if isinstance(result, list):
        return result[0]
    return result
