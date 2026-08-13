"""Guided re-detection —— candidate PRE-GATE(在 tracker 之前) → merge → tracker.update ONCE。

invariant 9:pre-gate 拒绝的 guided detection 绝不触碰 tracker。
candidate 无需 track id:从 `Detection.bbox → 临时 footpoint → image_to_court → canonical residual`
先做 candidate validation。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.tracking import Detection
from app.vision.courtvision_calibration_engine.homography import image_to_court


@dataclass
class GuidedCandidate:
    """一个 guided detection 的 pre-gate 结果。"""

    detection: Detection
    image_footpoint: tuple[float, float]
    canonical_position: tuple[float, float]
    residual_ft: float
    accepted: bool
    reject_reason: str | None = None
    local_position: tuple[float, float] | None = None
    guidance_id: str | None = None
    expected_global_player_id: str | None = None
    donor_view: str | None = None
    donor_quality: float = 0.0
    recovery_episode_id: str | None = None


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def guided_candidate_pre_gate(
    detection: Detection,
    *,
    homography,
    predicted_canonical: tuple[float, float] | None = None,
    predicted_local: tuple[float, float] | None = None,
    max_residual_ft: float,
    frame_width: int,
    frame_height: int,
) -> GuidedCandidate:
    """对单个 guided detection 做 pre-gate(在 tracker 之前)。

    通过条件:bbox/image sanity + 可投影 + target-local residual <= max_residual_ft。

    ``predicted_canonical`` remains a compatibility alias for existing callers;
    joint recovery passes ``predicted_local`` explicitly.
    """
    x1, y1, x2, y2 = (float(v) for v in detection.bbox)
    # bbox / image sanity
    if x2 <= x1 or y2 <= y1:
        return GuidedCandidate(detection, (0.0, 0.0), (0.0, 0.0), float("inf"), False, "invalid_bbox", (0.0, 0.0))
    if x1 < -50 or y1 < -50 or x2 > frame_width + 50 or y2 > frame_height + 50:
        return GuidedCandidate(detection, (0.0, 0.0), (0.0, 0.0), float("inf"), False, "bbox_out_of_frame", (0.0, 0.0))
    foot = ((x1 + x2) / 2.0, y2)  # 底边中点临时脚点
    try:
        cx, cy = image_to_court(foot, homography)
    except Exception:
        return GuidedCandidate(detection, foot, (0.0, 0.0), float("inf"), False, "projection_failed", (0.0, 0.0))
    expected = predicted_local if predicted_local is not None else predicted_canonical
    if expected is None:
        return GuidedCandidate(detection, foot, (cx, cy), float("inf"), False, "missing_prediction", (cx, cy))
    residual = _dist((cx, cy), expected)
    accepted = residual <= max_residual_ft
    return GuidedCandidate(
        detection, foot, (cx, cy), residual, accepted,
        None if accepted else "residual_too_large",
        (cx, cy),
    )


def filter_accepted(candidates: list[GuidedCandidate]) -> list[Detection]:
    """只保留 pre-gate accepted 的 guided detections。"""
    return [c.detection for c in candidates if c.accepted]


def merge_base_and_guided(
    base: list[Detection],
    guided: list[Detection],
    iou_threshold: float = 0.5,
) -> list[Detection]:
    """把 accepted guided detections 与 base 合并去重(高度重叠的 guided 丢弃)。"""
    result: list[Detection] = list(base)
    for g in guided:
        dup = any(_iou(g.bbox, b.bbox) >= iou_threshold for b in result)
        if not dup:
            result.append(g)
    return result


def _iou(a: list[float], b: list[float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    inter = iw * ih
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0
