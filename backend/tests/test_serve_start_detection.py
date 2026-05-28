import pytest

from app.schemas.events import ServeEventCandidate
from app.schemas.pose import PoseKeypoint, PoseOverlayFrame, PoseSubject
from app.schemas.tracking import (
    CourtCoordinateMetadata,
    CourtDimensions,
    PlayerTrajectoryArtifact,
    PlayerTrajectorySample,
    TrackingResult,
)
from app.vision.events.serve_start_detector import ServeStartDetector
from app.vision.courtvision_calibration_engine.court_units import normalize_court_unit


def sample(frame, time, x, y, *, player_id="Player_1", track_id=1, unit="m"):
    return PlayerTrajectorySample(
        frame_index=frame,
        timestamp_seconds=time,
        player_id=player_id,
        track_id=track_id,
        court_x=x,
        court_y=y,
        court_unit=unit,
        confidence=0.9,
    )


def tracking():
    return TrackingResult(fps=5, frame_count=80, processed_frame_count=8, frame_stride=1)


def metric_court(unit="m"):
    return CourtCoordinateMetadata(
        court_unit=unit,
        canonical=CourtDimensions(width=6.10 if unit == "m" else 20.0, length=13.41 if unit == "m" else 44.0, unit=unit),
    )


def pose_frame(frame, time, wrist_x, *, track_id="1"):
    return PoseOverlayFrame(
        frame_index=frame,
        timestamp_seconds=time,
        subjects=[
            PoseSubject(
                track_id=track_id,
                bbox=[0, 0, 100, 200],
                confidence=0.9,
                keypoints=[
                    PoseKeypoint(name="right_wrist", x=wrist_x, y=50, confidence=0.9),
                    PoseKeypoint(name="right_elbow", x=wrist_x / 2, y=80, confidence=0.9),
                ],
            )
        ],
    )


def test_serve_event_candidate_rejects_seek_after_anchor():
    with pytest.raises(ValueError):
        ServeEventCandidate(
            id="serve-001",
            timestamp_seconds=1,
            frame_index=5,
            confidence=0.8,
            seek_time_seconds=2,
            reason="bad seek",
        )


def test_detector_returns_pose_context_candidate_from_metric_baseline():
    trajectories = PlayerTrajectoryArtifact(
        job_id="job-serve",
        video_id="video-serve",
        court=metric_court("m"),
        players={
            "Player_1": [
                sample(0, 0, 3.0, 12.7),
                sample(5, 1, 3.01, 12.7),
                sample(10, 2, 3.02, 12.7),
                sample(15, 3, 3.9, 12.6),
            ],
            "Player_2": [
                sample(0, 0, 2.0, 1.0, player_id="Player_2", track_id=2),
                sample(5, 1, 2.0, 1.01, player_id="Player_2", track_id=2),
                sample(10, 2, 2.0, 1.02, player_id="Player_2", track_id=2),
                sample(15, 3, 3.0, 1.2, player_id="Player_2", track_id=2),
            ],
        },
    )
    poses = [pose_frame(0, 0, 10), pose_frame(5, 1, 10), pose_frame(10, 2, 210), pose_frame(15, 3, 220)]

    artifact = ServeStartDetector().detect(
        job_id="job-serve",
        video_id="video-serve",
        tracking=tracking(),
        player_trajectories=trajectories,
        pose_frames=poses,
    )

    assert artifact.status == "available"
    assert artifact.detection_mode == "pose"
    assert artifact.events[0].timestamp_seconds == 2
    assert artifact.events[0].signals
    assert artifact.events[0].signals.baseline_position_score is not None
    assert artifact.events[0].signals.arm_motion_peak_score is not None
    assert artifact.events[0].start_time_seconds == pytest.approx(0)
    assert artifact.events[0].seek_time_seconds == pytest.approx(0.5)
    assert "pose" in artifact.events[0].source_signals


def test_detector_supports_feet_baseline_units():
    trajectories = PlayerTrajectoryArtifact(
        job_id="job-serve",
        court=metric_court("ft"),
        players={
            "Player_1": [
                sample(0, 0, 10, 42, unit="ft"),
                sample(5, 1, 10.1, 42, unit="ft"),
                sample(10, 2, 10.2, 42, unit="ft"),
                sample(15, 3, 14, 41, unit="ft"),
            ]
        },
    )

    artifact = ServeStartDetector().detect(
        job_id="job-serve",
        video_id=None,
        tracking=tracking(),
        player_trajectories=trajectories,
    )

    assert artifact.status == "partial"
    assert artifact.events[0].court_unit == "ft"
    assert artifact.events[0].detection_mode == "roi"


def test_detector_rejects_continuous_rally_without_pre_stillness():
    trajectories = PlayerTrajectoryArtifact(
        job_id="job-serve",
        court=metric_court("m"),
        players={
            "Player_1": [
                sample(0, 0, 3.0, 12.7),
                sample(5, 1, 3.8, 12.7),
                sample(10, 2, 4.5, 12.4),
                sample(15, 3, 5.1, 12.0),
            ]
        },
    )

    artifact = ServeStartDetector().detect(
        job_id="job-serve",
        video_id=None,
        tracking=tracking(),
        player_trajectories=trajectories,
    )

    assert artifact.status == "no_candidates"
    assert artifact.events == []


def test_court_unit_helper_rejects_unknown_units():
    assert normalize_court_unit("m") == "m"
    assert normalize_court_unit("feet") == "ft"
    assert normalize_court_unit("yards") is None


def test_detector_reports_unavailable_without_tracking():
    artifact = ServeStartDetector().detect(job_id="job-serve", video_id=None)

    assert artifact.status == "unavailable"
    assert "tracking" in artifact.detail
