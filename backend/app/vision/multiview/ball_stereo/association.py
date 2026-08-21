"""Cross-view ball association（球 3D：跨视角候选关联）。

D3：几何用于帮助挑选（ranking），硬门只卡物理合理性；epipolar/回投残差只用于排序，
不因不完美虚拟相机 hard-reject 真实球。关联只消费 frame_status=="available" 的真实观测（由调用方保证）。
执行序：detect/filter → snapshot 本地 predictor → stereo association → local tracker update。
本模块不反向修改 BallTracker 状态。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Sequence

from app.vision.multiview.ball_stereo.stereo_measurement import (
    measure_stereo,
    triangulate_linear,
)

# 球候选的轻量视角观测（已过滤但未做唯一选择）
BallViewCandidate = tuple[float, float, float]  # (image_x, image_y, confidence)


@dataclass(frozen=True)
class AssociatedPair:
    """一对跨视角关联的候选，带评分。"""

    cam1_candidate: BallViewCandidate
    cam2_candidate: BallViewCandidate
    score: float
    passes_hard_gate: bool = False
    rejection_reason: str | None = None


@dataclass
class AssociationWeights:
    """排序权重（相对值，几何帮助挑选而非硬 reject）。"""

    reproj_weight: float = 1.0
    epipolar_weight: float = 1.0
    continuity_weight: float = 0.8
    confidence_weight: float = 0.3


_ASSOCIATION_DEFAULTS = AssociationWeights()


def _time_delta_small(cam1_timestamp_ms: float, cam2_timestamp_ms: float, max_gate_ms: float) -> bool:
    return abs(cam1_timestamp_ms - cam2_timestamp_ms) <= max_gate_ms


def hard_gate(
    *,
    projected_result,
    z: float,
    min_ground_z_ft: float,
    court_margin_ft: float,
) -> str | None:
    """物理合理性硬门。返回 rejection reason 或 None（通过）。

    z 不严重低于地面、位置不严重飞出球场环境。三角化位置"不荒谬"由回投误差体现。
    """
    if z < min_ground_z_ft:
        return "below_ground"
    if abs(z) > 50.0:
        return "z_absurd"
    if projected_result is None:
        return "out_of_court"
    return None


def rank_pair(
    *,
    cam1_confidence: float,
    cam2_confidence: float,
    measurement_reproj_cam1_px: float,
    measurement_reproj_cam2_px: float,
    epipolar_px: float,
    continuity: float,  # 来自本地 tracker pre-tick snapshot 的连续性（0..1）
    previous_path_continuity: float,  # 上一帧 3D 路径连续性（0..1）
    weights: AssociationWeights = _ASSOCIATION_DEFAULTS,
) -> float:
    """对一对候选打分（分数越高越好）。几何残差越低、连续性与置信度越高分越高。"""
    reproj = max(measurement_reproj_cam1_px, measurement_reproj_cam2_px, epipolar_px)
    q_geometry = max(0.0, 1.0 - reproj / 40.0)
    score = (
        weights.reproj_weight * q_geometry
        + weights.epipolar_weight * q_geometry
        + weights.continuity_weight * (0.5 * continuity + 0.5 * previous_path_continuity)
        + weights.confidence_weight * max(cam1_confidence, cam2_confidence)
    )
    return round(score, 4)


def associate_views(
    *,
    cam1_candidates: Sequence[BallViewCandidate],
    cam2_candidates: Sequence[BallViewCandidate],
    projection_cam1,
    projection_cam2,
    cam1_timestamp_ms: float,
    cam2_timestamp_ms: float,
    max_time_gate_ms: float = 40.0,
    min_ground_z_ft: float = -0.5,
    court_margin_ft: float = 6.0,
    max_court_x_ft: float = 20.0,
    max_court_y_ft: float = 44.0,
    cam1_continuity: float = 0.0,
    cam2_continuity: float = 0.0,
    previous_path_continuity: float = 0.0,
    weights: AssociationWeights = _ASSOCIATION_DEFAULTS,
) -> list[AssociatedPair]:
    """跨视角关联：先硬门，再排序。返回按 score 降序的通过硬门的配对。

    不做 epipolar 硬门槛——所有配对只要通过物理硬门就得分，由排序相对好坏。
    """
    if not _time_delta_small(cam1_timestamp_ms, cam2_timestamp_ms, max_time_gate_ms):
        return []

    results: list[AssociatedPair] = []
    for cand1 in cam1_candidates:
        for cand2 in cam2_candidates:
            # 三角化（几何不可用时跳过该配对）
            try:
                xyz = triangulate_linear(
                    projection_cam1, projection_cam2,
                    (cand1[0], cand1[1]), (cand2[0], cand2[1]),
                )
            except (ValueError, FloatingPointError):
                continue
            z = float(xyz[2])
            x, y = float(xyz[0]), float(xyz[1])

            reason = None
            if not (-court_margin_ft <= x <= max_court_x_ft + court_margin_ft):
                reason = "out_of_court"
            elif not (-court_margin_ft <= y <= max_court_y_ft + court_margin_ft):
                reason = "out_of_court"
            else:
                reason = hard_gate(
                    projected_result=(x, y), z=z,
                    min_ground_z_ft=min_ground_z_ft,
                    court_margin_ft=court_margin_ft,
                )
            if reason is not None:
                results.append(AssociatedPair(cand1, cand2, 0.0, passes_hard_gate=False, rejection_reason=reason))
                continue

            # 排序（几何帮助挑选）
            take = (cam1_timestamp_ms + cam2_timestamp_ms) / 2.0
            measurement = measure_stereo(
                projection_cam1=projection_cam1, projection_cam2=projection_cam2,
                image_xy1=(cand1[0], cand1[1]), image_xy2=(cand2[0], cand2[1]),
                cam1_timestamp_ms=cam1_timestamp_ms, cam2_timestamp_ms=cam2_timestamp_ms,
                take_timestamp_ms=take, sync_error_ms=abs(cam1_timestamp_ms - cam2_timestamp_ms),
                max_time_delta_ms=max_time_gate_ms,
            )
            continuity = max(cam1_continuity, cam2_continuity)
            score = rank_pair(
                cam1_confidence=cand1[2], cam2_confidence=cand2[2],
                measurement_reproj_cam1_px=measurement.reprojection_error_cam1_px,
                measurement_reproj_cam2_px=measurement.reprojection_error_cam2_px,
                epipolar_px=measurement.epipolar_residual_px,
                continuity=continuity,
                previous_path_continuity=previous_path_continuity,
                weights=weights,
            )
            results.append(AssociatedPair(cand1, cand2, score, passes_hard_gate=True, rejection_reason=None))

    passed = [r for r in results if r.passes_hard_gate]
    passed.sort(key=lambda r: r.score, reverse=True)
    return passed