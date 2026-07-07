import json

import numpy as np
import pytest

from app.vision.courtvision_calibration_engine.homography import compute_homography
from app.vision.pickleball_game_analysis import (
    BallCandidate,
    BallCourtAdapter,
    BallFrameSample,
    BallTracker,
    BallTrackerConfig,
    BounceDetector,
    BounceDetectorConfig,
    BounceEvent,
    TrajectoryCleaner,
    TrajectoryCleanerConfig,
    TrajectoryPoint,
)
from app.vision.pickleball_game_analysis.detection_writer import (
    build_bounce_events_payload,
    build_cleaned_trajectory_payload,
    build_raw_trajectory_payload,
    write_bounce_events,
)
from app.vision.pickleball_game_analysis.schemas import to_jsonable


class StubBallDetector:
    def __init__(self, frames):
        self.frames = list(frames)
        self.index = 0
        self.calls = []

    def detect(self, frame, conf=0.18):
        self.calls.append(conf)
        if self.index >= len(self.frames):
            return []
        result = self.frames[self.index]
        self.index += 1
        return result


def frame():
    return np.zeros((100, 100, 3), dtype=np.uint8)


def sample(frame_index, image_xy, court_xy=None):
    return TrajectoryPoint(
        frame_index=frame_index,
        timestamp_sec=frame_index / 30,
        image_xy=image_xy,
        court_xy=court_xy,
        confidence=0.8 if image_xy is not None else None,
    )


def bounce_points(court_xy=(11.6, 20.8)):
    points = []
    for index in range(35):
        image_xy = (100 + index * 5, 100 + abs(index - 16) * 6)
        court = court_xy if index == 16 else (10 + index * 0.1, 20 + index * 0.05)
        points.append(TrajectoryPoint(index + 1, index / 30, image_xy, court))
    return points


def test_schema_and_writer_serialize_numpy_and_empty_events(tmp_path):
    raw_sample = BallFrameSample(
        frame_index=np.int64(1),
        timestamp_sec=np.float32(0.033),
        image_xy=(np.float32(10.5), np.float64(20.25)),
        court_xy=None,
        confidence=np.float32(0.9),
        visible=True,
        accepted=True,
        candidate_count=np.int64(2),
    )
    raw_payload = build_raw_trajectory_payload(job_id="job-ball", samples=[raw_sample])
    cleaned_payload = build_cleaned_trajectory_payload(job_id="job-ball", samples=[TrajectoryPoint.from_sample(raw_sample)])
    empty_events = build_bounce_events_payload(job_id="job-ball", events=[])

    assert raw_payload["coordinate_system"]["court"] == "feet"
    assert raw_payload["samples"][0]["image_xy"] == pytest.approx([10.5, 20.25])
    assert cleaned_payload["filtering"]["max_interpolation_gap"] == 12
    assert empty_events["status"] == "no_candidates"
    assert empty_events["events"] == []
    assert to_jsonable({"value": np.float32(1.25)}) == {"value": pytest.approx(1.25)}

    output = write_bounce_events(tmp_path / "bounce_events.json", job_id="job-ball", events=[])
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["schema_version"] == "bounce_events.v1"


def test_court_adapter_projects_feet_and_handles_missing_or_out_of_bounds():
    matrix = compute_homography(
        [(0, 0), (100, 0), (100, 200), (0, 200)],
        [(0, 0), (20, 0), (20, 44), (0, 44)],
    )
    adapter = BallCourtAdapter()

    projected = adapter.project((50, 100), matrix)
    missing = adapter.project((50, 100), None)
    out_of_bounds = adapter.project((150, 250), matrix)

    assert adapter.coordinate_system == {"image": "pixels", "court": "feet", "court_width": 20.0, "court_length": 44.0}
    assert projected.court_xy == pytest.approx((10, 22))
    assert projected.in_bounds is True
    assert missing.court_xy is None
    assert missing.detail == "missing_homography"
    assert out_of_bounds.in_bounds is False


def test_ball_tracker_filters_candidates_roi_jumps_and_rebuilds_after_missing():
    matrix = compute_homography(
        [(0, 0), (100, 0), (100, 200), (0, 200)],
        [(0, 0), (20, 0), (20, 44), (0, 44)],
    )
    detector = StubBallDetector(
        [
            [],
            [BallCandidate(10, 10, 0.9, width=8, height=8)],
            [BallCandidate(90, 90, 0.9, width=8, height=8)],
            [BallCandidate(12, 12, 0.9, width=80, height=80)],
            [BallCandidate(95, 95, 0.9, width=8, height=8)],
            [BallCandidate(10, 10, 0.9, width=8, height=8)],
            [BallCandidate(11, 11, 0.9, width=8, height=8)],
            [BallCandidate(90, 90, 0.9, width=8, height=8)],
            [BallCandidate(92, 92, 0.9, width=8, height=8)],
        ]
    )
    tracker = BallTracker(
        detector,
        BallTrackerConfig(max_jump_pixels=20, prediction_gate_pixels=25, max_missing_frames=1, max_box_area_ratio=0.1),
    )

    no_candidate = tracker.update(frame(), 1, 0.0)
    accepted = tracker.update(frame(), 2, 0.033, homography=matrix)
    outside_roi = tracker.update(frame(), 3, 0.066, roi_corners=((0, 0), (20, 20)))
    too_large = tracker.update(frame(), 4, 0.099)
    jump = tracker.update(frame(), 5, 0.132)
    rebuilt = tracker.update(frame(), 6, 0.165)
    still_strict = tracker.update(frame(), 7, 0.198)
    accepted_after_rebuild = tracker.update(frame(), 8, 0.231)
    steady = tracker.update(frame(), 9, 0.264)

    assert no_candidate.visible is False
    assert no_candidate.reject_reason == "no_candidates"
    assert accepted.accepted is True
    assert accepted.court_xy == pytest.approx((2, 2.2))
    assert outside_roi.reject_reason == "outside_roi"
    assert too_large.reject_reason == "box_too_large"
    assert jump.accepted is True
    assert rebuilt.reject_reason == "jump_distance"
    assert still_strict.reject_reason == "jump_distance"
    assert accepted_after_rebuild.accepted is True
    assert steady.accepted is True


