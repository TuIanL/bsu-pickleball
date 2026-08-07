from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.capture_storage_service import (
    CaptureStorageError,
    capture_storage_is_available,
    create_capture_storage_plan,
    normalize_storage_root,
    validate_storage_root,
    write_json_atomic,
)
from app.services.storage_service import StorageService


def test_existing_captures_directory_is_reused(tmp_path: Path):
    captures = tmp_path / "captures"
    root, normalized = normalize_storage_root(str(captures))
    assert root == tmp_path
    assert normalized == captures

    plan = create_capture_storage_plan("take_001", str(captures))
    assert plan.captures_root == captures
    assert plan.take_dir.parent.parent == captures
    assert (plan.take_dir / "media").is_dir()
    assert (plan.take_dir / "timeline").is_dir()


def test_take_directory_is_rejected(tmp_path: Path):
    take_dir = tmp_path / "captures" / "2026-07-12" / "take_old"
    take_dir.mkdir(parents=True)
    with pytest.raises(CaptureStorageError, match="不能选择某次录制目录"):
        normalize_storage_root(str(take_dir))


def test_same_take_id_cannot_overwrite_non_empty_directory(tmp_path: Path):
    plan = create_capture_storage_plan("take_001", str(tmp_path))
    (plan.take_dir / "manifest.json").write_text("{}", encoding="utf-8")
    with pytest.raises(CaptureStorageError, match="非空"):
        create_capture_storage_plan("take_001", str(tmp_path))


def test_analysis_artifact_paths_use_logical_capture_references(tmp_path: Path):
    plan = create_capture_storage_plan("take_artifacts", str(tmp_path))
    storage = StorageService()
    StorageService.register_capture_job("job_artifacts", plan.take_dir)
    try:
        path = storage.ball_overlay_json_path("job_artifacts")
        assert path == plan.analysis_dir / "job_artifacts" / "ball_overlay.json"
        assert storage.logical_artifact_reference("job_artifacts", path) == ("analysis/job_artifacts/ball_overlay.json")
    finally:
        StorageService.unregister_capture_job("job_artifacts")


def test_storage_service_keeps_legacy_artifact_paths(tmp_path: Path):
    settings = type(
        "SettingsStub",
        (),
        {
            "ensure_data_dirs": lambda self: None,
            "resolved_uploads_dir": tmp_path / "uploads",
            "resolved_outputs_dir": tmp_path / "outputs",
            "resolved_calibrations_dir": tmp_path / "calibrations",
            "resolved_tmp_dir": tmp_path / "tmp",
        },
    )()
    storage = StorageService(settings)
    assert storage.logical_artifact_reference("legacy_job", tmp_path / "outputs" / "legacy_job.json") == str(
        tmp_path / "outputs" / "legacy_job.json"
    )


def test_atomic_event_file_write_preserves_previous_snapshot_on_replace_error(tmp_path: Path, monkeypatch):
    target = tmp_path / "timeline" / "events.json"
    target.parent.mkdir()
    target.write_text('{"version": 1}', encoding="utf-8")

    def fail_replace(*_args):
        raise OSError("simulated media failure")

    monkeypatch.setattr("app.services.capture_storage_service.os.replace", fail_replace)
    with pytest.raises(OSError, match="simulated media failure"):
        write_json_atomic(target, {"version": 2})
    assert target.read_text(encoding="utf-8") == '{"version": 1}'


@pytest.mark.parametrize(
    "method_name",
    [
        "analysis_overlay_video_path",
        "ball_overlay_json_path",
        "detections_jsonl_path",
        "heatmaps_manifest_json_path",
        "heatmaps_dir",
        "scatter_plots_manifest_json_path",
        "player_render_trajectory_path",
    ],
)
def test_all_analysis_artifact_kinds_are_under_capture_analysis_directory(tmp_path: Path, method_name: str):
    plan = create_capture_storage_plan("take_all_artifacts", str(tmp_path))
    storage = StorageService()
    StorageService.register_capture_job("job_all_artifacts", plan.take_dir)
    try:
        path = getattr(storage, method_name)("job_all_artifacts")
        assert plan.analysis_dir / "job_all_artifacts" in Path(path).parents
    finally:
        StorageService.unregister_capture_job("job_all_artifacts")


def test_missing_capture_media_is_reported_unavailable(tmp_path: Path):
    assert capture_storage_is_available(str(tmp_path / "ejected-volume")) is False


def test_storage_validation_rejects_insufficient_free_space(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "app.services.capture_storage_service.shutil.disk_usage",
        lambda _path: SimpleNamespace(free=90, total=100, used=10),
    )
    with pytest.raises(CaptureStorageError, match="空间不足"):
        validate_storage_root(str(tmp_path), min_free_space_bytes=100)
