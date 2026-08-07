"""Position Fusion —— 状态机、conflict gate、metric eligibility；与融合管线端到端。"""

from __future__ import annotations

import pytest

from app.vision.multiview.fusion import FusionConfig, FusionMeasurement, fuse_observation
from app.vision.multiview.quality import PairConsistencyResult
from app.vision.multiview.types import CanonicalObservation


def _canon(view_id, x, y, status="available", frame=0, conf=0.8, proj_conf=0.7, method="pose_ankle"):
    return CanonicalObservation(
        view_id=view_id,
        view_status=status,
        source_frame_index=frame,
        source_timestamp_ms=frame / 30.0 * 1000.0,
        mapped_take_timestamp_ms=frame / 30.0 * 1000.0,
        selection_error_ms=0.0,
        canonical_x_ft=x,
        canonical_y_ft=y,
        view_player_id="",
        detector_confidence=conf,
        projection_confidence=proj_conf,
        footpoint_method=method,
        tracking_status="detected",
        is_interpolated=False,
    )


def _pair(ref, sec, max_plausible=3.0):
    ref_xy = (ref.canonical_x_ft, ref.canonical_y_ft) if ref and ref.view_status == "available" else None
    sec_xy = (sec.canonical_x_ft, sec.canonical_y_ft) if sec and sec.view_status == "available" else None
    return PairConsistencyResult(
        inter_view_distance_ft=(
            ((ref_xy[0] - sec_xy[0]) ** 2 + (ref_xy[1] - sec_xy[1]) ** 2) ** 0.5
            if ref_xy and sec_xy
            else None
        ),
        residual_to_prediction_ft=None,
        association_cost=None,
        consistency=1.0,
    )


_CONFIG = FusionConfig(conflict_distance_ft=3.0, max_plausible_distance_ft=3.0)


def test_fusion_dual_observed_weighted():
    ref = _canon("cam_1", 5.0, 8.0, conf=0.9)
    sec = _canon("cam_2", 5.4, 8.2, conf=0.4)
    result = fuse_observation(
        global_player_id="g1",
        timestamp_seconds=0.0,
        take_timestamp_ms=0.0,
        reference_frame_index=0,
        reference_obs=ref,
        secondary_obs=sec,
        reference_intrinsic=0.9,
        secondary_intrinsic=0.4,
        pair=_pair(ref, sec),
        predicted=(5.2, 8.1),
        sync_quality="good",
        config=_CONFIG,
    )
    assert result is not None
    assert result.fusion_status == "dual_observed"
    assert result.metric_eligible is True
    assert result.measurement_source == "dual"
    # 高质量 ref 权重大：x 更靠近 5.0 而非 5.4。
    assert result.x_ft < 5.2
    assert result.x_ft > 5.0


def test_fusion_single_view_fallback():
    ref = _canon("cam_1", 5.0, 8.0, conf=0.9)
    sec = _canon("cam_2", 5.4, 8.2, status="unavailable")
    result = fuse_observation(
        global_player_id="g1",
        timestamp_seconds=0.0,
        take_timestamp_ms=0.0,
        reference_frame_index=0,
        reference_obs=ref,
        secondary_obs=sec,
        reference_intrinsic=0.9,
        secondary_intrinsic=0.0,
        pair=_pair(ref, sec),
        predicted=None,
        sync_quality="good",
        config=_CONFIG,
    )
    assert result is not None
    assert result.fusion_status == "single_view_fallback"
    assert result.measurement_source == "reference"
    assert result.metric_eligible is True
    assert (result.x_ft, result.y_ft) == (5.0, 8.0)


def test_fusion_no_observation_returns_none():
    ref = _canon("cam_1", 5.0, 8.0, status="unavailable")
    sec = _canon("cam_2", 5.4, 8.2, status="unavailable")
    result = fuse_observation(
        global_player_id="g1",
        timestamp_seconds=0.0,
        take_timestamp_ms=0.0,
        reference_frame_index=0,
        reference_obs=ref,
        secondary_obs=sec,
        reference_intrinsic=0.0,
        secondary_intrinsic=0.0,
        pair=_pair(ref, sec),
        predicted=None,
        sync_quality="good",
        config=_CONFIG,
    )
    assert result is None


def test_fusion_conflict_not_averaged():
    ref = _canon("cam_1", 5.0, 8.0, conf=0.9)
    sec = _canon("cam_2", 15.0, 35.0, conf=0.4)  # 远离 ref
    result = fuse_observation(
        global_player_id="g1",
        timestamp_seconds=0.0,
        take_timestamp_ms=0.0,
        reference_frame_index=0,
        reference_obs=ref,
        secondary_obs=sec,
        reference_intrinsic=0.9,
        secondary_intrinsic=0.4,
        pair=_pair(ref, sec),
        predicted=(5.2, 8.1),
        sync_quality="good",
        config=_CONFIG,
    )
    assert result is not None
    assert result.fusion_status == "conflict"
    # 绝不平均成 (10, 21.5) 的不存在中间位置。
    assert result.x_ft != pytest.approx(10.0)
    # 选择高质量 ref 观测。
    assert result.selected_view == "reference"
    assert result.metric_eligible is True


def test_fusion_conflict_uses_prediction_when_both_unreliable():
    ref = _canon("cam_1", 5.0, 8.0, conf=0.0, proj_conf=0.0)
    sec = _canon("cam_2", 15.0, 35.0, conf=0.0, proj_conf=0.0)
    result = fuse_observation(
        global_player_id="g1",
        timestamp_seconds=0.0,
        take_timestamp_ms=0.0,
        reference_frame_index=0,
        reference_obs=ref,
        secondary_obs=sec,
        reference_intrinsic=0.05,  # 低于 prediction_floor
        secondary_intrinsic=0.05,
        pair=_pair(ref, sec),
        predicted=(5.2, 8.1),
        sync_quality="good",
        config=_CONFIG,
    )
    assert result is not None
    assert result.fusion_status == "conflict"
    assert result.selected_view == "prediction"
    assert result.metric_eligible is False  # 预测点不进指标


def test_fusion_dual_metric_eligible_true_by_default():
    ref = _canon("cam_1", 5.0, 8.0)
    sec = _canon("cam_2", 5.4, 8.2)
    result = fuse_observation(
        global_player_id="g1",
        timestamp_seconds=0.0,
        take_timestamp_ms=0.0,
        reference_frame_index=0,
        reference_obs=ref,
        secondary_obs=sec,
        reference_intrinsic=0.8,
        secondary_intrinsic=0.8,
        pair=_pair(ref, sec),
        predicted=None,
        sync_quality="good",
        config=_CONFIG,
    )
    assert isinstance(result, FusionMeasurement)
    assert result.fusion_status == "dual_observed"
    assert result.metric_eligible is True
