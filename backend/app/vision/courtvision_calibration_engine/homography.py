"""
单应性矩阵（Homography）计算与坐标变换 —— 图像像素 ↔ 球场英尺坐标。

什么是单应性矩阵？
- 相机斜着拍球场，画面里的球场是一个"梯形透视变形"。单应性矩阵 H 是一个 3×3 的矩阵，
  能把"球场平面上的一个点"精确映射到"图像平面上的对应点"（反过来也行，用 H 的逆）。
- 只要我们知道"球场上的 4 个点"和它们在"画面上的 4 个对应像素点"，就能解出 H。
- 之后，任意像素点都能用 H 投影成球场坐标（比如球员脚底像素 → 球场真实位置），
  任意球场坐标也能用 H 的逆投影回画面（比如把标准球场线画回视频上）。

背后用到齐次坐标：一个 2D 点 (x, y) 写成 (x, y, 1)，乘上 3×3 的 H，
得到 (x', y', w')，再除以 w' 还原成 (x'/w', y'/w')。
"""

# `from __future__ import annotations`：兼容较新类型写法。
from __future__ import annotations

# Sequence：泛指"序列"（list/tuple 等）；下面用来标注"一串点"这种参数。
from collections.abc import Sequence
# List / Tuple / Union：类型注解用（Union 表示"或"）。
from typing import List, Tuple, Union

# numpy：Python 的数值计算库，矩阵/数组运算都靠它（写作 np）。
import numpy as np

# PointLike：单个 2D 点的类型，可以是 (x, y) 元组或 [x, y] 列表。
PointLike = Union[Tuple[float, float], List[float]]
# PointInput：可以是一个点，也可以是一串点。
PointInput = Union[PointLike, Sequence[PointLike]]


class HomographyError(ValueError):
    """
    单应性计算相关的自定义异常，继承自 ValueError。

    单独建一个类，方便调用方精确捕获"标定/投影"相关的错误（而不是把所有 ValueError 都拦下）。
    """
    pass


def _as_points(points: Sequence[PointLike], label: str) -> np.ndarray:
    """
    把一串点转成 numpy 数组并做基本校验。

    - 必须能转成二维数组，且第二维是 2（即每个点有 x、y 两个值）；
    - 所有坐标必须是有限数（不能是 NaN / 无穷大）。

    `label` 用于报错时指出"是哪个输入"不合法。
    """
    array = np.asarray(points, dtype=float)
    if array.ndim != 2 or array.shape[1] != 2:
        raise HomographyError(f"{label} must be a sequence of 2D points")
    if not np.isfinite(array).all():
        raise HomographyError(f"{label} must contain only finite numeric coordinates")
    return array


def _as_homography(homography: Sequence[Sequence[float]] | np.ndarray) -> np.ndarray:
    """把传入的矩阵转成 numpy 数组，并校验它确实是 3×3、元素都有限。"""
    matrix = np.asarray(homography, dtype=float)
    if matrix.shape != (3, 3):
        raise HomographyError("homography must be a 3x3 matrix")
    if not np.isfinite(matrix).all():
        raise HomographyError("homography must contain only finite numeric values")
    return matrix


def _normalize_homography(homography: np.ndarray) -> np.ndarray:
    """
    把单应性矩阵"归一化"：让右下角元素 h[2,2] 变成 1。

    齐次坐标下，整个矩阵乘同一个非零常数，表示的变换不变。
    所以统一除以 h[2,2]，让它表示更规范、后续计算更稳定。
    """
    if abs(float(homography[2, 2])) < 1e-12:
        raise HomographyError("homography normalization failed")
    return homography / homography[2, 2]


