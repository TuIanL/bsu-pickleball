"""Reference line support 诊断 —— 基于标准匹克球场线投影验证自动标定候选质量。

本文件解决的问题：自动标定（分割模型→掩码→四角点）给出的单应性是否可靠？
不能只看四角点对不对，还要看"整张球场线"是否和预测掩码吻合。

计算流程：
1. 从自动标定 keypoints 计算 court-to-image 单应性（使用 inverse homography）
2. 将标准匹克球场线（9 条）投影回图像
3. 对预测 mask 做距离变换，评估每条 projected line 的像素级支持度
4. 汇总 reference_score、coverage、supported_lines、rejection reasons
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from app.schemas.calibration import (
    AutomaticCalibrationKeypoints,
    ConfidenceBreakdown,
    ReferenceLineDiagnostics,
)
from app.vision.courtvision_calibration_engine.court_geometry import (
    PickleballCourtGeometry,
    standard_court,
)
from app.vision.courtvision_calibration_engine.homography import compute_homography


@dataclass(frozen=True)
class ReferenceLineResult:
    """单条球线投影后的支持度评估。"""
    line_name: str                          # 该球线名称（如 "baseline_left"）
    start_image: tuple[int, int]            # 投影回图像后的起点像素坐标 (x, y)
    end_image: tuple[int, int]              # 投影回图像后的终点像素坐标 (x, y)
    support_ratio: float                    # 沿线采样点落在 mask 上的比例（0~1）
    sample_count: int                       # 沿线采样点数


@dataclass
class ReferenceDiagnosticResult:
    """reference line support 的完整诊断结果。"""
    reference_score: float                     # 0.0 ~ 1.0，综合可信度评分
    coverage: float                            # 9 条线中有支持度的比例
    supported_lines: int                       # support_ratio >= threshold 的线数
    total_lines: int                           # 总投影线数（固定 9）
    line_results: list[ReferenceLineResult]    # 每条线的详细结果
    rejection_reasons: list[str] = field(default_factory=list)  # 不通过的原因列表
    summary: str = ""                          # 一句话汇总


# 容忍像素：projected line 上采样点距离 mask 轮廓的允许偏差
DEFAULT_TOLERANCE_PX = 12.0

# reference score 低于此值时可作为 rejection reason（整体不可信）
DEFAULT_REFERENCE_REJECT_THRESHOLD = 0.25

# 单条线 support_ratio 低于此值时被认为"不支持"
DEFAULT_LINE_SUPPORT_THRESHOLD = 0.15


def compute_reference_line_support(
    mask: np.ndarray,
    keypoints: AutomaticCalibrationKeypoints,
    court: PickleballCourtGeometry | None = None,
    tolerance_px: float = DEFAULT_TOLERANCE_PX,
    line_support_threshold: float = DEFAULT_LINE_SUPPORT_THRESHOLD,
    reference_reject_threshold: float = DEFAULT_REFERENCE_REJECT_THRESHOLD,
) -> ReferenceDiagnosticResult:
    """计算 reference line support 诊断。

    参数：
    - mask：自动标定模型输出的球场线二值掩码（前景=球场线）
    - keypoints：自动标定得到的四角点（图像像素坐标）
    - court：标准球场几何（默认用 standard_court()，即 20×44 英尺标准场）
    """
    import cv2

    court = court or standard_court()
    binary_mask = _as_binary(mask)

    # 距离变换：对掩码做"每个像素到最近前景（球场线）的欧氏距离"。
    # 之后判断投影线采样点到球场线的距离是否落在容忍范围内就很快。
    dist = cv2.distanceTransform(binary_mask, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)

    # 从 keypoints 计算 court-to-image homography：
    # 我们用"图像四角点" + "球场坐标系四角 (0,0)-(20,0)-(20,44)-(0,44)" 求单应性，
    # 然后取逆矩阵得到 court->image 的映射（把球场坐标投回图像）。
    image_points = [
        (keypoints.top_left.x, keypoints.top_left.y),
        (keypoints.top_right.x, keypoints.top_right.y),
        (keypoints.bottom_right.x, keypoints.bottom_right.y),
        (keypoints.bottom_left.x, keypoints.bottom_left.y),
    ]
    court_points = [
        (0.0, 0.0),
        (20.0, 0.0),
        (20.0, 44.0),
        (0.0, 44.0),
    ]
    try:
        h_image_to_court = compute_homography(image_points, court_points)
        h_court_to_image = np.linalg.inv(h_image_to_court)
    except Exception:
        # 单应性算不出来（比如四点共线），直接判为不可信
        return ReferenceDiagnosticResult(
            reference_score=0.0,
            coverage=0.0,
            supported_lines=0,
            total_lines=len(court.lines),
            line_results=[],
            rejection_reasons=["homography_failed"],
            summary="Homography computation failed; reference line projection is unavailable",
        )

    # 逐条球场线：投影回图像后，用距离图评估支持度
    line_results: list[ReferenceLineResult] = []
    for line in court.lines:
        result = _evaluate_line(line, h_court_to_image, dist, tolerance_px)
        line_results.append(result)

    # 统计"被支持"的线数和覆盖率
    supported = sum(1 for r in line_results if r.support_ratio >= line_support_threshold)
    coverage = supported / len(line_results) if line_results else 0.0

    # reference_score 由"平均支持度"(权重1.5) + "覆盖率"(权重0.3) 组合后夹到 0~1
    if line_results:
        mean_support = float(np.mean([r.support_ratio for r in line_results]))
        reference_score = float(max(0.0, min(1.0, mean_support * 1.5 + coverage * 0.3)))
    else:
        reference_score = 0.0

    rejection_reasons: list[str] = []
    if reference_score < reference_reject_threshold:
        rejection_reasons.append(
            f"reference_score ({reference_score:.2f}) 低于下限 ({reference_reject_threshold:.2f})"
        )

    summary_parts = [
        f"reference_score={reference_score:.2f}",
        f"supported={supported}/{len(court.lines)} lines",
        f"coverage={coverage:.2f}",
    ]
    if rejection_reasons:
        summary_parts.append(f"rejected: {rejection_reasons[0]}")

    return ReferenceDiagnosticResult(
        reference_score=reference_score,
        coverage=coverage,
        supported_lines=supported,
        total_lines=len(court.lines),
        line_results=line_results,
        rejection_reasons=rejection_reasons,
        summary="; ".join(summary_parts),
    )


def build_confidence_breakdown(
    segmentation_confidence: float,
    geometry_confidence: float,
    reference_score: float,
    combined_confidence: float,
) -> ConfidenceBreakdown:
    """把三个分项置信度与综合置信度打包成 schema 的 ConfidenceBreakdown。"""
    return ConfidenceBreakdown(
        segmentation=round(segmentation_confidence, 4),
        geometry=round(geometry_confidence, 4),
        reference=round(reference_score, 4),
        combined=round(combined_confidence, 4),
    )


def build_reference_diagnostics(result: ReferenceDiagnosticResult) -> ReferenceLineDiagnostics:
    """把内部 ReferenceDiagnosticResult 转成对外 schema 的 ReferenceLineDiagnostics。"""
    return ReferenceLineDiagnostics(
        reference_score=round(result.reference_score, 4),
        coverage=round(result.coverage, 4),
        supported_lines=result.supported_lines,
        total_lines=result.total_lines,
        tolerance_px=DEFAULT_TOLERANCE_PX,
        line_count_supported=result.supported_lines,
        passing_line_names=[
            r.line_name for r in result.line_results
            if r.support_ratio >= DEFAULT_LINE_SUPPORT_THRESHOLD
        ],
        rejection_reason=result.rejection_reasons[0] if result.rejection_reasons else None,
        summary=result.summary,
    )


def _evaluate_line(
    line,
    h_court_to_image: np.ndarray,
    distance_map: np.ndarray,
    tolerance_px: float,
) -> ReferenceLineResult:
    """把单条球场线从 court 坐标投影到图像，沿线采样并统计落在掩码上的比例。"""
    import cv2

    from app.vision.courtvision_calibration_engine.court_overlay import _project_point as project_court_point

    # 用 court_overlay 的投影函数把线两端投到图像像素
    start_img = project_court_point(line.start, h_court_to_image)
    end_img = project_court_point(line.end, h_court_to_image)

    # 按像素长度决定采样点数（每约 4 像素采一个，至少 4 点）
    length_px = float(np.hypot(end_img[1] - start_img[1], end_img[0] - start_img[0]))
    num_samples = max(4, int(length_px / 4.0))

    samples_hit = 0
    h, w = distance_map.shape[:2]

    # 沿线均匀插值采样，查看每个采样点到最近球场线的距离是否 <= 容忍值
    for i in range(num_samples):
        t = i / (num_samples - 1) if num_samples > 1 else 0.5
        px = int(round(start_img[0] + t * (end_img[0] - start_img[0])))
        py = int(round(start_img[1] + t * (end_img[1] - start_img[1])))

        if 0 <= px < w and 0 <= py < h:
            dist_val = distance_map[py, px]
            if dist_val <= tolerance_px:
                samples_hit += 1

    support_ratio = samples_hit / num_samples if num_samples > 0 else 0.0
    return ReferenceLineResult(
        line_name=line.name,
        start_image=start_img,
        end_image=end_img,
        support_ratio=float(support_ratio),
        sample_count=num_samples,
    )


def _as_binary(mask: np.ndarray) -> np.ndarray:
    """把任意形状的 mask 转成 0/1 的二值 uint8 数组。

    - 如果是 3 通道彩色，先取各通道最大值（当灰度）。
    - 大于 0 的都视为前景。
    """
    array = np.asarray(mask)
    if array.ndim == 3:
        array = array.max(axis=2)
    binary = (array > 0).astype(np.uint8)
    if binary.sum() == 0:
        return binary
    return binary
