"""观测质量 —— ViewIntrinsicQuality + PairConsistency 分离、bbox 归一化、插值降权。"""

from __future__ import annotations

import pytest

from app.vision.multiview.quality import (
    IntrinsicFeatures,
    PairConsistencyResult,
    fusion_weights,
    pair_consistency,
    view_intrinsic_quality,
)


def test_intrinsic_higher_features_higher_quality():
    low = view_intrinsic_quality(
        IntrinsicFeatures(detector_confidence=0.4, projection_confidence=0.5, footpoint_method="bbox_bottom_center")
    )
    high = view_intrinsic_quality(
        IntrinsicFeatures(detector_confidence=0.95, projection_confidence=0.9, footpoint_method="pose_ankle")
    )
    assert high > low


def test_intrinsic_bbox_normalized_across_resolutions():
    # 同一物理球员：4K(2160) 与 1080p 帧高不同，但 bbox 占比相同 → 质量近似。
    a = view_intrinsic_quality(
        IntrinsicFeatures(detector_confidence=0.8, bbox_height_px=200.0, frame_height_px=2160.0)
    )
    b = view_intrinsic_quality(
        IntrinsicFeatures(detector_confidence=0.8, bbox_height_px=100.0, frame_height_px=1080.0)
    )
    assert a == pytest.approx(b, abs=1e-6)

    # 但像素面积相同、分辨率不同 → 归一化后质量不同（原始像素不可比）。
    raw_big_px = view_intrinsic_quality(
        IntrinsicFeatures(detector_confidence=0.8, bbox_height_px=100.0, frame_height_px=2160.0)
    )
    raw_small_frame = view_intrinsic_quality(
        IntrinsicFeatures(detector_confidence=0.8, bbox_height_px=100.0, frame_height_px=1080.0)
    )
    assert raw_small_frame > raw_big_px  # 1080p 中 bbox 占比更高


def test_intrinsic_without_bbox_still_valid():
    # render v2 无 bbox 字段：缺省特征不参与权重，评分仍有效。
    score = view_intrinsic_quality(
        IntrinsicFeatures(detector_confidence=0.8, projection_confidence=0.7)
    )
    assert 0.0 <= score <= 1.0


def test_intrinsic_interpolated_downweighted():
    real = view_intrinsic_quality(
        IntrinsicFeatures(detector_confidence=0.8, tracking_status="detected")
    )
    interpolated = view_intrinsic_quality(
        IntrinsicFeatures(detector_confidence=0.8, tracking_status="interpolated", is_interpolated=True)
    )
    assert interpolated < real * 0.5


def test_metric_policy_accepts_only_explicitly_eligible_interpolation():
    from app.vision.multiview.consumers import metric_eligibility_policy

    assert metric_eligibility_policy("interpolated", metric_eligible_flag=True)
    assert not metric_eligibility_policy("interpolated", metric_eligible_flag=False)


def test_intrinsic_tracking_lost_low():
    detected = view_intrinsic_quality(IntrinsicFeatures(detector_confidence=0.8, tracking_status="detected"))
    lost = view_intrinsic_quality(IntrinsicFeatures(detector_confidence=0.8, tracking_status="lost"))
    assert lost < detected


def test_pair_consistency_dual_obs():
    result = pair_consistency((5.0, 8.0), (5.4, 8.2), (5.2, 8.1), max_plausible_distance_ft=3.0)
    assert isinstance(result, PairConsistencyResult)
    assert result.inter_view_distance_ft is not None
    assert pytest.approx(result.inter_view_distance_ft, abs=1e-6) == ((0.4**2 + 0.2**2) ** 0.5)
    assert 0.0 <= result.consistency <= 1.0


def test_pair_consistency_single_obs_uses_prediction():
    result = pair_consistency((5.0, 8.0), None, (5.6, 8.3), max_plausible_distance_ft=3.0)
    assert result.inter_view_distance_ft is None
    assert result.residual_to_prediction_ft is not None
    assert result.consistency > 0.0


def test_pair_consistency_no_obs_zero():
    result = pair_consistency(None, None, None, max_plausible_distance_ft=3.0)
    assert result.consistency == 0.0


def test_pair_consistency_large_disagreement_low_consistency():
    result = pair_consistency((5.0, 8.0), (15.0, 35.0), None, max_plausible_distance_ft=3.0)
    assert result.consistency == 0.0  # 远超阈值 → 完全不一致


def test_fusion_weights_prefers_higher_intrinsic():
    ref_w, sec_w = fusion_weights(0.9, 0.4, consistency=0.9)
    assert ref_w > sec_w
    assert pytest.approx(ref_w + sec_w, abs=1e-6) == 1.0


def test_fusion_weights_conflict_tilts_to_better_view():
    # 低一致性（冲突）→ 权重向高质量一路收拢。
    ref_w_low, sec_w_low = fusion_weights(0.4, 0.9, consistency=0.9)
    ref_w_high, sec_w_high = fusion_weights(0.4, 0.9, consistency=0.1)
    assert ref_w_high < ref_w_low  # 冲突时 ref（低质量）权重进一步降低
    assert sec_w_high > sec_w_low


def test_fusion_weights_degraded_sync_tilts_to_better_view():
    ref_w, sec_w = fusion_weights(0.8, 0.5, consistency=0.9, degraded_sync=True)
    assert ref_w > 0.5
