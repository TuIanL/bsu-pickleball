"""飞行段视角评分、切换与滞回测试。"""

from app.vision.multiview.ball_stereo.segment_view_selection import (
    compute_view_segment_metrics,
    select_main_view,
)
from app.vision.pickleball_game_analysis.schemas import TrajectoryPoint


def _points(*, visible: int, total: int, confidence: float, step: float):
    return [
        TrajectoryPoint(
            frame_index=index,
            timestamp_sec=index / 30.0,
            image_xy=(100.0 + step * index, 200.0) if index < visible else None,
            court_xy=None,
            confidence=confidence if index < visible else None,
            source="detector" if index < visible else "predicted",
        )
        for index in range(total)
    ]


def test_higher_coverage_continuity_and_visibility_select_main_view():
    metrics = {
        "cam_a": compute_view_segment_metrics("cam_a", _points(visible=9, total=10, confidence=0.8, step=8.0)),
        "cam_b": compute_view_segment_metrics("cam_b", _points(visible=5, total=10, confidence=0.9, step=2.0)),
    }
    result = select_main_view(metrics)
    assert result.primary_view_id == "cam_a"
    assert result.reason == "highest_segment_quality"
    assert metrics["cam_a"].observation_coverage == 0.9
    assert metrics["cam_a"].continuity == 0.9


def test_hysteresis_keeps_previous_view_when_scores_are_close():
    metrics = {
        "cam_a": compute_view_segment_metrics("cam_a", _points(visible=9, total=10, confidence=0.80, step=5.0)),
        "cam_b": compute_view_segment_metrics("cam_b", _points(visible=9, total=10, confidence=0.82, step=5.0)),
    }
    result = select_main_view(metrics, previous_primary_view_id="cam_a", hysteresis_margin=0.06)
    assert result.primary_view_id == "cam_a"
    assert result.reason == "hysteresis_kept_previous_primary"


def test_view_selection_is_deterministic_on_exact_tie():
    points = _points(visible=8, total=10, confidence=0.8, step=4.0)
    metrics = {
        "cam_b": compute_view_segment_metrics("cam_b", points),
        "cam_a": compute_view_segment_metrics("cam_a", points),
    }
    assert select_main_view(metrics).primary_view_id == "cam_a"
