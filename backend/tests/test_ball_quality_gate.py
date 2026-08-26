from __future__ import annotations

from app.vision.pickleball_game_analysis.ball_quality_gate import (
    BallQualityGateConfig,
    evaluate_candidate,
    evaluate_interpolation_gap,
    evaluate_motion,
    evaluate_pair_quality,
)
from app.vision.pickleball_game_analysis.schemas import BallCandidate
from app.vision.pickleball_game_analysis.schemas import TrajectoryPoint
from app.vision.pickleball_game_analysis.trajectory_cleaner import TrajectoryCleaner, TrajectoryCleanerConfig


def test_candidate_gate_rejects_low_confidence_and_outside_projected_court():
    config = BallQualityGateConfig()
    low = evaluate_candidate(
        BallCandidate(10, 10, 0.1, width=8, height=8),
        frame_shape=(720, 1280, 3),
        roi_corners=None,
        config=config,
        point_in_roi=True,
    )
    outside = evaluate_candidate(
        BallCandidate(10, 10, 0.9, width=8, height=8),
        frame_shape=(720, 1280, 3),
        roi_corners=None,
        config=config,
        point_in_roi=True,
        projected_xy=(25.0, 10.0),
        projection_detail="projected",
    )
    assert low.reason == "low_confidence"
    assert outside.reason == "outside_court_projection"


def test_motion_gate_uses_timestamp_seconds_and_rejects_speed_jump():
    config = BallQualityGateConfig(max_speed_px_per_sec=100.0)
    decision = evaluate_motion(
        [(0.0, (0.0, 0.0))],
        0.5,
        (40.0, 0.0),
        config=config,
    )
    assert decision.accepted
    too_fast = evaluate_motion(
        [(0.0, (0.0, 0.0))],
        0.1,
        (60.0, 0.0),
        config=config,
    )
    assert too_fast.reason == "speed_jump"


def test_interpolation_gate_is_time_based_and_records_long_gap_reason():
    config = BallQualityGateConfig(max_interpolation_gap_seconds=0.2)
    assert evaluate_interpolation_gap(0.0, 0.15, config=config).accepted
    long_gap = evaluate_interpolation_gap(0.0, 0.21, config=config)
    assert long_gap.reason == "long_gap"


def test_pair_gate_rejects_ambiguous_or_invalid_geometry():
    config = BallQualityGateConfig(min_pair_score_margin=0.1)
    ambiguous = evaluate_pair_quality(
        timestamp_delta_ms=2.0,
        reprojection_error_px=2.0,
        geometry_quality=0.8,
        depth_valid=True,
        xyz=(5.0, 10.0, 2.0),
        score=0.8,
        next_best_score=0.75,
        previous_xyz=None,
        config=config,
        max_time_delta_ms=40.0,
    )
    invalid = evaluate_pair_quality(
        timestamp_delta_ms=2.0,
        reprojection_error_px=2.0,
        geometry_quality=0.8,
        depth_valid=True,
        xyz=(5.0, 10.0, -1.0),
        score=0.9,
        next_best_score=None,
        previous_xyz=None,
        config=config,
        max_time_delta_ms=40.0,
    )
    assert ambiguous.status == "diagnostic_only"
    assert ambiguous.reason == "ambiguous_pair"
    assert invalid.reason == "below_ground"


def test_cleaner_does_not_interpolate_a_long_timestamp_gap():
    points = [
        TrajectoryPoint(0, 0.0, (0.0, 0.0), (0.0, 0.0), confidence=0.8),
        TrajectoryPoint(1, 0.3, None, None),
        TrajectoryPoint(2, 0.6, (60.0, 0.0), (6.0, 0.0), confidence=0.8),
    ]
    cleaned = TrajectoryCleaner(
        TrajectoryCleanerConfig(max_interpolation_gap_seconds=0.2)
    ).interpolate(points)
    assert cleaned[1].image_xy is None
    assert cleaned[1].diagnostics["gap_boundary_reason"] == "long_gap"
