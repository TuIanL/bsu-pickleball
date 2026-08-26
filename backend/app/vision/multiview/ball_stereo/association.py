"""Cross-view ball association（球 3D：跨视角候选关联）。

D3：几何用于帮助挑选（ranking），硬门只卡物理合理性；epipolar/回投残差只用于排序，
不因不完美虚拟相机 hard-reject 真实球。关联只消费 frame_status=="available" 的真实观测（由调用方保证）。
执行序：detect/filter → snapshot 本地 predictor → stereo association → local tracker update。
本模块不反向修改 BallTracker 状态。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

import numpy as np

from app.vision.pickleball_game_analysis.ball_quality_gate import (
    BallQualityGateConfig,
    evaluate_pair_quality,
)
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
    quality_label: str = "rejected"
    anchor_eligible: bool = False
    quality_components: dict[str, Any] = field(default_factory=dict)
    stereo_measurement: Any | None = None


@dataclass
class AssociationWeights:
    """排序权重（相对值，几何帮助挑选而非硬 reject）。"""

    reproj_weight: float = 1.0
    epipolar_weight: float = 1.0
    continuity_weight: float = 0.8
    confidence_weight: float = 0.3
    scale_weight: float = 0.2
    direction_weight: float = 0.25


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
    scale_consistency: float = 0.5,
    direction_consistency: float = 0.5,
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
        + weights.scale_weight * scale_consistency
        + weights.direction_weight * direction_consistency
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
    cam1_scale_consistency: float = 0.5,
    cam2_scale_consistency: float = 0.5,
    cam1_direction_consistency: float = 0.5,
    cam2_direction_consistency: float = 0.5,
    previous_xyz: tuple[float, float, float] | None = None,
    max_trusted_reprojection_px: float = 24.0,
    weights: AssociationWeights = _ASSOCIATION_DEFAULTS,
) -> list[AssociatedPair]:
    """跨视角关联：先物理硬门，再按质量排序并计算权威 pair 资格。

    低质量 pair 仍返回给 diagnostic，但只有通过共享质量门且与次优
    pair 有足够分差的结果才会被标记为 ``anchor_eligible``。
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
                results.append(
                    AssociatedPair(cand1, cand2, 0.0, passes_hard_gate=False, rejection_reason=reason)
                )
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
            path_continuity = previous_path_continuity
            if previous_xyz is not None:
                distance_ft = math.sqrt(sum((float(xyz[i]) - previous_xyz[i]) ** 2 for i in range(3)))
                path_continuity = max(path_continuity, max(0.0, 1.0 - distance_ft / 12.0))
            scale_consistency = 0.5 * (cam1_scale_consistency + cam2_scale_consistency)
            direction_consistency = 0.5 * (cam1_direction_consistency + cam2_direction_consistency)
            score = rank_pair(
                cam1_confidence=cand1[2], cam2_confidence=cand2[2],
                measurement_reproj_cam1_px=measurement.reprojection_error_cam1_px,
                measurement_reproj_cam2_px=measurement.reprojection_error_cam2_px,
                epipolar_px=measurement.epipolar_residual_px,
                continuity=continuity,
                previous_path_continuity=path_continuity,
                scale_consistency=scale_consistency,
                direction_consistency=direction_consistency,
                weights=weights,
            )
            max_residual = max(
                measurement.reprojection_error_cam1_px,
                measurement.reprojection_error_cam2_px,
                measurement.epipolar_residual_px,
            )
            anchor_eligible = (
                max_residual <= max_trusted_reprojection_px
                and measurement.geometry_quality >= 0.4
                and measurement.depth_valid
            )
            components = {
                "reprojection_error_px": round(max_residual, 4),
                "geometry_quality": round(measurement.geometry_quality, 4),
                "tracker_continuity": round(continuity, 4),
                "previous_path_continuity": round(path_continuity, 4),
                "scale_consistency": round(scale_consistency, 4),
                "direction_consistency": round(direction_consistency, 4),
            }
            results.append(
                AssociatedPair(
                    cand1,
                    cand2,
                    score,
                    passes_hard_gate=True,
                    rejection_reason=None,
                    quality_label="trusted_anchor" if anchor_eligible else "low_quality_audit_only",
                    anchor_eligible=anchor_eligible,
                    quality_components=components,
                    stereo_measurement=measurement,
                )
            )

    passed = [r for r in results if r.passes_hard_gate]
    passed.sort(key=lambda r: r.score, reverse=True)
    quality_config = BallQualityGateConfig(
        max_reprojection_error_px=max_trusted_reprojection_px,
        min_pair_score_margin=0.08,
        court_margin_ft=court_margin_ft,
    )
    qualified: list[AssociatedPair] = []
    for index, pair in enumerate(passed):
        # 重新三角化只用于质量评估；正式 measurement 仍由 canonical runner
        # 在选出唯一可信 pair 后生成，避免低质量 pair 进入权威证据。
        try:
            xyz = triangulate_linear(
                projection_cam1,
                projection_cam2,
                pair.cam1_candidate[:2],
                pair.cam2_candidate[:2],
            )
            take = (cam1_timestamp_ms + cam2_timestamp_ms) / 2.0
            measurement = pair.stereo_measurement or measure_stereo(
                projection_cam1=projection_cam1,
                projection_cam2=projection_cam2,
                image_xy1=pair.cam1_candidate[:2],
                image_xy2=pair.cam2_candidate[:2],
                cam1_timestamp_ms=cam1_timestamp_ms,
                cam2_timestamp_ms=cam2_timestamp_ms,
                take_timestamp_ms=take,
                sync_error_ms=abs(cam1_timestamp_ms - cam2_timestamp_ms),
                max_time_delta_ms=max_time_gate_ms,
            )
            max_residual = max(
                measurement.reprojection_error_cam1_px,
                measurement.reprojection_error_cam2_px,
                measurement.epipolar_residual_px,
            )
            decision = evaluate_pair_quality(
                timestamp_delta_ms=abs(cam1_timestamp_ms - cam2_timestamp_ms),
                reprojection_error_px=max_residual,
                geometry_quality=measurement.geometry_quality,
                depth_valid=measurement.depth_valid,
                xyz=xyz,
                score=pair.score,
                next_best_score=passed[index + 1].score if index + 1 < len(passed) else None,
                previous_xyz=previous_xyz,
                config=quality_config,
                max_time_delta_ms=max_time_gate_ms,
                court_width_ft=max_court_x_ft,
                court_length_ft=max_court_y_ft,
            )
        except (ValueError, FloatingPointError, np.linalg.LinAlgError):
            decision = None
        if decision is None:
            qualified.append(pair)
            continue
        anchor_eligible = decision.accepted
        qualified.append(
            AssociatedPair(
                pair.cam1_candidate,
                pair.cam2_candidate,
                pair.score,
                passes_hard_gate=pair.passes_hard_gate,
                rejection_reason=None if anchor_eligible else decision.reason,
                quality_label="trusted_anchor" if anchor_eligible else "low_quality_audit_only",
                anchor_eligible=anchor_eligible,
                quality_components={
                    **dict(pair.quality_components),
                    "quality_gate_reason": decision.reason,
                    "score_margin": (
                        pair.score - passed[index + 1].score if index + 1 < len(passed) else None
                    ),
                },
                stereo_measurement=measurement,
            )
        )
    return qualified
