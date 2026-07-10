import numpy as np
import pytest

from app.vision.pickleball_game_analysis import (
    BallCandidate,
    BallTracker,
    BallTrackerConfig,
)
from app.vision.pickleball_game_analysis.schemas import BallTrackState


class StubBallDetector:
    def __init__(self, frames):
        self.frames = list(frames)
        self.index = 0

    def detect(self, frame, conf=0.18):
        if self.index >= len(self.frames):
            return []
        result = self.frames[self.index]
        self.index += 1
        return result


def frame():
    return np.zeros((720, 1280, 3), dtype=np.uint8)


def candidate(x, y, conf=0.8, width=8, height=8):
    return BallCandidate(x, y, conf, width=width, height=height)


def make_config(**overrides):
    defaults = {
        "base_gate_pixels": 60,
        "min_gate_pixels": 40,
        "max_gate_pixels": 200,
        "speed_factor": 1.0,
        "min_prediction_points": 3,
        "tentative_min_hits": 2,
        "lock_min_hits": 4,
        "max_missing_frames_locked": 10,
        "max_missing_frames": 5,
        "max_box_area_ratio": 0.01,
    }
    defaults.update(overrides)
    return BallTrackerConfig(**defaults)


# ── task 11.1: SEARCHING → TENTATIVE → LOCKED state transitions ──

def test_state_transition_searching_to_locked():
    """Tracks transitions from SEARCHING through TENTATIVE to LOCKED."""
    detector = StubBallDetector([
        [candidate(100, 200, 0.8)],   # frame 0: accepted → 1 hits
        [candidate(105, 205, 0.8)],   # frame 1: accepted → 2 hits → TENTATIVE
        [candidate(110, 210, 0.8)],   # frame 2: accepted → 3 hits
        [candidate(115, 215, 0.8)],   # frame 3: accepted → 4 hits → LOCKED
    ])
    tracker = BallTracker(detector, make_config())

    s0 = tracker.update(frame(), 0, 0.0)
    assert s0.track_state == BallTrackState.SEARCHING.value

    s1 = tracker.update(frame(), 1, 0.033)
    assert s1.track_state == BallTrackState.TENTATIVE.value

    s2 = tracker.update(frame(), 2, 0.066)
    assert s2.track_state == BallTrackState.TENTATIVE.value

    s3 = tracker.update(frame(), 3, 0.1)
    assert s3.track_state == BallTrackState.LOCKED.value


# ── task 11.2: LOCKED → LOST → recovery → LOCKED ──

def test_locked_lost_recovery_cycle():
    """LOCKED → LOST on missing, recover back to LOCKED when candidate near prediction."""
    detector = StubBallDetector([
        [candidate(100, 200, 0.8)],   # 0: TENTATIVE after 2
        [candidate(105, 205, 0.8)],   # 1: TENTATIVE
        [candidate(110, 210, 0.8)],   # 2: TENTATIVE
        [candidate(115, 215, 0.8)],   # 3: LOCKED
        [],                            # 4: missing → LOST
        [],                            # 5: missing → LOST
        [candidate(120, 220, 0.8)],   # 6: recovery near predicted → LOCKED
    ])
    tracker = BallTracker(detector, make_config())

    for i in range(4):
        tracker.update(frame(), i, i * 0.033)

    s4 = tracker.update(frame(), 4, 0.133)
    assert s4.track_state == BallTrackState.LOST.value
    assert s4.accepted is False
    assert s4.predicted_position is not None

    s5 = tracker.update(frame(), 5, 0.166)
    assert s5.track_state == BallTrackState.LOST.value

    s6 = tracker.update(frame(), 6, 0.2)
    assert s6.track_state == BallTrackState.LOCKED.value
    assert s6.accepted is True


# ── task 11.3: LOST → SEARCHING after exceeding max_missing_frames_locked ──

def test_lost_transitions_to_searching_after_prolonged_missing():
    """After exceeding max_missing_frames_locked, state resets to SEARCHING."""
    detector = StubBallDetector([
        [candidate(100, 200, 0.8)],
        [candidate(105, 205, 0.8)],
        [candidate(110, 210, 0.8)],
        [candidate(115, 215, 0.8)],   # LOCKED after this
    ] + [[]] * 12)                    # 12 missing frames > 10
    tracker = BallTracker(detector, make_config())

    for i in range(4):
        tracker.update(frame(), i, i * 0.033)

    for i in range(4, 14):
        s = tracker.update(frame(), i, i * 0.033)
        if i == 4:
            assert s.track_state == BallTrackState.LOST.value
        elif i == 14:
            assert s.track_state == BallTrackState.LOST.value

    s15 = tracker.update(frame(), 15, 0.5)
    assert s15.track_state == BallTrackState.SEARCHING.value


# ── task 11.4: LOCKED rejects distant high-confidence false positive ──

def test_locked_rejects_distant_false_positive():
    """In LOCKED, a far-away high-confidence candidate is rejected."""
    detector = StubBallDetector([
        [candidate(100, 200, 0.7)],
        [candidate(105, 205, 0.7)],
        [candidate(110, 210, 0.7)],
        [candidate(115, 215, 0.7)],   # LOCKED
        [candidate(500, 500, 0.95)],  # distant high-confidence
    ])
    tracker = BallTracker(detector, make_config(min_gate_pixels=40, base_gate_pixels=60))

    for i in range(4):
        tracker.update(frame(), i, i * 0.033)

    s4 = tracker.update(frame(), 4, 0.133)
    assert s4.accepted is False
    assert s4.overall_decision == "missing_predicted_only"
    assert s4.predicted_position is not None
    assert s4.track_state == BallTrackState.LOST.value


