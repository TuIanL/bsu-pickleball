"""真实界外与环境离群不得混为一谈。"""

from app.vision.pickleball_game_analysis.ball_environment_classifier import (
    BallEnvironmentClassifier,
    EndpointEvidence,
)


def test_real_sideline_out_is_preserved_without_automatic_adjudication():
    result = BallEnvironmentClassifier().classify(
        (21.4, 30.0),
        EndpointEvidence(continuity_score=0.9, endpoint_time_consistent=True, cross_view_supported=True),
    )
    assert result.outcome_classification == "legal_out_candidate"
    assert result.accepted_for_formal_trajectory
    assert not result.automatic_adjudication
    assert result.non_adjudication_notice == "可能界外落点，非自动判罚"


def test_serve_behind_baseline_remains_a_valid_outside_line_candidate():
    result = BallEnvironmentClassifier().classify(
        (10.0, -4.0),
        EndpointEvidence(continuity_score=0.8, endpoint_time_consistent=True),
    )
    assert result.court_location == "outside_line"
    assert result.outcome_classification == "legal_out_candidate"


def test_small_calibration_overrun_degrades_instead_of_deleting():
    result = BallEnvironmentClassifier().classify(
        (28.6, 30.0),
        EndpointEvidence(calibration_uncertainty_ft=0.8, continuity_score=0.7),
    )
    assert result.outcome_classification == "calibration_uncertain"
    assert result.accepted_for_formal_trajectory


def test_static_spectator_area_false_positive_requires_multiple_rejection_signals():
    result = BallEnvironmentClassifier().classify(
        (55.0, 80.0),
        EndpointEvidence(
            continuity_score=0.1,
            endpoint_time_consistent=False,
            static_pattern=True,
            jump_detected=True,
            reprojection_error_px=120.0,
            cross_view_supported=False,
        ),
    )
    assert result.outcome_classification == "environment_outlier"
    assert not result.accepted_for_formal_trajectory
    assert {"static_pattern", "trajectory_jump", "high_reprojection_error"} <= set(result.reasons)


def test_far_out_point_with_continuous_cross_view_support_is_not_rejected_on_position_alone():
    result = BallEnvironmentClassifier().classify(
        (29.5, 40.0),
        EndpointEvidence(
            continuity_score=0.95,
            endpoint_time_consistent=True,
            cross_view_supported=True,
            calibration_uncertainty_ft=0.2,
        ),
    )
    assert result.outcome_classification == "calibration_uncertain"
    assert result.accepted_for_formal_trajectory
