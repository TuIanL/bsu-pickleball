"""下游消费 —— metric eligibility 策略、移动/可视化点提取、单视角回退。"""

from __future__ import annotations

from app.vision.multiview.consumers import (
    FusedTrackPoint,
    metric_eligibility_policy,
    movement_points,
    select_trajectory_source,
    visualization_points,
)


def _sample(status, x, y, eligible=True):
    return {
        "global_player_id": "g1",
        "timestamp_seconds": 0.0,
        "take_timestamp_ms": 0.0,
        "reference_frame_index": 0,
        "x_ft": x,
        "y_ft": y,
        "fusion_status": status,
        "fusion_confidence": 0.8,
        "measurement_source": "dual" if status == "dual_observed" else "none",
        "metric_eligible": eligible,
    }


def test_policy_dual_and_single_yes():
    assert metric_eligibility_policy("dual_observed", metric_eligible_flag=True) is True
    assert metric_eligibility_policy("single_view_fallback", metric_eligible_flag=True) is True


def test_policy_predicted_no():
    assert metric_eligibility_policy("predicted", metric_eligible_flag=False) is False


def test_policy_unavailable_no():
    assert metric_eligibility_policy("unavailable", metric_eligible_flag=False) is False


def test_policy_conflict_depends_on_flag():
    assert metric_eligibility_policy("conflict", metric_eligible_flag=True) is True
    assert metric_eligibility_policy("conflict", metric_eligible_flag=False) is False


def test_movement_points_filters_predicted_and_no_coords():
    artifact = {
        "schema_version": "fused_player_trajectory.v1",
        "samples": [
            _sample("dual_observed", 5.0, 8.0),
            _sample("predicted", 5.2, 8.1, eligible=False),
            _sample("unavailable", None, None, eligible=False),
            _sample("conflict", 15.0, 35.0, eligible=True),
        ],
    }
    points = movement_points(artifact)
    assert isinstance(points[0], FusedTrackPoint)
    assert len(points) == 2  # dual + conflict(eligible)
    assert all(p.metric_eligible for p in points)


def test_visualization_points_includes_predicted():
    artifact = {
        "schema_version": "fused_player_trajectory.v1",
        "samples": [
            _sample("dual_observed", 5.0, 8.0),
            _sample("predicted", 5.2, 8.1, eligible=False),
        ],
    }
    points = visualization_points(artifact)
    assert len(points) == 2
    assert points[1].fusion_status == "predicted"
    assert points[1].metric_eligible is False


def test_select_trajectory_source_prefers_fused():
    assert select_trajectory_source(True, True) == "fused"
    assert select_trajectory_source(True, False) == "fused"
    assert select_trajectory_source(False, True) == "single_view"
