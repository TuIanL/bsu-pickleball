import pytest

from app.vision.courtvision_calibration_engine.homography import (
    HomographyError,
    compute_homography,
    court_to_image,
    image_to_court,
    project_point,
)


def test_homography_projects_pixels_to_court_feet():
    matrix = compute_homography(
        [(0, 0), (100, 0), (100, 200), (0, 200)],
        [(0, 0), (20, 0), (20, 44), (0, 44)],
    )

    x, y = image_to_court((50, 100), matrix)

    assert x == pytest.approx(10)
    assert y == pytest.approx(22)


def test_court_to_image_projects_feet_back_to_pixels():
    matrix = compute_homography(
        [(0, 0), (100, 0), (100, 200), (0, 200)],
        [(0, 0), (20, 0), (20, 44), (0, 44)],
    )
    inverse = pytest.importorskip("numpy").linalg.inv(matrix)

    x, y = court_to_image((10, 22), inverse)

    assert x == pytest.approx(50)
    assert y == pytest.approx(100)


def test_homography_transforms_batch_points():
    matrix = compute_homography(
        [(0, 0), (100, 0), (100, 200), (0, 200)],
        [(0, 0), (20, 0), (20, 44), (0, 44)],
    )

    points = image_to_court([(0, 0), (50, 100), (100, 200)], matrix)

    assert points[0] == pytest.approx((0, 0))
    assert points[1] == pytest.approx((10, 22))
    assert points[2] == pytest.approx((20, 44))


def test_project_point_remains_compatible():
    matrix = compute_homography(
        [(0, 0), (100, 0), (100, 200), (0, 200)],
        [(0, 0), (20, 0), (20, 44), (0, 44)],
    )

    assert project_point(matrix, (50, 100)) == pytest.approx((10, 22))


def test_homography_rejects_too_few_points():
    with pytest.raises(HomographyError):
        compute_homography([(0, 0), (1, 0), (1, 1)], [(0, 0), (20, 0), (20, 44)])


def test_homography_rejects_mismatched_point_counts():
    with pytest.raises(HomographyError):
        compute_homography(
            [(0, 0), (1, 0), (1, 1), (0, 1)],
            [(0, 0), (20, 0), (20, 44)],
        )


def test_homography_rejects_malformed_points():
    with pytest.raises(HomographyError):
        image_to_court((1, 2, 3), [[1, 0, 0], [0, 1, 0], [0, 0, 1]])

    with pytest.raises(HomographyError):
        image_to_court((1, 2), [[1, 0], [0, 1]])


def test_homography_rejects_degenerate_points():
    with pytest.raises(HomographyError):
        compute_homography(
            [(0, 0), (1, 1), (2, 2), (3, 3)],
            [(0, 0), (5, 5), (10, 10), (15, 15)],
        )
