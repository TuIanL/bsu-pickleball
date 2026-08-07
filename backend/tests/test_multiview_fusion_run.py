"""MultiViewFusionRun —— 运行实体所有权、job-level gate、等待语义、产物归属。"""

from __future__ import annotations

from app.services.dual_camera_sync import SyncCalibration
from app.vision.multiview.court_frame import CanonicalCourtFrameDefinition, CourtOrientation
from app.vision.multiview.fusion_run import MultiViewFusionRun, default_run_output_dir
from app.vision.multiview.sync import MultiViewSyncCalibration
from app.vision.multiview.view_input import MultiViewViewInput


def _view(view_id: str, orientation: CourtOrientation | None) -> MultiViewViewInput:
    return MultiViewViewInput(
        view_id=view_id,
        capture_track_id=f"tr_{view_id}",
        video_id=f"vid_{view_id}",
        analysis_job_id=f"job_{view_id}",
        calibration_id=f"calib_{view_id}",
        court_orientation=orientation,
    )


def _good_sync() -> MultiViewSyncCalibration:
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
    return MultiViewSyncCalibration(
        reference_camera="cam_1",
        mappings={"cam_1": calibration, "cam_2": calibration},
    )


def test_run_holds_inputs_and_output_ownership():
    run = MultiViewFusionRun.create(
        capture_take_id="take_1",
        source_analysis_job_ids=["job_cam_1", "job_cam_2"],
        view_inputs=[_view("cam_1", CourtOrientation.mirror_y), _view("cam_2", CourtOrientation.mirror_x)],
        sync_calibration_ref=_good_sync(),
        canonical_frame_ref=CanonicalCourtFrameDefinition.create("take_1", "北端", "南端"),
        output_dir=default_run_output_dir("/data/take_1/analysis", "mvf_abc"),
    )
    assert run.capture_take_id == "take_1"
    assert run.source_analysis_job_ids == ["job_cam_1", "job_cam_2"]
    assert set(run.view_ids()) == {"cam_1", "cam_2"}
    assert run.view_input("cam_2").analysis_job_id == "job_cam_2"
    # fused artifact 归属 Run 自身产物目录，不挂任何 cam job / take。
    assert str(run.output_dir).endswith("analysis/multiview/mvf_abc")


def test_eligibility_ready_when_orientations_and_sync_ok():
    run = MultiViewFusionRun.create(
        capture_take_id="take_1",
        source_analysis_job_ids=["job_cam_1", "job_cam_2"],
        view_inputs=[_view("cam_1", CourtOrientation.mirror_y), _view("cam_2", CourtOrientation.mirror_x)],
        sync_calibration_ref=_good_sync(),
    )
    result = run.check_eligibility()
    assert result.ready is True
    assert result.sync_gate == "fuse"


def test_cam_2_not_auto_inferred_as_rotate_180():
    # 硬断言：cam_2 缺 orientation 时，Run 不自动推断 rotate_180。
    run = MultiViewFusionRun.create(
        capture_take_id="take_1",
        source_analysis_job_ids=["job_cam_1", "job_cam_2"],
        view_inputs=[_view("cam_1", CourtOrientation.mirror_y), _view("cam_2", None)],
        sync_calibration_ref=_good_sync(),
    )
    result = run.check_eligibility()
    assert result.ready is False
    assert "cam_2" in result.missing_orientations
    # 校验后 cam_2 仍为 None（未被填充）。
    assert run.view_input("cam_2").court_orientation is None


def test_eligibility_single_view_when_sync_missing():
    run = MultiViewFusionRun.create(
        capture_take_id="take_1",
        source_analysis_job_ids=["job_cam_1", "job_cam_2"],
        view_inputs=[_view("cam_1", CourtOrientation.mirror_y), _view("cam_2", CourtOrientation.mirror_x)],
        sync_calibration_ref=None,  # sync authority unavailable
    )
    result = run.check_eligibility()
    assert result.ready is False
    assert result.sync_gate == "single_view"


def test_eligibility_degraded_sync_still_fuses():
    degraded = SyncCalibration(
        reference_camera="cam_1",
        camera_id="cam_2",
        offset_seconds=0.5,
        rate=1.0,
        drift_ppm=0.0,
        residual_rms_seconds=0.05,
        anchor_count=2,
        quality="degraded",
        reason="anchor fit residual exceeds threshold",
    )
    sync = MultiViewSyncCalibration(reference_camera="cam_1", mappings={"cam_2": degraded})
    run = MultiViewFusionRun.create(
        capture_take_id="take_1",
        source_analysis_job_ids=["job_cam_1", "job_cam_2"],
        view_inputs=[_view("cam_1", CourtOrientation.mirror_y), _view("cam_2", CourtOrientation.mirror_x)],
        sync_calibration_ref=sync,
    )
    result = run.check_eligibility()
    assert result.ready is True
    assert result.sync_gate == "fuse_degraded"


def test_wait_for_source_jobs_all_completed():
    run = MultiViewFusionRun.create(
        capture_take_id="take_1",
        source_analysis_job_ids=["job_cam_1", "job_cam_2"],
        view_inputs=[_view("cam_1", CourtOrientation.mirror_y), _view("cam_2", CourtOrientation.mirror_x)],
    )
    statuses = {"job_cam_1": "completed", "job_cam_2": "completed"}
    assert run.wait_for_source_jobs(statuses.get) is True


def test_wait_for_source_jobs_fails_on_missing():
    run = MultiViewFusionRun.create(
        capture_take_id="take_1",
        source_analysis_job_ids=["job_cam_1", "job_cam_2"],
        view_inputs=[_view("cam_1", CourtOrientation.mirror_y), _view("cam_2", CourtOrientation.mirror_x)],
    )
    statuses = {"job_cam_1": "completed", "job_cam_2": "failed"}
    assert run.wait_for_source_jobs(statuses.get) is False
