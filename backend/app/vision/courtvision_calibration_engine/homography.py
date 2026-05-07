from __future__ import annotations

from collections.abc import Sequence
from typing import List, Tuple, Union

import numpy as np

PointLike = Union[Tuple[float, float], List[float]]


class HomographyError(ValueError):
    pass


def _as_points(points: Sequence[PointLike], label: str) -> np.ndarray:
    array = np.asarray(points, dtype=float)
    if array.ndim != 2 or array.shape[1] != 2:
        raise HomographyError(f"{label} must be a sequence of 2D points")
    return array


def compute_homography(image_points: Sequence[PointLike], court_points: Sequence[PointLike]) -> np.ndarray:
    """Compute an image-pixel to court-coordinate homography with DLT."""

    src = _as_points(image_points, "image_points")
    dst = _as_points(court_points, "court_points")

    if len(src) != len(dst):
        raise HomographyError("image_points and court_points must have the same length")
    if len(src) < 4:
        raise HomographyError("at least four point correspondences are required")

    rows: list[list[float]] = []
    for (x, y), (u, v) in zip(src, dst):
        rows.append([-x, -y, -1.0, 0.0, 0.0, 0.0, u * x, u * y, u])
        rows.append([0.0, 0.0, 0.0, -x, -y, -1.0, v * x, v * y, v])

    matrix = np.asarray(rows, dtype=float)
    if np.linalg.matrix_rank(matrix) < 8:
        raise HomographyError("point correspondences are degenerate")

    _, _, vh = np.linalg.svd(matrix)
    h = vh[-1].reshape(3, 3)

    if abs(h[2, 2]) < 1e-12:
        raise HomographyError("homography normalization failed")

    return h / h[2, 2]


def project_point(homography: Sequence[Sequence[float]], point: PointLike) -> tuple[float, float]:
    h = np.asarray(homography, dtype=float)
    if h.shape != (3, 3):
        raise HomographyError("homography must be a 3x3 matrix")

    x, y = float(point[0]), float(point[1])
    projected = h @ np.asarray([x, y, 1.0], dtype=float)

    if abs(projected[2]) < 1e-12:
        raise HomographyError("projected point has invalid homogeneous coordinate")

    return float(projected[0] / projected[2]), float(projected[1] / projected[2])
