import pytest

from app.vision.courtvision_calibration_engine.homography import HomographyError, compute_homography, project_point


def test_homography_projects_pixels_to_court_feet():
    matrix = compute_homography(
        [(0, 0), (100, 0), (100, 200), (0, 200)],
        [(0, 0), (20, 0), (20, 44), (0, 44)],
    )

    x, y = project_point(matrix, (50, 100))

    assert x == pytest.approx(10)
    assert y == pytest.approx(22)


def test_homography_rejects_too_few_points():
    with pytest.raises(HomographyError):
        compute_homography([(0, 0), (1, 0), (1, 1)], [(0, 0), (20, 0), (20, 44)])


def test_homography_rejects_degenerate_points():
    with pytest.raises(HomographyError):
        compute_homography(
            [(0, 0), (1, 1), (2, 2), (3, 3)],
            [(0, 0), (5, 5), (10, 10), (15, 15)],
        )
