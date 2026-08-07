"""Canonical Timeline —— 融合时刻来源与 pairing tolerance。"""

from __future__ import annotations

import pytest

from app.services.dual_camera_sync import SyncCalibration
from app.vision.multiview.canonical_timeline import CanonicalTimelineBuilder
from app.vision.multiview.court_frame import CourtOrientation
from app.vision.multiview.sync import MultiViewSyncCalibration
from app.vision.multiview.types import ViewObservation


def _obs(view_id, frame_index, timestamp_seconds, x, y):
    return ViewObservation(
        view_id=view_id,
        source_frame_index=frame_index,
        timestamp_seconds=timestamp_seconds,
        local_x_ft=x,
        local_y_ft=y,
    )


def _build(reference_obs, secondary_obs, *, offset_seconds=0.5, rate=1.0, max_pairing_error_ms=1000.0 / 30.0):
    calibration = SyncCalibration(
        reference_camera="cam_1",
        camera_id="cam_2",
        offset_seconds=offset_seconds,
        rate=rate,
        drift_ppm=(rate - 1.0) * 1_000_000,
        residual_rms_seconds=0.001,
        anchor_count=2,
        quality="good",
    )
    sync = MultiViewSyncCalibration(
        reference_camera="cam_1",
        mappings={"cam_1": calibration, "cam_2": calibration},
    )
    builder = CanonicalTimelineBuilder(max_pairing_error_ms=max_pairing_error_ms)
    return builder.build(
        reference_view_id="cam_1",
        reference_observations=reference_obs,
        secondary_view_id="cam_2",
        secondary_observations=secondary_obs,
        sync=sync,
        secondary_camera_id="cam_2",
        orientations={"cam_1": CourtOrientation.mirror_y, "cam_2": CourtOrientation.mirror_x},
    )


def test_timeline_ticks_follow_reference_frames():
    ref = [_obs("cam_1", i, i / 30.0, 4.0, 8.0) for i in range(4)]
    sec = [_obs("cam_2", i, i / 30.0 + 0.5, 16.0, 36.0) for i in range(4)]
    ticks = _build(ref, sec)

    assert len(ticks) == 4
    assert [t.reference_frame_index for t in ticks] == [0, 1, 2, 3]
    assert ticks[0].take_timestamp_ms == pytest.approx(0.0)
    assert ticks[3].take_timestamp_ms == pytest.approx(3.0 / 30.0 * 1000.0)


def test_secondary_pairs_with_zero_error_when_aligned():
    ref = [_obs("cam_1", i, i / 30.0, 4.0, 8.0) for i in range(4)]
    sec = [_obs("cam_2", i, i / 30.0 + 0.5, 16.0, 36.0) for i in range(4)]
    ticks = _build(ref, sec)

    for tick in ticks:
        sec_obs = tick.observations["cam_2"]
        assert sec_obs.view_status == "available"
        assert sec_obs.source_frame_index == tick.reference_frame_index
        assert sec_obs.selection_error_ms is not None
        assert abs(sec_obs.selection_error_ms) <= 1.0


def test_secondary_out_of_tolerance_is_unavailable():
    # reference 密（每帧），secondary 稀疏（每 3 帧），配对误差超容差时 unavailable。
    ref = [_obs("cam_1", i, i / 30.0, 4.0, 8.0) for i in range(4)]
    sec = [_obs("cam_2", i, i / 10.0, 16.0, 36.0) for i in range(2)]  # 0.0, 0.1
    ticks = _build(ref, sec, offset_seconds=0.0, max_pairing_error_ms=20.0)

    # ref0(0.0) → 对齐 sec0；ref3(0.1) → 对齐 sec1：available。
    # ref1(0.0333)、ref2(0.0667) → 最近 sec 误差 0.0333 > 0.02：unavailable。
    assert ticks[0].observations["cam_2"].view_status == "available"
    assert ticks[3].observations["cam_2"].view_status == "available"
    assert ticks[1].observations["cam_2"].view_status == "unavailable"
    assert ticks[2].observations["cam_2"].view_status == "unavailable"


def test_secondary_missing_camera_mapping_unavailable():
    ref = [_obs("cam_1", i, i / 30.0, 4.0, 8.0) for i in range(3)]
    sec = [_obs("cam_2", i, i / 30.0, 16.0, 36.0) for i in range(3)]
    calibration = SyncCalibration(
        reference_camera="cam_1",
        camera_id="cam_2",
        offset_seconds=0.5,
        rate=1.0,
        drift_ppm=0.0,
        residual_rms_seconds=0.001,
        anchor_count=2,
        quality="good",
    )
    sync = MultiViewSyncCalibration(reference_camera="cam_1", mappings={"cam_1": calibration})
    ticks = CanonicalTimelineBuilder().build(
        reference_view_id="cam_1",
        reference_observations=ref,
        secondary_view_id="cam_2",
        secondary_observations=sec,
        sync=sync,
        secondary_camera_id="cam_2",
        orientations={"cam_1": CourtOrientation.mirror_y, "cam_2": CourtOrientation.mirror_x},
    )
    for tick in ticks:
        assert tick.observations["cam_2"].view_status == "unavailable"


def test_no_sync_means_secondary_unavailable():
    ref = [_obs("cam_1", i, i / 30.0, 4.0, 8.0) for i in range(3)]
    sec = [_obs("cam_2", i, i / 30.0, 16.0, 36.0) for i in range(3)]
    ticks = CanonicalTimelineBuilder().build(
        reference_view_id="cam_1",
        reference_observations=ref,
        secondary_view_id="cam_2",
        secondary_observations=sec,
        sync=None,  # sync authority unavailable
        secondary_camera_id="cam_2",
        orientations={"cam_1": CourtOrientation.mirror_y, "cam_2": CourtOrientation.mirror_x},
    )
    for tick in ticks:
        assert tick.observations["cam_2"].view_status == "unavailable"


def test_reference_obs_always_available_and_normalized():
    ref = [_obs("cam_1", i, i / 30.0, 4.0, 8.0) for i in range(2)]
    sec = [_obs("cam_2", i, i / 30.0 + 0.5, 16.0, 36.0) for i in range(2)]
    ticks = _build(ref, sec)

    # cam_1 orientation = mirror_y: local y=8 (near) -> canonical y=36；local x=4 -> 4。
    ref_obs = ticks[0].observations["cam_1"]
    assert ref_obs.view_status == "available"
    assert ref_obs.canonical_x_ft == pytest.approx(4.0)
    assert ref_obs.canonical_y_ft == pytest.approx(44.0 - 8.0)

    # cam_2 orientation = mirror_x: local x=16 -> canonical x=4；y=36 -> 36。
    sec_obs = ticks[0].observations["cam_2"]
    assert sec_obs.canonical_x_ft == pytest.approx(20.0 - 16.0)
    assert sec_obs.canonical_y_ft == pytest.approx(36.0)


def test_missing_orientation_raises():
    ref = [_obs("cam_1", 0, 0.0, 4.0, 8.0)]
    sec = [_obs("cam_2", 0, 0.5, 16.0, 36.0)]

    with pytest.raises(ValueError, match="orientation"):
        CanonicalTimelineBuilder().build(
            reference_view_id="cam_1",
            reference_observations=ref,
            secondary_view_id="cam_2",
            secondary_observations=sec,
            sync=None,
            secondary_camera_id="cam_2",
            orientations={"cam_1": CourtOrientation.mirror_y},  # cam_2 缺失
        )
