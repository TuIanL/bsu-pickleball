"""融合管线端到端 —— predict → associate → quality → pair → fusion → update 循环。"""

from __future__ import annotations

import pytest

from app.services.dual_camera_sync import SyncCalibration
from app.vision.multiview.association import PlayerAssociation
from app.vision.multiview.court_frame import CourtOrientation
from app.vision.multiview.fusion import FusionConfig
from app.vision.multiview.global_filter import GlobalTrackFilter
from app.vision.multiview.pipeline import run_fusion_pipeline
from app.vision.multiview.sync import MultiViewSyncCalibration
from app.vision.multiview.types import ViewObservation


def _obs(view_id, player_id, frame, ts, x, y):
    return ViewObservation(
        view_id=view_id,
        source_frame_index=frame,
        timestamp_seconds=ts,
        local_x_ft=x,
        local_y_ft=y,
        view_player_id=player_id,
        projection_confidence=0.7,
        footpoint_method="pose_ankle",
        confidence=0.9,
    )


def _good_sync(offset=0.5):
    calibration = SyncCalibration(
        reference_camera="cam_1",
        camera_id="cam_2",
        offset_seconds=offset,
        rate=1.0,
        drift_ppm=0.0,
        residual_rms_seconds=0.001,
        anchor_count=2,
        quality="good",
    )
    return MultiViewSyncCalibration(reference_camera="cam_1", mappings={"cam_2": calibration})


def test_pipeline_dual_view_aligned_measurements():
    ref = [_obs("cam_1", "A", i, i / 30.0, 5.0 + i, 8.0) for i in range(4)]
    sec = [_obs("cam_2", "X", i, i / 30.0 + 0.5, 5.0 + i, 8.0) for i in range(4)]
    result = run_fusion_pipeline(
        reference_view_id="cam_1",
        reference_observations=ref,
        secondary_view_id="cam_2",
        secondary_observations=sec,
        reference_orientation=CourtOrientation.identity,
        secondary_orientation=CourtOrientation.identity,
        sync=_good_sync(),
        secondary_camera_id="cam_2",
        max_pairing_error_ms=1000.0 / 30.0,
        config=FusionConfig(),
        global_players=[PlayerAssociation("g1", "A", "X")],
    )
    assert len(result.measurements) == 4
    for m in result.measurements:
        assert m.global_player_id == "g1"
        assert m.fusion_status in ("dual_observed", "single_view_fallback")
        assert m.metric_eligible is True
    # 单调移动：x 依次递增。
    xs = [m.x_ft for m in result.measurements]
    assert xs == sorted(xs)
    assert xs[0] == pytest.approx(5.0, abs=0.01)


def test_pipeline_filter_updated_and_predicts():
    ref = [_obs("cam_1", "A", i, i / 30.0, 5.0 + i, 8.0) for i in range(4)]
    sec = [_obs("cam_2", "X", i, i / 30.0 + 0.5, 5.0 + i, 8.0) for i in range(4)]
    filter_ = GlobalTrackFilter()
    run_fusion_pipeline(
        reference_view_id="cam_1",
        reference_observations=ref,
        secondary_view_id="cam_2",
        secondary_observations=sec,
        reference_orientation=CourtOrientation.identity,
        secondary_orientation=CourtOrientation.identity,
        sync=_good_sync(),
        secondary_camera_id="cam_2",
        max_pairing_error_ms=1000.0 / 30.0,
        config=FusionConfig(),
        global_players=[PlayerAssociation("g1", "A", "X")],
        filter_=filter_,
    )
    # 真实观测回灌后，filter 有 g1 状态并可预测。
    assert filter_.state_for("g1") is not None
    assert "g1" in filter_.predict(0.1)


def test_pipeline_secondary_unavailable_single_fallback():
    # sync offset=0.5，但 secondary 帧时间错开 5s → 配对误差远超容差 → 该路 unavailable。
    ref = [_obs("cam_1", "A", i, i / 30.0, 5.0 + i, 8.0) for i in range(4)]
    sec = [_obs("cam_2", "X", i, i / 30.0 + 5.0, 5.0 + i, 8.0) for i in range(4)]  # 错开 5s
    result = run_fusion_pipeline(
        reference_view_id="cam_1",
        reference_observations=ref,
        secondary_view_id="cam_2",
        secondary_observations=sec,
        reference_orientation=CourtOrientation.identity,
        secondary_orientation=CourtOrientation.identity,
        sync=_good_sync(),  # offset=0.5
        secondary_camera_id="cam_2",
        max_pairing_error_ms=1000.0 / 30.0,
        config=FusionConfig(),
        global_players=[PlayerAssociation("g1", "A", "X")],
    )
    assert result.measurements
    for m in result.measurements:
        assert m.fusion_status == "single_view_fallback"
        assert m.measurement_source == "reference"


def test_pipeline_automatic_association_pass():
    # 不预置关联：管线内部先跑关联器建立 A↔X。
    ref = [_obs("cam_1", "A", i, i / 30.0, 5.0, 8.0) for i in range(4)]
    sec = [_obs("cam_2", "X", i, i / 30.0 + 0.5, 5.2, 8.1) for i in range(4)]
    result = run_fusion_pipeline(
        reference_view_id="cam_1",
        reference_observations=ref,
        secondary_view_id="cam_2",
        secondary_observations=sec,
        reference_orientation=CourtOrientation.identity,
        secondary_orientation=CourtOrientation.identity,
        sync=_good_sync(),
        secondary_camera_id="cam_2",
        max_pairing_error_ms=1000.0 / 30.0,
        config=FusionConfig(),
    )
    assert result.global_players
    g = result.global_players[0]
    assert g.reference_view_player_id == "A"
    assert g.secondary_view_player_id == "X"
    assert result.measurements
    assert all(m.global_player_id == g.global_player_id for m in result.measurements)


def test_pipeline_mirror_orientations_align_cross_view():
    # 对向机位典型：ref mirror_y、sec mirror_x；同一物理点在两路 canonical 下接近。
    # ref local (4,8) → canonical (4, 44-8)=(4,36)。
    # sec 需 mirror_x 后 canonical=(4,36) → local (20-4, 36)=(16,36)。
    ref = [_obs("cam_1", "A", i, i / 30.0, 4.0, 8.0) for i in range(3)]
    sec = [_obs("cam_2", "X", i, i / 30.0 + 0.5, 16.0, 36.0) for i in range(3)]
    result = run_fusion_pipeline(
        reference_view_id="cam_1",
        reference_observations=ref,
        secondary_view_id="cam_2",
        secondary_observations=sec,
        reference_orientation=CourtOrientation.mirror_y,
        secondary_orientation=CourtOrientation.mirror_x,
        sync=_good_sync(),
        secondary_camera_id="cam_2",
        max_pairing_error_ms=1000.0 / 30.0,
        config=FusionConfig(),
        global_players=[PlayerAssociation("g1", "A", "X")],
    )
    # 两路 canonical 化后一致 → dual_observed，融合 x 在 4 附近。
    assert result.measurements
    assert all(m.fusion_status == "dual_observed" for m in result.measurements)
    assert all(m.x_ft == pytest.approx(4.0, abs=0.01) for m in result.measurements)
    assert all(m.y_ft == pytest.approx(36.0, abs=0.01) for m in result.measurements)
