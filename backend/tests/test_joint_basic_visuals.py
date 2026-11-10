from types import SimpleNamespace

import pytest

from app.schemas.pipeline import AnalysisArtifacts
from app.services.joint_basic_visuals import publish_joint_basic_visuals


def setup_case(tmp_path, *, pose=True):
    settings = SimpleNamespace(
        enable_pose_inference=False, enable_ball_detection=False, enable_ball_reconstruction=False,
        rtmpose_config_path="config", rtmpose_checkpoint_path="checkpoint", rtmpose_device="cpu",
        pose_confidence=.3, pose_confidence_exit=.2, pose_keypoint_schema="rtmpose26",
    )
    result = SimpleNamespace(artifacts=AnalysisArtifacts(), stages=[])
    written = {}
    storage = SimpleNamespace(
        read_json=lambda _: {"views": {}},
        fused_player_overlay_json_path=lambda _: tmp_path / "fused.json",
        pose_overlay_json_path=lambda _: tmp_path / "pose.json",
        write_json_atomic=lambda p, data: written.update({str(p): data}),
    )
    job = SimpleNamespace(id="j", enablePoseInference=pose)
    return settings, result, storage, job, written


def test_joint_pose_request_publishes_real_builder_result_and_completed_stage(tmp_path, monkeypatch):
    settings, result, storage, job, written = setup_case(tmp_path)
    monkeypatch.setattr("app.vision.pose.rtmpose26_adapter.RTMPose26Adapter", lambda **kw: object())
    seen = []
    def build(**kw):
        seen.append(kw)
        return {"status": "available", "detail": "observed poses", "frames": []}
    monkeypatch.setattr("app.services.joint_pose_artifacts.build_joint_pose_artifact", build)
    publish_joint_basic_visuals(
        job=job, result=result, storage=storage, settings=settings,
        videos={"cam_1": SimpleNamespace(id="v", path="video.mp4")}, reference_view_id="cam_1",
    )
    assert seen[0]["video_ids"] == {"cam_1": "v"}
    assert result.artifacts.pose_overlay_status == "available"
    assert result.artifacts.pose_overlay_url == "/api/analysis/jobs/j/artifacts/pose-overlay"
    assert result.stages[-1].id == "multiview-visualization" and result.stages[-1].status == "done"
    assert written[str(tmp_path / "pose.json")]["detail"] == "observed poses"


def test_live_visual_progress_follows_existing_joint_stage_graph(tmp_path, monkeypatch):
    from app.services.analysis_progress import build_stage_snapshot, merge_stage_event, validate_stage_snapshot
    from app.services.job_orchestration import stage_from_pipeline
    settings, result, storage, job, _ = setup_case(tmp_path)
    monkeypatch.setattr("app.vision.pose.rtmpose26_adapter.RTMPose26Adapter", lambda **kw: object())
    def build(**kw):
        kw["progress_callback"](1, 2)
        kw["progress_callback"](2, 2)
        return {"status": "available", "detail": "poses", "frames": []}
    monkeypatch.setattr("app.services.joint_pose_artifacts.build_joint_pose_artifact", build)
    stages = build_stage_snapshot("joint_tracking_v2", active_stage="multiview-metrics")
    def progress(event):
        nonlocal stages
        stages = merge_stage_event(stages, stage_from_pipeline(event), "joint_tracking_v2")
    publish_joint_basic_visuals(
        job=job, result=result, storage=storage, settings=settings, videos={},
        reference_view_id="cam_1", progress_callback=progress,
    )
    validate_stage_snapshot(stages, "joint_tracking_v2")
    assert next(s for s in stages if s.id == "multiview-visualization").status == "done"


def test_explicit_pose_off_overrides_global_and_performs_no_postpass(tmp_path):
    settings, result, storage, job, written = setup_case(tmp_path, pose=False)
    settings.enable_pose_inference = True
    def forbidden(_):
        raise AssertionError("disabled inference read source artifacts")
    storage.read_json = forbidden
    publish_joint_basic_visuals(job=job, result=result, storage=storage, settings=settings,
                               videos={}, reference_view_id="cam_1")
    assert not written


def test_requested_pose_failure_does_not_turn_into_success(tmp_path, monkeypatch):
    settings, result, storage, job, written = setup_case(tmp_path)
    monkeypatch.setattr("app.vision.pose.rtmpose26_adapter.RTMPose26Adapter", lambda **kw: object())
    def fail(**kw):
        raise RuntimeError("model failure")
    monkeypatch.setattr("app.services.joint_pose_artifacts.build_joint_pose_artifact", fail)
    with pytest.raises(RuntimeError, match="model failure"):
        publish_joint_basic_visuals(job=job, result=result, storage=storage, settings=settings,
                                   videos={}, reference_view_id="cam_1")
    assert not written
    assert result.artifacts.pose_overlay_status is None


def test_missing_formal_overlay_reports_generation_failure_not_input_media(tmp_path):
    settings, result, storage, job, written = setup_case(tmp_path)
    result.artifacts.fused_player_overlay_detail = "MemoryError: output allocation"
    def missing(_):
        raise FileNotFoundError("fused.json")
    storage.read_json = missing
    with pytest.raises(RuntimeError, match="MemoryError"):
        publish_joint_basic_visuals(job=job, result=result, storage=storage, settings=settings,
                                   videos={}, reference_view_id="cam_1")
    assert not written
