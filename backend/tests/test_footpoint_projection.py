import json

import pytest
from pydantic import ValidationError

from app.schemas.calibration import CourtPoint2D
from app.schemas.tracking import (
    BoundingBox,
    Detection,
    PlayerFramePosition,
    ProjectedTrackPoint,
    Track,
    TrackingResult,
)
from app.vision.courtvision_calibration_engine.homography import compute_homography
from app.vision.player_tracking_engine.footpoint_estimator import FootpointEstimator, estimate_footpoint
from app.vision.player_tracking_engine.multi_object_tracker import MultiObjectTracker
from app.vision.player_tracking_engine.player_projector import PlayerProjector


def homography_matrix():
    return compute_homography(
        [(0, 0), (100, 0), (100, 200), (0, 200)],
        [(0, 0), (20, 0), (20, 44), (0, 44)],
    ).tolist()


def test_footpoint_is_bottom_center_of_bbox():
    bbox = BoundingBox(x1=10, y1=20, x2=30, y2=80)

    estimate = FootpointEstimator().estimate(bbox)

    assert estimate.image_footpoint == [20, 80]
    assert estimate.method == "bbox_bottom_center"
    assert estimate_footpoint(bbox) == (20, 80)


def test_player_projector_adds_court_coordinates_from_footpoint():
    track = Track(track_id=1, bbox=[40, 10, 60, 100], confidence=0.9)

    positions = PlayerProjector().project(
        tracks=[track],
        homography=homography_matrix(),
        frame_index=7,
        timestamp=0.25,
    )

    assert len(positions) == 1
    assert positions[0].frame_index == 7
    assert positions[0].timestamp == pytest.approx(0.25)
    assert positions[0].track_id == 1
    assert positions[0].image_footpoint == [50, 100]
    assert positions[0].court_position[0] == pytest.approx(10)
    assert positions[0].court_position[1] == pytest.approx(22)
    assert positions[0].valid is True


def test_player_projector_filters_out_of_bounds_points():
    track = Track(track_id=1, bbox=[940, 10, 960, 100], confidence=0.9)

    positions = PlayerProjector().project(
        tracks=[track],
        homography=homography_matrix(),
        frame_index=0,
        timestamp=0,
    )

    assert positions == []


def test_tracking_schemas_are_json_serializable():
    detection = Detection(bbox=[10, 20, 30, 80], confidence=0.8, class_name="person")
    track = Track(track_id=1, bbox=[10, 20, 30, 80], confidence=0.8)
    position = PlayerFramePosition(
        frame_index=0,
        timestamp=0.0,
        track_id=1,
        bbox=[10, 20, 30, 80],
        image_footpoint=[20, 80],
        court_position=[4, 17.6],
        confidence=0.8,
    )
    result = TrackingResult(
        video_id="video-test",
        calibration_id="calib-test",
        fps=30,
        frame_count=10,
        processed_frame_count=5,
        frame_stride=2,
        detections=[detection],
        tracks=[track],
        positions=[position],
    )

    payload = json.loads(result.model_dump_json())

    assert payload["fps"] == 30
    assert payload["frame_stride"] == 2
    assert payload["detections"][0]["class_name"] == "person"
    assert payload["tracks"][0]["track_id"] == 1
    assert payload["positions"][0]["image_footpoint"] == [20.0, 80.0]


def test_projected_track_point_accepts_boundary_observation_outside_standard_court():
    point = ProjectedTrackPoint(
        frame_index=0,
        timestamp_seconds=0.0,
        track_id="Player_1",
        image_point={"x": 100, "y": 200},
        confidence=0.9,
        court_point={"x": 10, "y": 44.2195},
    )

    payload = point.model_dump(mode="json")

    assert payload["court_point"] == {"x": 10.0, "y": 44.2195}


def test_calibration_court_point_keeps_strict_standard_bounds():
    with pytest.raises(ValidationError):
        CourtPoint2D(x=10, y=44.2195)


def test_iou_tracker_reuses_ids_and_creates_new_ids():
    tracker = MultiObjectTracker(iou_threshold=0.2, max_lost=1)

    first = tracker.update([Detection(bbox=[0, 0, 20, 40], confidence=0.9)])
    second = tracker.update([Detection(bbox=[2, 0, 22, 40], confidence=0.88)])
    third = tracker.update([Detection(bbox=[100, 0, 120, 40], confidence=0.75)])

    assert first[0].track_id == 1
    assert second[0].track_id == 1
    assert third[0].track_id == 2


def test_iou_tracker_retains_lost_track_for_reassociation():
    tracker = MultiObjectTracker(iou_threshold=0.2, max_lost=1)

    first = tracker.update([Detection(bbox=[0, 0, 20, 40], confidence=0.9)])
    missing = tracker.update([])
    reassociated = tracker.update([Detection(bbox=[1, 0, 21, 40], confidence=0.85)])

    assert first[0].track_id == 1
    assert missing == []
    assert reassociated[0].track_id == 1