# ── task 11.5: LOCKED outputs predicted_position when missing ──

def test_locked_outputs_predicted_position_on_missing():
    """Missing frame in LOCKED should include predicted_position."""
    detector = StubBallDetector([
        [candidate(100, 200, 0.7)],
        [candidate(105, 205, 0.7)],
        [candidate(110, 210, 0.7)],
        [candidate(115, 215, 0.7)],   # LOCKED
        [],                            # no candidates → missing
    ])
    tracker = BallTracker(detector, make_config())

    for i in range(4):
        tracker.update(frame(), i, i * 0.033)

    s4 = tracker.update(frame(), 4, 0.133)
    assert s4.accepted is False
    assert s4.overall_decision == "missing_no_candidates"
    assert s4.predicted_position is not None


# ── task 11.6: short-term missing recovery ──

def test_short_term_missing_recovery():
    """After a few missing frames with recovery near prediction, track continues."""
    detector = StubBallDetector([
        [candidate(100, 200, 0.7)],
        [candidate(105, 205, 0.7)],
        [candidate(110, 210, 0.7)],
        [candidate(115, 215, 0.7)],   # LOCKED
        [], [], [],                    # 3 missing
        [candidate(130, 230, 0.7)],   # near predicted (within gate)
    ])
    tracker = BallTracker(detector, make_config())

    for i in range(4):
        tracker.update(frame(), i, i * 0.033)

    for i in range(4, 7):
        s = tracker.update(frame(), i, i * 0.033)
        assert s.accepted is False
        assert s.track_state == BallTrackState.LOST.value

    s7 = tracker.update(frame(), 7, 0.233)
    assert s7.accepted is True
    assert s7.track_state == BallTrackState.LOCKED.value


# ── task 11.7: fast ball not rejected by dynamic gate ──

def test_fast_ball_not_rejected_by_dynamic_gate():
    """Fast ball with consistent direction passes dynamic gate."""
    detector = StubBallDetector([
        [candidate(100, 100, 0.8)],
        [candidate(130, 105, 0.8)],    # dx=30
        [candidate(160, 110, 0.8)],    # dx=30
        [candidate(190, 115, 0.8)],    # dx=30 → LOCKED
        [candidate(220, 120, 0.8)],    # fast but consistent
    ])
    tracker = BallTracker(detector, make_config())

    for i in range(5):
        s = tracker.update(frame(), i, i * 0.033)
        assert s.accepted is True, f"Frame {i} should be accepted"
    assert s.track_state == BallTrackState.LOCKED.value


# ── task 11.8: player-motion-aware static suppression ──

def test_player_motion_static_false_positive_suppression():
    """Stationary candidate with active player motion is suppressed."""
    detector = StubBallDetector([
        [candidate(200, 300, 0.9)] for _ in range(35)  # 35 frames at same spot
    ])
    tracker = BallTracker(
        detector,
        make_config(stationary_window_frames=30, stationary_radius_pixels=5.0),
    )

    for i in range(30):
        s = tracker.update(frame(), i, i * 0.033, player_motion_pixels=50.0)
    # After 30 frames in same spot with players moving, candidate should be rejected
    s_final = tracker.update(frame(), 30, 1.0, player_motion_pixels=50.0)
    assert s_final.reject_reason == "static_false_positive"


# ── task 11.9: player_motion_pixels=None fallback ──

def test_no_player_motion_fallback_to_existing_behavior():
    """When player_motion_pixels is None, tracker uses existing stationary behavior."""
    detector = StubBallDetector([
        [candidate(200, 300, 0.9)] for _ in range(35)
    ])
    tracker = BallTracker(
        detector,
        make_config(stationary_window_frames=30, stationary_radius_pixels=5.0),
    )

    for i in range(31):
        s = tracker.update(frame(), i, i * 0.033, player_motion_pixels=None)
    # Without player motion context, falls back to existing stationary_candidate check
    assert s.reject_reason == "stationary_candidate"


# ── task 11.10: debug metadata format ──

def test_debug_metadata_format():
    """Accepted and rejected frames have proper debug metadata in diagnostics."""
    detector = StubBallDetector([
        [candidate(100, 200, 0.7)],
        [candidate(105, 205, 0.7)],
        [candidate(110, 210, 0.7)],
        [candidate(115, 215, 0.7)],   # LOCKED
        [candidate(500, 500, 0.95)],  # distant false positive
    ])
    tracker = BallTracker(detector, make_config())

    for i in range(4):
        s = tracker.update(frame(), i, i * 0.033)
        assert s.track_state is not None
        assert s.overall_decision == "accepted"
        debug = s.diagnostics.get("ball_frame_debug")
        assert debug is not None
        assert debug.overall_decision == "accepted"
        assert debug.track_state is not None

    s4 = tracker.update(frame(), 4, 0.133)
    assert s4.overall_decision == "missing_predicted_only"
    debug = s4.diagnostics.get("ball_frame_debug")
    assert debug is not None
    assert debug.predicted_position is not None
    assert len(debug.candidates) == 1
    assert debug.candidates[0].rejection_reason == "physics_gate_rejected"
    assert debug.candidates[0].passed_physics_gate is False
