from app.vision.courtvision_calibration_engine.court_geometry import PickleballCourtGeometry, standard_court


def test_standard_court_constants_and_lines():
    court = standard_court()

    assert isinstance(court, PickleballCourtGeometry)
    assert court.coordinate_system == {"unit": "feet", "width": 20.0, "length": 44.0}
    assert court.width_ft == 20
    assert court.length_ft == 44
    assert court.net_y_ft == 22
    assert court.near_kitchen_y_ft == 15
    assert court.far_kitchen_y_ft == 29
    assert court.net_line.start.y == 22
    assert court.near_kitchen_line.start.y == 15
    assert court.far_kitchen_line.start.y == 29
    assert len(court.service_zones) == 4
    assert len(court.lines) == 9


def test_standard_court_keypoints_are_canonical_outer_corners():
    court = standard_court()
    keypoints = court.standard_keypoints

    assert len(keypoints) == 4
    assert keypoints["top_left"].x == 0.0
    assert keypoints["top_left"].y == 0.0
    assert keypoints["top_right"].x == 20.0
    assert keypoints["top_right"].y == 0.0
    assert keypoints["bottom_right"].x == 20.0
    assert keypoints["bottom_right"].y == 44.0
    assert keypoints["bottom_left"].x == 0.0
    assert keypoints["bottom_left"].y == 44.0


def test_standard_court_polygons_include_kitchen_and_service_regions():
    court = standard_court()

    polygon_names = {polygon.name for polygon in court.polygons}

    assert "outer_boundary" in polygon_names
    assert "near_kitchen" in polygon_names
    assert "far_kitchen" in polygon_names
    assert "near_left_service" in polygon_names
    assert "far_right_service" in polygon_names


def test_zone_membership_helpers():
    court = standard_court()

    assert court.is_in_bounds(10, 22)
    assert not court.is_in_bounds(21, 22)
    assert court.is_in_kitchen(10, 16)
    assert court.is_in_kitchen(10, 28)
    assert not court.is_in_kitchen(10, 10)
    assert court.service_zone_for(5, 10) == "near_left_service"
    assert court.service_zone_for(15, 35) == "far_right_service"
