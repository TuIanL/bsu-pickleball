"""Canonical Court Frame Contract —— CourtOrientation、两级坐标系、CanonicalCourtFrameDefinition 持久化。"""

from __future__ import annotations

import pytest

from app.vision.multiview.court_frame import (
    COURT_LENGTH_FT,
    COURT_WIDTH_FT,
    CanonicalCourtFrameDefinition,
    CourtOrientation,
    canonical_to_local,
    is_supported_orientation_scope,
    load_canonical_court_frame,
    local_to_canonical,
    resolve_or_create_canonical_court_frame,
    validate_canonical_court_frame_compatibility,
    write_canonical_court_frame,
)


@pytest.mark.parametrize(
    ("orientation", "x", "y", "expected"),
    [
        (CourtOrientation.identity, 4.0, 8.0, (4.0, 8.0)),
        (CourtOrientation.rotate_180, 4.0, 8.0, (16.0, 36.0)),
        (CourtOrientation.mirror_x, 4.0, 8.0, (16.0, 8.0)),
        (CourtOrientation.mirror_y, 4.0, 8.0, (4.0, 36.0)),
    ],
)
def test_local_to_canonical_four_transforms(orientation, x, y, expected):
    assert local_to_canonical(x, y, orientation) == pytest.approx(expected)


def test_rotate_180_maps_corners_to_opposite_corners():
    # 对向机位核心场景：rotate_180 把一端底线整体搬到另一端。
    assert local_to_canonical(0.0, 0.0, CourtOrientation.rotate_180) == pytest.approx(
        (COURT_WIDTH_FT, COURT_LENGTH_FT)
    )
    assert local_to_canonical(COURT_WIDTH_FT, COURT_LENGTH_FT, CourtOrientation.rotate_180) == pytest.approx(
        (0.0, 0.0)
    )


def test_mirror_x_preserves_y():
    assert local_to_canonical(5.0, 12.0, CourtOrientation.mirror_x) == pytest.approx(
        (COURT_WIDTH_FT - 5.0, 12.0)
    )


def test_mirror_y_preserves_x():
    assert local_to_canonical(5.0, 12.0, CourtOrientation.mirror_y) == pytest.approx(
        (5.0, COURT_LENGTH_FT - 12.0)
    )


def test_transforms_are_self_inverse():
    # 4 个保轴变换均为对合：canonical_to_local == local_to_canonical。
    for orientation in CourtOrientation:
        out = local_to_canonical(7.0, 33.0, orientation)
        back = canonical_to_local(out[0], out[1], orientation)
        assert back == pytest.approx((7.0, 33.0))


def test_invalid_orientation_rejected_by_str_enum():
    with pytest.raises(ValueError):
        CourtOrientation("mirror_diagonal")  # 不存在的朝向


def test_none_orientation_raises_on_normalize():
    # None = 尚未声明，禁止投影式猜测。
    with pytest.raises(ValueError, match="court_orientation is None"):
        local_to_canonical(4.0, 8.0, None)


def test_supported_scope_axis_preserving_only():
    assert is_supported_orientation_scope("baseline") is True
    assert is_supported_orientation_scope("elevated_baseline") is True
    # sideline / 未知类型视为不支持。
    assert is_supported_orientation_scope("sideline") is False
    assert is_supported_orientation_scope(None) is False


def test_canonical_frame_definition_round_trip(tmp_path):
    definition = CanonicalCourtFrameDefinition.create(
        capture_take_id="take_1",
        end_a_definition="北端底线",
        end_b_definition="南端底线",
    )
    path = write_canonical_court_frame(tmp_path, definition)
    assert path.exists()

    loaded = load_canonical_court_frame(tmp_path)
    assert loaded is not None
    assert loaded.frame_id == definition.frame_id
    assert loaded.capture_take_id == "take_1"
    assert loaded.end_a_definition == "北端底线"
    assert loaded.end_b_definition == "南端底线"


def test_resolve_reuses_same_frame_id(tmp_path):
    # 同一 take 首次配置后持久化，后续分析复用同一 frame_id，禁止重跑翻转。
    first = resolve_or_create_canonical_court_frame(tmp_path, "take_1", "北端", "南端")
    second = resolve_or_create_canonical_court_frame(tmp_path, "take_1", "北端", "南端")
    assert first.frame_id == second.frame_id

    # 再次以不同端点调用也不应新建（守护"同一 take 单一 frame_id"）。
    third = resolve_or_create_canonical_court_frame(tmp_path, "take_1", "南端", "北端")
    assert third.frame_id == first.frame_id
    assert third.end_a_definition == "北端"


def test_load_missing_returns_none(tmp_path):
    assert load_canonical_court_frame(tmp_path) is None


def test_new_request_can_reject_canonical_frame_conflict(tmp_path):
    frame = resolve_or_create_canonical_court_frame(
        tmp_path,
        "take_1",
        "北端",
        "南端",
        orientation_by_view={"cam_1": "identity", "cam_2": "rotate_180"},
    )
    assert validate_canonical_court_frame_compatibility(
        frame,
        capture_take_id="take_1",
        end_a_definition="北端",
        end_b_definition="南端",
        orientation_by_view={"cam_1": "rotate_180", "cam_2": "identity"},
    )


def test_existing_frame_can_be_completed_with_a_new_view_orientation(tmp_path):
    frame = resolve_or_create_canonical_court_frame(
        tmp_path,
        "take_1",
        "北端",
        "南端",
        orientation_by_view={"cam_1": "identity"},
    )

    assert validate_canonical_court_frame_compatibility(
        frame,
        capture_take_id="take_1",
        end_a_definition="北端",
        end_b_definition="南端",
        orientation_by_view={"cam_1": "identity", "cam_2": "rotate_180"},
    ) is None

    completed = resolve_or_create_canonical_court_frame(
        tmp_path,
        "take_1",
        "北端",
        "南端",
        orientation_by_view={"cam_1": "identity", "cam_2": "rotate_180"},
    )
    assert completed.frame_id == frame.frame_id
    assert completed.orientation_by_view == {"cam_1": "identity", "cam_2": "rotate_180"}
