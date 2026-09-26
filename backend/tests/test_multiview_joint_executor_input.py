from app.services.multiview_joint_executor import _deserialize_joint_view_input


def test_joint_serve_candidates_publish_tracking_only_status(tmp_path):
    from types import SimpleNamespace
    from app.schemas.pipeline import AnalysisArtifacts
    from app.services.storage_service import StorageService
    from app.services.multiview_joint_executor import _publish_joint_serve_candidates
    storage = StorageService()
    storage.register_capture_job("serve-smoke", tmp_path)
    session = SimpleNamespace(
        snapshot=lambda: SimpleNamespace(overlay_frames=[]),
        build_player_trajectory_artifact=lambda **kw: None,
    )
    result = SimpleNamespace(artifacts=AnalysisArtifacts())
    _publish_joint_serve_candidates(
        job=SimpleNamespace(id="serve-smoke", videoId="v", frameStride=2),
        result=result, runtime=SimpleNamespace(tracking_session=session),
        storage=storage, fps=30, frame_count=60,
    )
    assert result.artifacts.serve_events_status == "unavailable"
    payload = storage.read_json(storage.serve_events_json_path("serve-smoke"))
    assert payload["events"] == []
    assert "tracking" in payload["detail"]


def test_formal_joint_rejects_disabled_inference_before_opening_media(monkeypatch):
    from types import SimpleNamespace
    import pytest
    import app.services.multiview_joint_executor as module
    monkeypatch.setattr(module, "get_settings", lambda: SimpleNamespace(enable_model_inference=False))
    job = SimpleNamespace(metadata=SimpleNamespace(capture_take_id=None))
    with pytest.raises(RuntimeError, match="人物模型推理未启用"):
        module.MultiViewJointExecutor(None, None).execute(job, None, None)


def test_deserialize_joint_view_input_accepts_persisted_camel_case_payload():
    view = _deserialize_joint_view_input(
        {
            "cameraSlot": "cam_1",
            "captureTrackId": "track-1",
            "cameraId": "174",
            "videoId": "rec-1",
            "calibrationId": "calib-1",
            "courtOrientation": "identity",
        }
    )

    assert view.camera_slot == "cam_1"
    assert view.capture_track_id == "track-1"
    assert view.camera_id == "174"
    assert view.video_id == "rec-1"
    assert view.calibration_id == "calib-1"
    assert view.court_orientation == "identity"


def test_deserialize_joint_view_input_preserves_internal_snake_case_payload():
    view = _deserialize_joint_view_input(
        {
            "camera_slot": "cam_2",
            "camera_id": "175",
            "video_id": "rec-2",
            "calibration_id": "calib-2",
            "court_orientation": "rotate_180",
        }
    )

    assert view.camera_slot == "cam_2"
    assert view.camera_id == "175"
    assert view.video_id == "rec-2"
    assert view.calibration_id == "calib-2"
    assert view.court_orientation == "rotate_180"
