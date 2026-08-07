"""
掩码 → 关键点转换（mask_to_keypoints）。

自动标定的第二步：拿到球场线分割掩码后，从中提取出"球场的四个角点"
（左上 / 右上 / 右下 / 左下），作为标定的关键点（keypoints）。

思路：
1. 先清理掩码（形态学闭运算 + 膨胀，连上断线）；
2. 用霍夫变换找直线候选（horizontal/vertical）；
3. 若线足够，取最外圈的 2 横 2 竖，求交点得四角；
4. 线不够时，退回"最小外接矩形"取四角；
5. 最后算一个 0~1 的置信度，衡量这次提取靠不靠谱。
"""

# `from __future__ import annotations`：兼容较新类型写法。
from __future__ import annotations

# dataclass：数据类（详见 schemas.py 注释）。
from dataclasses import dataclass

# numpy：数值计算库。
import numpy as np

# 标定相关的数据结构（来自 schemas.calibration）。
from app.schemas.calibration import AutomaticCalibrationKeypoints, ImagePoint


@dataclass(frozen=True)
class LineCandidate:
    """一条被检测到的直线候选：极坐标参数 + 两个端点 + 朝向（horizontal/vertical）。"""

    rho: float
    theta: float
    points: tuple[tuple[int, int], tuple[int, int]]
    orientation: str


@dataclass(frozen=True)
class MaskToKeypointsResult:
    """掩码转关键点的结果：四角 keypoints + 置信度 + 掩码占比 + 线数 + 各线候选。"""

    keypoints: AutomaticCalibrationKeypoints
    confidence: float
    mask_area_ratio: float
    line_count: int
    lines: list[LineCandidate]


class MaskGeometryError(ValueError):
    """掩码几何处理相关的错误（继承自 ValueError）。"""

    pass


def mask_to_court_keypoints(
    mask: np.ndarray,
    min_area_ratio: float = 0.03,
) -> MaskToKeypointsResult:
    """
    主入口：从球场线掩码提取四角关键点。

    参数：
    - mask：分割得到的球场线掩码（H×W，线处非 0）；
    - min_area_ratio：掩码有效面积占整图比例的下限，太小说明球场线太稀疏、不可信。

    返回一个 MaskToKeypointsResult，包含四角和本次提取的置信度。
    """
    clean_mask = clean_court_line_mask(mask)
    height, width = clean_mask.shape[:2]
    if height <= 0 or width <= 0:
        raise MaskGeometryError("Mask has invalid dimensions")

    # 球场线占整图的比例（太稀疏说明识别失败）
    mask_area_ratio = float(np.count_nonzero(clean_mask)) / float(width * height)
    if mask_area_ratio < min_area_ratio:
        raise MaskGeometryError("Court-line mask is too sparse")

    # 找直线候选
    lines = extract_line_candidates(clean_mask)
    if len(lines) < 4:
        # 线不够 4 条：退回"最小外接矩形"取四角
        keypoints = _contour_keypoints(clean_mask)
        confidence = _quadrilateral_confidence(keypoints, width, height, mask_area_ratio, line_count=len(lines))
        return MaskToKeypointsResult(
            keypoints=keypoints,
            confidence=confidence,
            mask_area_ratio=mask_area_ratio,
            line_count=len(lines),
            lines=lines,
        )

    # 把线按朝向分开，并各自按位置(rho)排序
    horizontal = sorted([line for line in lines if line.orientation == "horizontal"], key=lambda line: line.rho)
    vertical = sorted([line for line in lines if line.orientation == "vertical"], key=lambda line: line.rho)
    if len(horizontal) < 2 or len(vertical) < 2:
        # 横/竖不足 2 条，同样退回外接矩形
        keypoints = _contour_keypoints(clean_mask)
        confidence = _quadrilateral_confidence(keypoints, width, height, mask_area_ratio, line_count=len(lines))
        return MaskToKeypointsResult(
            keypoints=keypoints,
            confidence=confidence,
            mask_area_ratio=mask_area_ratio,
            line_count=len(lines),
            lines=lines,
        )

    # 取最外圈的两条横线和两条竖线（即球场的四条边）
    top_line = horizontal[0]
    bottom_line = horizontal[-1]
    left_line = vertical[0]
    right_line = vertical[-1]
    corners = [
        _intersect(left_line, top_line),  # 左上
        _intersect(right_line, top_line),  # 右上
        _intersect(right_line, bottom_line),  # 右下
        _intersect(left_line, bottom_line),  # 左下
    ]
    if any(point is None for point in corners):
        # 有交点算不出（平行线）→ 退回外接矩形
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
    """
    清理掩码：把断断续续的线连起来、稍微加粗，便于后续找直线。

    用 OpenCV 的"闭运算"（先膨胀后腐蚀，补上缝隙）+ 一次膨胀。
    没有 OpenCV 就退回原始二值掩码。
    """
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
    """用霍夫变换从掩码里提取直线候选。"""
    try:
        import cv2  # type: ignore
    except ImportError:
        return []

    # 1) Canny 边缘检测，得到线状边缘
    edges = cv2.Canny(mask, 50, 150, apertureSize=3)
    # 最短线长：至少占短边的 15%
    min_length = max(24, int(min(mask.shape[:2]) * 0.15))
    # 2) 概率霍夫变换找线段
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
        # 判断朝向：|dx| >= |dy| 算水平线，否则竖直线
        orientation = "horizontal" if abs(dx) >= abs(dy) else "vertical"
        if orientation == "horizontal":
            rho = float((y1 + y2) / 2.0)  # 用中点的 y 作为"水平位置"
            theta = float(np.arctan2(dy, dx))
        else:
            rho = float((x1 + x2) / 2.0)  # 用中点的 x 作为"垂直位置"
            theta = float(np.arctan2(dy, dx))
        candidates.append(LineCandidate(rho=rho, theta=theta, points=((x1, y1), (x2, y2)), orientation=orientation))

    # 3) 去掉重复/过近的线
    return _dedupe_lines(candidates, mask.shape)