def test_ball_tracker_rejects_stationary_logo_like_candidates():
    detector = StubBallDetector([[BallCandidate(48, 52, 0.9, width=7, height=7)] for _ in range(8)])
    tracker = BallTracker(
        detector,
        BallTrackerConfig(stationary_window_frames=4, stationary_radius_pixels=1.5, max_box_area_ratio=0.1),
    )

    samples = [tracker.update(frame(), index, index / 30) for index in range(8)]

    assert any(sample.accepted for sample in samples[:3])
    assert samples[3].accepted is False
    assert samples[3].reject_reason == "stationary_candidate"
    assert samples[-1].reject_reason == "stationary_candidate"


def test_ball_tracker_rejects_points_projected_far_outside_court():
    matrix = compute_homography(
        [(0, 0), (100, 0), (100, 200), (0, 200)],
        [(0, 0), (20, 0), (20, 44), (0, 44)],
    )
    detector = StubBallDetector([[BallCandidate(180, 100, 0.9, width=8, height=8)]])
    tracker = BallTracker(
        detector,
        BallTrackerConfig(court_bounds_margin_ft=2.0, max_box_area_ratio=0.1),
    )

    sample = tracker.update(frame(), 1, 0.0, homography=matrix)

    assert sample.accepted is False
    assert sample.reject_reason == "projected_outside_court"
    assert sample.court_xy == pytest.approx((36, 22))


def test_trajectory_cleaner_removes_isolated_jump_and_interpolates_short_gaps():
    cleaner = TrajectoryCleaner(TrajectoryCleanerConfig(max_interpolation_gap=2, outlier_step_floor_px=50))
    points = [
        sample(1, (0, 0), (0, 0)),
        sample(2, (10, 0), (1, 0)),
        sample(3, (20, 0), (2, 0)),
        sample(4, (500, 500), (50, 50)),
        sample(5, (30, 0), (3, 0)),
        sample(6, (40, 0), (4, 0)),
    ]

    cleaned = cleaner.remove_outliers(points)
    interpolated = cleaner.interpolate(
        [
            sample(1, (0, 0), (0, 0)),
            sample(2, None, None),
            sample(3, (20, 0), (2, 0)),
            sample(4, None, None),
            sample(5, None, None),
            sample(6, None, None),
            sample(7, (70, 0), (7, 0)),
        ]
    )

    assert cleaned[3].image_xy is None
    assert cleaned[3].diagnostics["cleaner_reject_reason"] == "isolated_jump"
    assert interpolated[1].image_xy == pytest.approx((10, 0))
    assert interpolated[1].court_xy == pytest.approx((1, 0))
    assert interpolated[1].interpolated is True
    assert interpolated[3].image_xy is None
    assert interpolated[4].image_xy is None
    assert interpolated[5].image_xy is None


def test_bounce_detector_detects_skips_missing_rejects_margin_and_dedupes():
    detector = BounceDetector(BounceDetectorConfig(max_center_velocity=99999, max_speed_ratio=999))

    events = detector.detect(bounce_points())
    missing_points = bounce_points()
    missing_points[10] = TrajectoryPoint(11, 10 / 30, None, None)
    outside_events = detector.detect(bounce_points(court_xy=(100, 100)))

    assert len(events) == 1
    assert events[0].frame_index == 17
    assert events[0].detection_method == "trajectory_lag20"
    assert events[0].diagnostics["local_y_valley"] is True
    assert detector.detect(missing_points) == []
    assert outside_events == []

    close = [
        BounceEvent("a", 10, 0.3, (1, 1), None, 0.4, "trajectory_lag20"),
        BounceEvent("b", 12, 0.4, (1, 1), None, 0.8, "trajectory_lag20"),
        BounceEvent("c", 40, 1.3, (1, 1), None, 0.5, "trajectory_lag20"),
    ]
    deduped = detector._dedupe_events(close)
    assert [event.frame_index for event in deduped] == [12, 40]
    assert [event.event_id for event in deduped] == ["bounce-1", "bounce-2"]
