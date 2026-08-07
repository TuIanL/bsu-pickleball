"""观测质量（quality）—— ViewIntrinsicQuality 与 PairConsistency 分离。

- **ViewIntrinsicQuality**：某一路自身的质量。确定性规则，非训练模型。
  特征：detector confidence / normalized bbox height（`bbox_height / frame_height`）/
  projection confidence / footpoint method / tracking state / calibration quality /
  sync selection error。bbox 用归一化尺寸，不使用原始像素面积（不同分辨率/zoom/裁切下不可比）。
  render v2 无 bbox 字段时该特征缺省，不参与权重（Spike 第一轮即可用）。
- **PairConsistency**：两路之间的成对关系：inter-view distance / residual to
  predicted global position / association cost。pairwise 不混入 intrinsic。
- 决策输入 = `ViewIntrinsicQuality + PairConsistency + Global prediction`。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.vision.multiview.types import CanonicalObservation

# 脚点方法的质量权重（方法越可靠权重越高）。
FOOTPOINT_METHOD_QUALITY: dict[str, float] = {
    "bbox_bottom_center": 0.7,
    "ankle": 0.9,
    "pose_ankle": 0.9,
    "pose_foot": 0.85,
}

# 跟踪状态的质量权重。
TRACKING_STATUS_QUALITY: dict[str, float] = {
    "detected": 1.0,
    "tentative": 0.7,
    "interpolated": 0.2,
    "unmatched": 0.4,
    "lost": 0.1,
    "inactive": 0.1,
}

# 近端球员归一化 bbox 高度的参考值（占帧高比例），达到该值计 1.0。
NORMALIZED_BBOX_REFERENCE = 0.12

# sync 选择误差阈值（秒）：超过则显著降权。
SYNC_SELECTION_ERROR_S_THRESHOLD = 1.0 / 30.0


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


@dataclass(frozen=True)
class IntrinsicFeatures:
    """某一路观测的 intrinsic 特征（全部可缺省，缺失的特征不参与权重）。"""

    detector_confidence: float = 0.0
    bbox_height_px: float | None = None
    frame_height_px: float | None = None
    projection_confidence: float | None = None
    footpoint_method: str | None = None
    tracking_status: str = "detected"
    is_interpolated: bool = False
    calibration_quality: str = "ok"
    sync_selection_error_s: float | None = None


def intrinsic_from_canonical(obs: CanonicalObservation | None) -> IntrinsicFeatures:
    """从 canonical 观测构造 intrinsic 特征（不可用/缺失 → 低质量 lost）。"""
    if obs is None or obs.view_status != "available":
        return IntrinsicFeatures(tracking_status="lost")
    return IntrinsicFeatures(
        detector_confidence=obs.detector_confidence or 0.0,
        projection_confidence=obs.projection_confidence,
        footpoint_method=obs.footpoint_method,
        tracking_status=obs.tracking_status or "detected",
        is_interpolated=obs.is_interpolated,
    )


def normalized_bbox_score(bbox_height_px: float, frame_height_px: float) -> float:
    """归一化 bbox 高度质量分：`bbox_height / frame_height` 相对参考值。"""
    if frame_height_px <= 0 or bbox_height_px <= 0:
        return 0.0
    normalized = bbox_height_px / frame_height_px
    return _clamp01(normalized / NORMALIZED_BBOX_REFERENCE)


def view_intrinsic_quality(features: IntrinsicFeatures) -> float:
    """确定性单视角质量评分（0..1）。

    带权平均 + 惩罚项：
    - detector confidence / normalized bbox / projection confidence / footpoint /
      tracking 加权平均；
    - interpolated 观测整体乘以 0.2（不作为独立证据）；
    - calibration warning 乘 0.85；
    - sync selection error 超阈值乘 0.6。
    """
    scores: list[float] = []
    weights: list[float] = []

    scores.append(_clamp01(features.detector_confidence))
    weights.append(0.3)

    if features.bbox_height_px is not None and features.frame_height_px is not None:
        scores.append(normalized_bbox_score(features.bbox_height_px, features.frame_height_px))
        weights.append(0.3)

    if features.projection_confidence is not None:
        scores.append(_clamp01(features.projection_confidence))
        weights.append(0.2)

    scores.append(FOOTPOINT_METHOD_QUALITY.get(features.footpoint_method or "", 0.5))
    weights.append(0.1)

    scores.append(TRACKING_STATUS_QUALITY.get(features.tracking_status, 0.5))
    weights.append(0.1)

    weighted = sum(s * w for s, w in zip(scores, weights, strict=False)) / sum(weights)

    if features.is_interpolated:
        weighted *= 0.2
    if features.calibration_quality == "warning":
        weighted *= 0.85
    if (
        features.sync_selection_error_s is not None
        and features.sync_selection_error_s > SYNC_SELECTION_ERROR_S_THRESHOLD
    ):
        weighted *= 0.6

    return _clamp01(weighted)


@dataclass(frozen=True)
class PairConsistencyResult:
    """两路观测的成对一致性。"""

    inter_view_distance_ft: float | None
    residual_to_prediction_ft: float | None
    association_cost: float | None
    consistency: float  # 0..1，1 = 完全一致


def pair_consistency(
    ref_canonical: tuple[float, float] | None,
    sec_canonical: tuple[float, float] | None,
    predicted: tuple[float, float] | None,
    max_plausible_distance_ft: float,
) -> PairConsistencyResult:
    """计算两路成对一致性（不混入任何单视角 intrinsic 特征）。

    - 双观测：inter-view distance 主导；
    - 单观测：residual to predicted 主导；
    - 无观测：consistency = 0。
    """
    inter_view = None
    if ref_canonical is not None and sec_canonical is not None:
        inter_view = _distance(ref_canonical, sec_canonical)

    residual = None
    if predicted is not None:
        candidates: list[float] = []
        if ref_canonical is not None:
            candidates.append(_distance(ref_canonical, predicted))
        if sec_canonical is not None:
            candidates.append(_distance(sec_canonical, predicted))
        if candidates:
            residual = min(candidates)

    consistency = 0.0
    if inter_view is not None:
        consistency = _clamp01(1.0 - inter_view / max_plausible_distance_ft)
    elif residual is not None:
        consistency = _clamp01(1.0 - residual / max_plausible_distance_ft)

    return PairConsistencyResult(
        inter_view_distance_ft=inter_view,
        residual_to_prediction_ft=residual,
        association_cost=inter_view if inter_view is not None else residual,
        consistency=consistency,
    )


def fusion_weights(
    ref_intrinsic: float,
    sec_intrinsic: float,
    consistency: float,
    *,
    degraded_sync: bool = False,
) -> tuple[float, float]:
    """由 intrinsic + consistency 计算两路融合权重（和为 1）。

    一致性越低，越向高质量观测收拢（避免把冲突平均成中间点）。
    `degraded_sync=True` 时降低时间同步信任，进一步依赖较高 intrinsic 的一路。
    """
    if ref_intrinsic <= 0 and sec_intrinsic <= 0:
        return (0.5, 0.5)
    ref_w = ref_intrinsic
    sec_w = sec_intrinsic
    if consistency < 0.5:
        # 冲突场景：向更可信的一路倾斜。
        if ref_w > sec_w:
            ref_w *= 1.0 + (0.5 - consistency)
            sec_w *= 1.0 - (0.5 - consistency)
        else:
            sec_w *= 1.0 + (0.5 - consistency)
            ref_w *= 1.0 - (0.5 - consistency)
    if degraded_sync:
        ref_w, sec_w = (max(ref_w, 0.55), min(sec_w, 0.45)) if ref_w > sec_w else (min(ref_w, 0.45), max(sec_w, 0.55))
    total = ref_w + sec_w
    if total <= 0:
        return (0.5, 0.5)
    return (ref_w / total, sec_w / total)


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