def compute_homography(image_points: Sequence[PointLike], court_points: Sequence[PointLike]) -> np.ndarray:
    """用 OpenCV 的 RANSAC 计算"图像像素 → 球场坐标"的单应性矩阵。"""

    # 把两组点都转成 float32 的 numpy 数组（OpenCV 要求 float32）
    src = _as_points(image_points, "image_points").astype(np.float32)
    dst = _as_points(court_points, "court_points").astype(np.float32)

    # 两组点数量必须一致，且至少 4 对（解 8 个未知量需要 ≥4 对）
    if len(src) != len(dst):
        raise HomographyError("image_points and court_points must have the same length")
    if len(src) < 4:
        raise HomographyError("at least four point correspondences are required")
    # 去重后也要 ≥4 个，避免给了重复点导致退化
    if np.unique(src, axis=0).shape[0] < 4 or np.unique(dst, axis=0).shape[0] < 4:
        raise HomographyError("point correspondences must include at least four unique points")

    # 延迟导入 OpenCV（只有真要算的时候才需要）
    try:
        import cv2  # type: ignore
    except ImportError as exc:
        raise HomographyError("OpenCV is required to compute homography") from exc

    # cv2.findHomography：用 RANSAC 鲁棒估计 H，能容忍少量错误对应点（离群点）。
    # 返回 (矩阵, 内点掩码)。RANSAC 会挑出"大多数点都支持"的那组解。
    matrix, inlier_mask = cv2.findHomography(src, dst, cv2.RANSAC)
    if matrix is None or matrix.shape != (3, 3):
        raise HomographyError("point correspondences are degenerate")
    # 内点数量也要 ≥4，否则这个 H 不可信
    if inlier_mask is not None and int(inlier_mask.sum()) < 4:
        raise HomographyError("homography requires at least four inlier correspondences")

    # 归一化后返回（用 float 精度的 numpy 数组）
    return _normalize_homography(np.asarray(matrix, dtype=float))


def _coerce_point_input(point_or_points: PointInput) -> tuple[np.ndarray, bool]:
    """
    把"一个点"或"一串点"统一整理成 (N×2 数组, 是否单点) 的形式。

    - 传入一维（如 [x, y]）→ 变成 1×2，并标记 is_single=True（之后返回单个点）；
    - 传入二维（如 [[x1,y1],[x2,y2]]）→ 直接用，is_single=False（返回列表）；
    - 其它维度或坐标非法 → 报错。
    """
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
    """
    核心：用单应性矩阵把点从"一个平面"变换到"另一个平面"。

    步骤（齐次坐标）：
    1. 每个点补一个 1，变成 (x, y, 1)；
    2. 矩阵乘法 H @ point，得到 (x', y', w')；
    3. 除以 w' 还原成 (x'/w', y'/w')。
    如果 w' 接近 0，说明是"无穷远点"，无法投影，直接报错。
    """
    matrix = _as_homography(homography)
    points, is_single = _coerce_point_input(point_or_points)
    # 给每个点补第 3 维（全是 1），得到齐次坐标
    homogeneous = np.column_stack([points, np.ones(len(points), dtype=float)])
    # 矩阵乘法：H 乘以齐次坐标（注意转置以对齐维度）
    projected = (matrix @ homogeneous.T).T

    # 检查有没有 w' ≈ 0 的非法点
    invalid = np.isclose(projected[:, 2], 0.0, atol=1e-12)
    if bool(invalid.any()):
        raise HomographyError("projected point has invalid homogeneous coordinate")

    # 除以 w' 还原成普通坐标
    transformed = projected[:, :2] / projected[:, 2:3]
    result = [(float(x), float(y)) for x, y in transformed]
    # 单个点就返回元组，多个点就返回列表
    return result[0] if is_single else result


def image_to_court(
    point_or_points: PointInput,
    homography: Sequence[Sequence[float]] | np.ndarray,
) -> tuple[float, float] | list[tuple[float, float]]:
    """
    像素坐标 → 球场坐标。

    注意：这里的 `homography` 必须是"图像→球场"方向的矩阵
    （即 compute_homography 算出来的那个）。
    """
    return _transform_points(point_or_points, homography)


def court_to_image(
    point_or_points: PointInput,
    inverse_homography: Sequence[Sequence[float]] | np.ndarray,
) -> tuple[float, float] | list[tuple[float, float]]:
    """
    球场坐标 → 像素坐标。

    注意：这里要传入"球场→图像"方向的矩阵，也就是 image_to_court 那个 H 的逆矩阵
    （用 np.linalg.inv(H) 求得）。
    """
    return _transform_points(point_or_points, inverse_homography)


def project_point(homography: Sequence[Sequence[float]], point: PointLike) -> tuple[float, float]:
    """
    便捷函数：投影单个点。

    无论传入 H 还是 H 的逆，本函数都是"用这个矩阵把 point 投影一次"。
    若结果是列表（理论上单个点不会），取第一个返回。
    """
    result = _transform_points(point, homography)
    if isinstance(result, list):
        return result[0]
    return result
