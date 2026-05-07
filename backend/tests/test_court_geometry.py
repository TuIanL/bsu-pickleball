from app.vision.courtvision_calibration_engine.court_geometry import standard_court


def test_standard_court_constants_and_lines():
    court = standard_court()

    assert court.width_ft == 20
    assert court.length_ft == 44
    assert court.net_y_ft == 22
    assert court.near_kitchen_y_ft == 15
    assert court.far_kitchen_y_ft == 29
    assert court.net_line.start.y == 22
    assert len(court.service_zones) == 4


def test_zone_membership_helpers():
    court = standard_court()

    assert court.is_in_bounds(10, 22)
    assert not court.is_in_bounds(21, 22)
    assert court.is_in_kitchen(10, 16)
    assert court.is_in_kitchen(10, 28)
    assert not court.is_in_kitchen(10, 10)
    assert court.service_zone_for(5, 10) == "near_left_service"
    assert court.service_zone_for(15, 35) == "far_right_service"
