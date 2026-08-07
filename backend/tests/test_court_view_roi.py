from app.schemas.court_view import CourtViewThresholds
from app.schemas.tracking import Detection
from app.vision.court_view import (
    CourtViewFrameScorer,
    CourtViewStateMachine,
    compute_expanded_detection_roi,
    filter_detections_to_roi,
)


def test_compute_expanded_detection_roi_from_calibration_corners():
    roi = compute_expanded_detection_roi(
        [(20, 10), (80, 10), (80, 90), (20, 90)],
        100,
        100,
        calibration_id="calib-1",
    )

    assert roi.status == "available"
    assert roi.bounds is not None
    assert roi.bounds.x1 == 0
    assert roi.bounds.x2 == 99
    assert roi.bounds.clipped_to_frame is True
    assert roi.calibration_id == "calib-1"


def test_compute_expanded_detection_roi_reports_missing_inputs():
    roi = compute_expanded_detection_roi(None, 100, 100)

    assert roi.status == "unavailable"
    assert roi.diagnostics["reason"] == "missing_calibration_keypoints"


def test_compute_expanded_detection_roi_reports_degenerate_geometry():
    roi = compute_expanded_detection_roi(
        [(10, 10), (10, 20), (10, 30), (10, 40)],
        100,
        100,
    )

    assert roi.status == "unavailable"
    assert roi.diagnostics["reason"] == "degenerate_court_width"


def test_filter_detections_to_roi_uses_source_frame_footpoint():
    roi = compute_expanded_detection_roi(
        [(20, 10), (60, 10), (60, 90), (20, 90)],
        120,
        100,
    )
    detections = [
        Detection(bbox=[25, 10, 45, 80], confidence=0.9),
        Detection(bbox=[100, 10, 115, 80], confidence=0.9),
    ]

    kept, filtered = filter_detections_to_roi(detections, roi)

    assert kept == [detections[0]]
    assert filtered == 1


def test_court_view_frame_scorer_clamps_scores_to_schema_range():
    assert CourtViewFrameScorer._clamp_score(-0.0216) == 0.0
    assert CourtViewFrameScorer._clamp_score(0.42) == 0.42
    assert CourtViewFrameScorer._clamp_score(1.4) == 1.0


def test_court_view_state_machine_clamps_negative_score_samples():
    state = CourtViewStateMachine(CourtViewThresholds(match_threshold=0.75, start_frames=1, end_frames=1))

    sample = state.update(0, 0.0, -0.0216)

    assert sample.score == 0.0
    assert sample.reason == "gated_non_court_view"


def test_court_view_state_machine_segments_and_gated_frames():
    state = CourtViewStateMachine(
        CourtViewThresholds(
            match_threshold=0.75,
            start_frames=2,
            end_frames=2,
            skip_non_court_frames=True,
        )
    )

    samples = [
        state.update(0, 0.0, 0.9),
        state.update(1, 0.2, 0.88),
        state.update(2, 0.4, 0.7),
        state.update(3, 0.6, 0.65),
    ]
    state.finish(3, 0.6)

    assert [sample.reason for sample in samples] == [
        "court_view",
        "court_view",
        "gated_non_court_view",
        "gated_non_court_view",
    ]
    assert state.gated_frame_count == 2
    assert len(state.segments) == 1
    assert state.segments[0].start_frame_index == 0
    assert state.segments[0].end_frame_index == 1
    assert state.segments[0].low_score_frame_count == 2


def test_court_view_state_machine_reports_gate_unavailable():
    state = CourtViewStateMachine(CourtViewThresholds(match_threshold=0.75, start_frames=1, end_frames=1))

    sample = state.update(0, 0.0, None)

    assert sample.reason == "gate_unavailable"
    assert sample.score is None