def _dedupe_lines(lines: list[LineCandidate], shape: tuple[int, ...]) -> list[LineCandidate]:
    """
    对直线去重：同一朝向上、位置(rho)很接近的多条线，归为一组，每组只保留最长的一条。

    tolerance 是"算作同一条线"的位置容差（短边的 3.5% 或至少 8 像素）。
    """
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
    """计算一条线段的长度（欧氏距离）。"""
    (x1, y1), (x2, y2) = line.points
    return float(np.hypot(x2 - x1, y2 - y1))


def _intersect(line_a: LineCandidate, line_b: LineCandidate) -> tuple[float, float] | None:
    """
    计算两条线段所在直线的交点（解析几何的两根直线相交公式）。

    若分母为 0（两直线平行）→ 返回 None。
    """
    (x1, y1), (x2, y2) = line_a.points
    (x3, y3), (x4, y4) = line_b.points
    denominator = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(float(denominator)) < 1e-9:
        return None
    px = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / denominator
    py = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / denominator
    return float(px), float(py)


def _contour_keypoints(mask: np.ndarray) -> AutomaticCalibrationKeypoints:
    """
    退化方案：当直线不够时，用"最小外接矩形"从掩码轮廓提取四角。

    步骤：找轮廓 → 所有轮廓点合并 → 求最小面积矩形 → 取其四个角点。
    """
    try:
        import cv2  # type: ignore
    except ImportError as exc:
        raise MaskGeometryError("OpenCV is required for mask geometry extraction") from exc

    contours, _hierarchy = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise MaskGeometryError("Court-line mask has no contours")

    points = np.vstack(contours).reshape(-1, 2).astype(np.float32)
    rect = cv2.minAreaRect(points)  # 最小面积外接矩形（旋转矩形）
    box = cv2.boxPoints(rect)  # 取出四个角点
    return _ordered_points_to_keypoints([(float(x), float(y)) for x, y in box])


def _ordered_points_to_keypoints(points: list[tuple[float, float]]) -> AutomaticCalibrationKeypoints:
    """
    把 4 个点整理成"有序的四角"（左上/右上/右下/左下）的 AutomaticCalibrationKeypoints。

    AutomaticCalibrationKeypoints 要求四个角都给 ImagePoint（x, y）。
    """
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
    """
    把 4 个无序点排成"左上 → 右上 → 右下 → 左下"的顺序。

    技巧：
    - 坐标和(x+y) 最小的是左上，最大的是右下；
    - 坐标差(y-x) 最小的是右上，最大的是左下。
    """
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
    """
    给提取出的四边形四角打分（0~1），评估这次标定候选的可靠程度。

    检查项：
    1. 坐标都必须是有限数；
    2. 四角不能超出画面边界太离谱（±10%）；
    3. 四边形面积占整图比例不能太小（<8% 视为退化）；
    4. 四条边长度都要 >1（不能塌成线/点）。

    最终分数综合：对边长度平衡(35%) + 邻边高度平衡(20%) + 线数(20%) + 面积比(15%) + 掩码占比(10%)。
    """
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
    return float(
        max(
            0.0,
            min(
                1.0,
                0.35 * opposite_balance
                + 0.2 * height_balance
                + 0.2 * line_score
                + 0.15 * area_score
                + 0.1 * mask_score,
            ),
        )
    )


def _polygon_area(points: np.ndarray) -> float:
    """
    用"鞋带公式"（Shoelace formula）计算多边形面积。

    对任意简单多边形都适用：叉积求和再除以 2 取绝对值。
    """
    x = points[:, 0]
    y = points[:, 1]
    return float(abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2.0)


def _as_binary_mask(mask: np.ndarray) -> np.ndarray:
    """
    把任意掩码规整成 0/255 的二值图。

    - 若是彩色(3 维)，先取各通道最大值压成单通道；
    - 再 >0 的部分置 255，其余 0。
    """
    array = np.asarray(mask)
    if array.ndim == 3:
        array = array.max(axis=2)
    return (array > 0).astype(np.uint8) * 255
