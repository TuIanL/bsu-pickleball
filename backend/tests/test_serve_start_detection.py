import pytest

from app.schemas.events import ServeEventCandidate
from app.schemas.tracking import (
    CourtCoordinateMetadata,
    PlayerTrajectoryArtifact,
    PlayerTrajectorySample,
    TrackingResult,
)
from app.vision.events.serve_start_detector import ServeStartDetector


def sample(frame, time, x, y):
    return PlayerTrajectorySample(
        frame_index=frame,
        timestamp_seconds=time,
        player_id="Player_1",
        track_id=1,
        court_x=x,
        court_y=y,
        confidence=0.9,
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


def test_detector_returns_available_candidate_from_trajectory():
    tracking = TrackingResult(fps=5, frame_count=50, processed_frame_count=5, frame_stride=1)
    trajectories = PlayerTrajectoryArtifact(
        job_id="job-serve",
        video_id="video-serve",
        court=CourtCoordinateMetadata(),
        players={
            "Player_1": [
                sample(0, 0, 5, 5),
                sample(5, 1, 5.1, 5),
                sample(10, 2, 5.2, 5),
                sample(15, 3, 9.0, 5),
            ]
        },
    )

    artifact = ServeStartDetector().detect(
        job_id="job-serve",
        video_id="video-serve",
        tracking=tracking,
        player_trajectories=trajectories,
        pose_frames=[],
    )

    assert artifact.status == "partial"
    assert artifact.events[0].timestamp_seconds == 2
    assert artifact.events[0].seek_time_seconds == pytest.approx(0.5)
    assert "trajectory" in artifact.events[0].source_signals


def test_detector_reports_no_candidates_when_tracking_has_no_burst():
    tracking = TrackingResult(fps=5, frame_count=50, processed_frame_count=5, frame_stride=1)
    trajectories = PlayerTrajectoryArtifact(
        job_id="job-serve",
        players={"Player_1": [sample(0, 0, 5, 5), sample(5, 1, 5.1, 5), sample(10, 2, 5.2, 5)]},
    )

    artifact = ServeStartDetector().detect(
        job_id="job-serve",
        video_id=None,
        tracking=tracking,
        player_trajectories=trajectories,
    )

    assert artifact.status == "no_candidates"
    assert artifact.events == []


def test_detector_reports_unavailable_without_tracking():
    artifact = ServeStartDetector().detect(job_id="job-serve", video_id=None)

    assert artifact.status == "unavailable"
    assert "tracking" in artifact.detail
