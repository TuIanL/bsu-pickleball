import numpy as np
import pytest

from app.vision.courtvision_calibration_engine.court_geometry import standard_court
from app.vision.courtvision_calibration_engine.court_overlay import draw_court_overlay
from app.vision.courtvision_calibration_engine.homography import compute_homography


def test_draw_court_overlay_preserves_shape_and_draws_pixels():
    pytest.importorskip("cv2")
    court = standard_court()
    image_to_court = compute_homography(
        [(0, 0), (100, 0), (100, 220), (0, 220)],
        [(0, 0), (20, 0), (20, 44), (0, 44)],
    )
    frame = np.zeros((240, 120, 3), dtype=np.uint8)

    output = draw_court_overlay(frame, np.linalg.inv(image_to_court), court)

    assert output.shape == frame.shape
    assert int(output.sum()) > 0
