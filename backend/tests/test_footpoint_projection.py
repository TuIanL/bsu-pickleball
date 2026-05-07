import pytest

from app.schemas.tracking import BoundingBox, ImageTrackPoint
from app.vision.courtvision_calibration_engine.homography import compute_homography
from app.vision.player_tracking_engine.footpoint_estimator import estimate_footpoint
from app.vision.player_tracking_engine.player_projector import project_track_points


def test_footpoint_is_bottom_center_of_bbox():
    assert estimate_footpoint(BoundingBox(x1=10, y1=20, x2=30, y2=80)) == (20, 80)


def test_project_track_points_adds_court_coordinates():
    matrix = compute_homography(
        [(0, 0), (100, 0), (100, 200), (0, 200)],
        [(0, 0), (20, 0), (20, 44), (0, 44)],
    )
    point = ImageTrackPoint(
        frame_index=0,
        timestamp_seconds=0,
        track_id="p1",
        image_point={"x": 50, "y": 100},
        confidence=0.9,
        side="near",
    )

    projected = project_track_points([point], matrix.tolist())

    assert projected[0].court_point.x == pytest.approx(10)
    assert projected[0].court_point.y == pytest.approx(22)
    assert projected[0].track_id == "p1"
