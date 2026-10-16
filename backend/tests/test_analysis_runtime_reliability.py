"""运行时资源与生命周期回归。"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from types import SimpleNamespace
from pathlib import Path
import os
import shutil

import pytest

from app.schemas.video import VideoMetadata
from app.services import analysis_pipeline as pipeline_module
from app.services.job_orchestration import AnalysisWorkerRuntime
from app.services.storage_service import StorageService
from app.services.tmp_cleanup import purge_stale_tmp


class _FakeCapture:
    def __init__(self, *, opened: bool) -> None:
        self.opened = opened
        self.release_count = 0

    def isOpened(self) -> bool:
        return self.opened

    def get(self, _property: int) -> float:
        return 30.0

    def release(self) -> None:
        self.release_count += 1


@pytest.mark.parametrize("opened", [False, True])
def test_run_tracking_releases_capture_when_setup_fails(monkeypatch, opened: bool) -> None:
    capture = _FakeCapture(opened=opened)
    fake_cv2 = SimpleNamespace(
        VideoCapture=lambda _path: capture,
        CAP_PROP_FPS=1,
        CAP_PROP_FRAME_COUNT=2,
        CAP_PROP_FRAME_WIDTH=3,
        CAP_PROP_FRAME_HEIGHT=4,
    )
    monkeypatch.setitem(sys.modules, "cv2", fake_cv2)

    class _TimingProvider:
        duration_seconds = 1.0

        @classmethod
        def from_media(cls, *_args, **_kwargs):
            return cls()

    monkeypatch.setattr(pipeline_module, "FrameTimingProvider", _TimingProvider)
    monkeypatch.setattr(pipeline_module, "resolve_effective_fps", lambda *_args: SimpleNamespace(effective_fps=30.0))

    def fail_window_setup(**_kwargs):
        raise RuntimeError("forced analysis-window setup failure")

    monkeypatch.setattr(pipeline_module, "resolve_analysis_window", fail_window_setup)
    pipeline = pipeline_module.AnalysisPipeline.__new__(pipeline_module.AnalysisPipeline)
    pipeline.settings = SimpleNamespace(pre_roll_ms=0, post_roll_ms=0)
    video = VideoMetadata(
        id="video-test",
        original_filename="test.mp4",
        size_bytes=1,
        path="/tmp/test.mp4",
        uploaded_at=datetime.now(UTC),
    )

    with pytest.raises(RuntimeError):
        pipeline._run_tracking(
            job_id="job-test",
            video=video,
            homography=[],
            video_id="video-test",
            calibration_id=None,
            calibration_keypoints=None,
            frame_stride=1,
        )

    assert capture.release_count == 1


@pytest.mark.parametrize(
    ("error_status", "expected_status"),
    [("failed", "failed"), ("unavailable", "unavailable")],
)
def test_unusable_tracking_overlay_never_reports_overlay_video_available(
    monkeypatch, error_status: str, expected_status: str
) -> None:
    pipeline = pipeline_module.AnalysisPipeline.__new__(pipeline_module.AnalysisPipeline)
    pipeline.settings = SimpleNamespace(
        enable_analysis_overlay_video=True,
        enable_position_visualizations=False,
        visualization_language="zh",
    )
    monkeypatch.setattr(
        pipeline,
        "_load_visualization_inputs",
        lambda _job_id: ({}, {"tracking_overlay": (error_status, "tracking overlay unusable")}),
    )

    class _OverlayWriterMustNotRun:
        def __init__(self, **_kwargs):
            raise AssertionError("invalid upstream input must block overlay video generation")

    monkeypatch.setattr(pipeline_module, "OverlayVideoWriter", _OverlayWriterMustNotRun)
    fields = pipeline._run_visualization(job_id="job-test", video=SimpleNamespace(path="/tmp/input.mp4"))

    assert fields.analysis_overlay_video_status == expected_status
    assert fields.analysis_overlay_video_path is None


def test_purge_stale_tmp_removes_old_orphans_but_keeps_recent_and_running(tmp_path: Path) -> None:
    root = tmp_path / "tmp"
    root.mkdir()
    placeholder = root / ".gitkeep"
    placeholder.touch()
    active = root / "job-active"
    active.mkdir()
    active_file = active / "partial.bin"
    active_file.write_text("active")
    stale = root / "job-finished"
    stale.mkdir()
    stale_file = stale / "partial.bin"
    stale_file.write_text("stale")
    recent = root / "orphan-recent"
    recent.mkdir()
    recent_file = recent / "partial.bin"
    recent_file.write_text("recent")
    normal = root / "job-normal-finish"
    normal.mkdir()
    (normal / "partial.bin").write_text("normal")

    runtime = AnalysisWorkerRuntime.__new__(AnalysisWorkerRuntime)
    runtime.store = SimpleNamespace(
        storage=SimpleNamespace(tmp_dir=root, delete_path_tree=lambda path: shutil.rmtree(path, ignore_errors=True))
    )
    runtime._cleanup_tmp("job-normal-finish")
    assert not normal.exists()

    now = 10_000_000.0
    old_mtime = now - 25 * 60 * 60
    recent_mtime = now - 60 * 60
    for path in (active, active_file, stale, stale_file, placeholder):
        os.utime(path, (old_mtime, old_mtime))
    for path in (recent, recent_file):
        os.utime(path, (recent_mtime, recent_mtime))

    storage = SimpleNamespace(tmp_dir=root)
    job_store = SimpleNamespace(
        list=lambda: [SimpleNamespace(id="job-active", canonicalStatus="running")]
    )
    removed = purge_stale_tmp(24, storage=storage, job_store=job_store, now=now)

    assert removed == 1
    assert placeholder.exists()
    assert active.exists()
    assert recent.exists()
    assert not stale.exists()


def test_purge_stale_tmp_fails_closed_when_job_state_is_unavailable(tmp_path: Path) -> None:
    root = tmp_path / "tmp"
    stale = root / "job-possibly-active"
    stale.mkdir(parents=True)
    old_mtime = 1_000_000.0
    os.utime(stale, (old_mtime, old_mtime))

    class _UnavailableJobStore:
        def list(self):
            raise OSError("control database unavailable")

    removed = purge_stale_tmp(
        1,
        storage=SimpleNamespace(tmp_dir=root),
        job_store=_UnavailableJobStore(),
        now=old_mtime + 2 * 60 * 60,
    )

    assert removed == 0
    assert stale.exists()


def test_capture_take_lookup_failure_uses_separate_degraded_root(monkeypatch, tmp_path: Path) -> None:
    from app import database

    class _BrokenQuery:
        def filter(self, *_args):
            return self

        def first(self):
            raise OSError("database is unavailable")

    class _BrokenDb:
        def query(self, *_args):
            return _BrokenQuery()

        def close(self):
            pass

    monkeypatch.setattr(database, "get_session_factory", lambda: lambda: _BrokenDb())
    settings = SimpleNamespace(
        ensure_data_dirs=lambda: None,
        resolved_uploads_dir=tmp_path / "uploads",
        resolved_outputs_dir=tmp_path / "outputs",
        resolved_calibrations_dir=tmp_path / "calibrations",
        resolved_tmp_dir=tmp_path / "tmp",
    )
    storage = StorageService(settings)
    job_id = "job-degraded-test"
    StorageService.unregister_capture_job(job_id)

    try:
        root = storage.resolve_capture_job_root(job_id, "take-unavailable")
        assert root == tmp_path / "outputs" / "_degraded" / job_id
        assert storage.ball_overlay_json_path(job_id).parent == root
        assert storage._capture_job_degradation[job_id] == "capture_session_lookup_failed"
        assert storage._safe_join(root, "nested", "artifact.json") == root / "nested" / "artifact.json"
    finally:
        StorageService.unregister_capture_job(job_id)


def test_safe_join_rejects_traversal_absolute_paths_and_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "authorized"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    assert StorageService._safe_join(root, "nested", "artifact.json") == root / "nested" / "artifact.json"
    with pytest.raises(ValueError):
        StorageService._safe_join(root, "../outside/escape.json")
    with pytest.raises(ValueError):
        StorageService._safe_join(root, outside / "absolute.json")

    link = root / "external"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip("symlinks are unavailable on this filesystem")
    with pytest.raises(ValueError):
        StorageService._safe_join(root, "external", "escape.json")


def test_degraded_capture_storage_is_persisted_on_job_summary(monkeypatch, tmp_path: Path) -> None:
    from app import database
    from app.core.config import Settings
    from app.schemas.analysis import AnalysisJobCreate, AnalysisUploadMetadata
    from app.services.job_orchestration import AnalysisWorkerRuntime, JobStore

    class _BrokenQuery:
        def filter(self, *_args):
            return self

        def first(self):
            raise OSError("database is unavailable")

    class _BrokenDb:
        def query(self, *_args):
            return _BrokenQuery()

        def close(self):
            pass

    monkeypatch.setattr(database, "get_session_factory", lambda: lambda: _BrokenDb())
    storage = StorageService(Settings(
        uploads_dir=tmp_path / "uploads",
        outputs_dir=tmp_path / "outputs",
        calibrations_dir=tmp_path / "calibrations",
        tmp_dir=tmp_path / "tmp",
    ))
    store = JobStore(storage)
    metadata = AnalysisUploadMetadata(
        fileName="capture.mp4", matchTitle="test", venue="test", matchDate="2026-10-05",
        matchFormat="singles", cameraAngle="baseline", athleteLabel="test", level="test",
        capture_take_id="take-unavailable",
    )
    claimed = store.claim(store.create_job(AnalysisJobCreate(metadata=metadata)).id, "worker-degraded")
    assert claimed is not None

    runtime = AnalysisWorkerRuntime(store, pipeline_factory=lambda: None, on_completed=lambda *_args: None)
    trace = runtime._open_run_trace(claimed)

    assert trace.path == tmp_path / "outputs" / "_degraded" / claimed.id / "run_trace.jsonl"
    persisted = store.get(claimed.id)
    assert persisted is not None
    assert persisted.artifactStorageStatus == "degraded"
    assert persisted.artifactStorageReason == "capture_session_lookup_failed"
    StorageService.unregister_capture_job(claimed.id)


def test_failed_second_attempt_cannot_expose_first_attempt_completed_result(monkeypatch, tmp_path: Path) -> None:
    import threading

    from app.core.config import Settings
    from app.schemas.analysis import AnalysisJobCreate, AnalysisStage, AnalysisUploadMetadata
    from app.services.analysis_progress import stage_ids
    from app.services.job_orchestration import AnalysisWorkerRuntime, JobStore

    settings = Settings(
        uploads_dir=tmp_path / "uploads",
        outputs_dir=tmp_path / "outputs",
        calibrations_dir=tmp_path / "calibrations",
        tmp_dir=tmp_path / "tmp",
    )
    storage = StorageService(settings)
    store = JobStore(storage)
    metadata = AnalysisUploadMetadata(
        fileName="retry.mp4", matchTitle="test", venue="test", matchDate="2026-10-05",
        matchFormat="singles", cameraAngle="baseline", athleteLabel="test", level="test",
    )
    job = store.claim(store.create_job(AnalysisJobCreate(metadata=metadata)).id, "worker-retry")
    assert job is not None
    for stage_id in list(stage_ids("single_view"))[: list(stage_ids("single_view")).index("video-read")]:
        job = store.mark_stage(job, AnalysisStage(id=stage_id, label=stage_id, status="done", detail="done", progress=100))
    job = store.mark_stage(job, AnalysisStage(id="video-read", label="video-read", status="active", detail="running", progress=10))

    calls = {"count": 0}

    class _Executor:
        def execute(self, current_job, _token, _progress_callback):
            calls["count"] += 1
            if calls["count"] == 1:
                storage.write_json(storage.output_json_path(current_job.id), {"status": "completed", "message": "stale"})
            raise RuntimeError(f"attempt {calls['count']} failed")

    monkeypatch.setattr(
        "app.services.analysis_executor_dispatch.resolve_executor",
        lambda *args, **kwargs: _Executor(),
    )
    runtime = AnalysisWorkerRuntime(store, pipeline_factory=lambda: None, on_completed=lambda *_args: None)

    final = runtime._execute_pipeline(job, threading.Event())
    result_path = storage.output_json_path(job.id)

    assert calls["count"] == 2
    assert final.canonicalStatus == "failed"
    assert store.get(job.id).canonicalStatus == "failed"
    assert not result_path.exists()
    assert storage.artifact_attempt_is_incomplete(job.id)


def test_capture_take_without_session_dir_is_a_valid_non_degraded_result(monkeypatch, tmp_path: Path) -> None:
    from app import database

    take = SimpleNamespace(session_dir=None)

    class _Query:
        def filter(self, *_args):
            return self

        def first(self):
            return take

    class _Db:
        def query(self, *_args):
            return _Query()

        def close(self):
            pass

    monkeypatch.setattr(database, "get_session_factory", lambda: lambda: _Db())
    job_id = "job-empty-session-test"
    StorageService.unregister_capture_job(job_id)
    try:
        assert StorageService.register_capture_job_from_take(job_id, "take-empty") is None
        assert StorageService.capture_job_degradation_reason(job_id) is None
    finally:
        StorageService.unregister_capture_job(job_id)


def test_concurrent_first_capture_root_resolution_is_consistent(monkeypatch, tmp_path: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor

    from app import database

    session_dir = tmp_path / "capture-session"
    session_dir.mkdir()
    take = SimpleNamespace(session_dir=str(session_dir))

    class _Query:
        def filter(self, *_args):
            return self

        def first(self):
            return take

    class _Db:
        def query(self, *_args):
            return _Query()

        def close(self):
            pass

    monkeypatch.setattr(database, "get_session_factory", lambda: lambda: _Db())
    settings = SimpleNamespace(
        ensure_data_dirs=lambda: None,
        resolved_uploads_dir=tmp_path / "uploads",
        resolved_outputs_dir=tmp_path / "outputs",
        resolved_calibrations_dir=tmp_path / "calibrations",
        resolved_tmp_dir=tmp_path / "tmp",
    )
    storage = StorageService(settings)
    job_id = "job-concurrent-root-test"
    StorageService.unregister_capture_job(job_id)

    def resolve(method_name: str) -> Path:
        storage.resolve_capture_job_root(job_id, "take-concurrent")
        return getattr(storage, method_name)(job_id)

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            roots = list(pool.map(resolve, ["tracking_overlay_json_path", "ball_trajectory_json_path"]))
        assert {path.parent for path in roots} == {session_dir / "analysis" / job_id}
        assert (session_dir / "analysis" / job_id).is_dir()
    finally:
        StorageService.unregister_capture_job(job_id)


def test_degraded_artifacts_remain_readable_after_restart_and_reconnect(monkeypatch, tmp_path: Path) -> None:
    from app.core.config import Settings

    settings = Settings(uploads_dir=tmp_path / "uploads", outputs_dir=tmp_path / "outputs",
                        calibrations_dir=tmp_path / "calibrations", tmp_dir=tmp_path / "tmp")
    storage = StorageService(settings)
    session = tmp_path / "external-session"
    monkeypatch.setattr(StorageService, "_read_capture_session_dir", classmethod(lambda _cls, _take: session))
    root = storage.resolve_capture_job_root("job-reconnect", "take-reconnect")
    storage.write_json(storage.output_json_path("job-reconnect"), {"status": "failed"})
    assert root == storage.outputs_dir / "_degraded" / "job-reconnect"
    # A fresh process has no registry and the external volume is now accessible.
    StorageService.unregister_capture_job("job-reconnect")
    session.mkdir()
    restarted = StorageService(settings)
    assert restarted.resolve_capture_job_root("job-reconnect", "take-reconnect") == root
    assert restarted.read_json(restarted.output_json_path("job-reconnect")) == {"status": "failed"}
    assert restarted.capture_job_degradation_reason("job-reconnect") == "capture_storage_unavailable"
    assert not (session / "analysis" / "job-reconnect").exists()
