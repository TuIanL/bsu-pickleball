"""BallTracker 多帧候选质量与预测缺口回归测试。"""

from __future__ import annotations

from app.vision.pickleball_game_analysis.ball_tracker import BallTracker, BallTrackerConfig
from app.vision.pickleball_game_analysis.schemas import BallCandidate


class _UnusedDetector:
    def detect(self, frame, conf=0.18):
        raise AssertionError("update_from_candidates must not run the detector")


FRAME_SHAPE = (480, 640, 3)


def _candidate(x: float, *, confidence: float = 0.8, size: float = 8.0) -> BallCandidate:
    return BallCandidate(x, 200.0, confidence, width=size, height=size)


def _update(tracker: BallTracker, tick: int, candidates: list[BallCandidate]):
    return tracker.update_from_candidates(
        frame_index=tick * 2,
        timestamp_sec=tick / 30.0,
        view_candidates=candidates,
        frame_shape=FRAME_SHAPE,
    )


def _locked_tracker() -> BallTracker:
    tracker = BallTracker(
        _UnusedDetector(),
        BallTrackerConfig(
            effective_fps=30.0,
            frame_stride=2,
            max_box_area_ratio=0.1,
            base_gate_pixels=80.0,
            max_gate_pixels=180.0,
        ),
    )
    for tick, x in enumerate((100.0, 115.0, 130.0, 145.0)):
        assert _update(tracker, tick, [_candidate(x)]).accepted
    return tracker


def test_multiple_same_class_candidates_use_direction_speed_scale_and_prediction():
    tracker = _locked_tracker()
    sample = _update(
        tracker,
        4,
        [
            _candidate(160.0, confidence=0.62, size=9.0),
            _candidate(125.0, confidence=0.99, size=24.0),
        ],
    )

    assert sample.accepted
    assert sample.image_xy == (160.0, 200.0)
    debug = sample.diagnostics["ball_frame_debug"]
    assert debug.accepted_candidate_id == str((160.0, 200.0))
    components = debug.candidates[0].score_components
    assert components["direction_consistency"] > components["speed_consistency"] - 0.01
    assert set(components) == {
        "prediction_distance_px",
        "scale_consistency",
        "direction_consistency",
        "speed_consistency",
        "short_gap_consistency",
    }


def test_short_occlusion_is_predicted_non_authoritative_and_reacquires_fast_ball():
    tracker = _locked_tracker()
    missing = _update(tracker, 4, [])
    reacquired = _update(tracker, 5, [_candidate(175.0, confidence=0.55, size=12.0)])

    assert not missing.accepted
    assert missing.source == "predicted"
    assert missing.predicted_position == (160.0, 200.0)
    assert missing.diagnostics["metric_eligibility"] == {
        "bounce": False,
        "landing": False,
        "speed": False,
        "peak_height": False,
        "reason": "predicted_short_gap",
    }
    assert reacquired.accepted
    assert reacquired.image_xy == (175.0, 200.0)


def test_static_advert_candidate_is_blacklisted_but_moving_blurred_ball_remains_available():
    tracker = BallTracker(
        _UnusedDetector(),
        BallTrackerConfig(
            stationary_blacklist_frames=3,
            stationary_window_frames=20,
            max_box_area_ratio=0.1,
        ),
    )
    static = _candidate(40.0, confidence=0.99, size=8.0)
    for tick in range(3):
        _update(tracker, tick, [static])
    rejected = _update(tracker, 3, [static])
    assert rejected.reject_reason == "stationary_blacklisted"
    assert rejected.diagnostics["candidate_filter"][0]["reason"] == "stationary_blacklisted"

    tracker.clear()
    samples = [
        _update(tracker, tick, [_candidate(80.0 + 25.0 * tick, confidence=0.45, size=6.0 + tick * 1.5)])
        for tick in range(5)
    ]
    assert all(sample.accepted for sample in samples)


def test_temporal_candidate_diagnostics_are_deterministic():
    def run_once():
        tracker = _locked_tracker()
        sample = _update(tracker, 4, [_candidate(160.0, confidence=0.7), _candidate(130.0, confidence=0.9)])
        debug = sample.diagnostics["ball_frame_debug"]
        return sample.image_xy, [candidate.score_components for candidate in debug.candidates]

    assert run_once() == run_once()


def test_pre_tick_snapshot_is_read_only_and_exposes_continuity():
    tracker = _locked_tracker()
    before = (tracker.track_state, tracker.missing_frames, list(tracker.trajectory))
    snapshot = tracker.pre_tick_snapshot(4 / 30.0)
    after = (tracker.track_state, tracker.missing_frames, list(tracker.trajectory))
    assert before == after
    assert snapshot.track_state == "locked"
    assert snapshot.continuity_score > 0.7
    assert snapshot.predicted_position == (160.0, 200.0)
    assert snapshot.recent_velocity_px_per_sec is not None
