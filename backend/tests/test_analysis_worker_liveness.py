"""跨进程分析控制面、Worker lease 和失联恢复测试。"""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.schemas.analysis import (
    AnalysisJobCreate,
    AnalysisJobSummary,
    AnalysisUploadMetadata,
    MultiViewCreateRequest,
    MultiViewViewPayload,
)
from app.services.job_orchestration import AnalysisWorkerRuntime, JobStore, build_stages
from app.services.storage_service import StorageService


def make_storage(tmp_path) -> StorageService:
    from app.core.config import Settings

    settings = Settings(
        uploads_dir=tmp_path / "uploads",
        outputs_dir=tmp_path / "outputs",
        calibrations_dir=tmp_path / "calibrations",
        tmp_dir=tmp_path / "tmp",
    )
    return StorageService(settings)


def make_metadata(**overrides) -> AnalysisUploadMetadata:
    fields = {
        "fileName": "liveness.mp4",
        "matchTitle": "心跳测试",
        "venue": "测试场",
        "matchDate": "2026-08-24",
        "matchFormat": "singles",
        "cameraAngle": "baseline",
        "athleteLabel": "测试球员",
        "level": "测试",
    }
    fields.update(overrides)
    return AnalysisUploadMetadata(**fields)


def make_job(store: JobStore):
    return store.create_job(AnalysisJobCreate(metadata=make_metadata(), videoId="video-1"))


def test_legacy_json_import_is_idempotent_and_does_not_overwrite_control_plane(tmp_path):
    storage = make_storage(tmp_path)
    store = JobStore(storage)
    job = make_job(store)

    # 旧 JSON 仍可被发现，但不能覆盖已经存在的 SQLite 任务。
    legacy_payload = job.model_copy(
        update={
            "status": "failed",
            "canonicalStatus": "failed",
            "displayStatus": "failed",
            "errorMessage": "stale legacy snapshot",
        }
    )
    storage.write_json_atomic(storage.job_json_path(job.id), legacy_payload.model_dump(mode="json"))

    restarted_store = JobStore(storage)
    restored = restarted_store.get(job.id)
    assert restored is not None
    assert restored.canonicalStatus == "queued"
    assert restored.errorMessage is None

    old_job = AnalysisJobSummary(
        id="legacy-only",
        status="processing",
        canonicalStatus="running",
        displayStatus="processing",
        stage="video-read",
        progress=42,
        createdAt="2026-08-24T00:00:00+00:00",
        updatedAt="2026-08-24T00:00:00+00:00",
        metadata=make_metadata(),
        stages=build_stages("video-read"),
        videoId="video-legacy",
        analysisMode="real",
    )
    storage.write_json_atomic(storage.job_json_path(old_job.id), old_job.model_dump(mode="json"))
    imported = JobStore(storage).get(old_job.id)
    assert imported is not None
    assert imported.canonicalStatus == "running"
    assert imported.workerHeartbeatAt is None


def test_claim_heartbeat_is_lease_conditional_and_cross_process_visible(tmp_path):
    storage = make_storage(tmp_path)
    store_a = JobStore(storage)
    store_b = JobStore(storage)
    job = make_job(store_a)

    claimed = store_a.claim(job.id, "worker-a")
    assert claimed is not None
    assert claimed.workerRunId
    assert claimed.workerPid is not None
    assert claimed.claimedAt == claimed.workerHeartbeatAt

    before = store_b.get(job.id)
    assert before is not None
    assert store_b.heartbeat(job.id, "stale-run", heartbeat_at="2026-08-24T00:00:00+00:00") is False
    assert store_b.heartbeat(job.id, claimed.workerRunId, heartbeat_at="2026-08-24T00:01:00+00:00") is True

    after = store_a.get(job.id)
    assert after is not None
    assert after.workerHeartbeatAt == "2026-08-24T00:01:00+00:00"
    assert after.updatedAt == before.updatedAt
    assert store_a.is_lease_current(job.id, claimed.workerRunId) is True


def test_terminal_update_preserves_scene_reference_from_current_control_plane_row(tmp_path):
    storage = make_storage(tmp_path)
    store = JobStore(storage)
    job = store.create_job(
        AnalysisJobCreate(
            metadata=make_metadata(capture_take_id="take-metric"),
            videoId="video-1",
            calibrationId="calibration-1",
            analysisKind="multiview",
            multiview=MultiViewCreateRequest(
                referenceViewId="cam_1",
                executionMode="joint_tracking_v2",
                sceneCalibrationMode="metric",
                sceneCalibrationRevision=3,
                views=[
                    MultiViewViewPayload(
                        viewId="cam_1",
                        videoId="video-1",
                        calibrationId="calibration-1",
                        courtOrientation="identity",
                    ),
                    MultiViewViewPayload(
                        viewId="cam_2",
                        videoId="video-2",
                        calibrationId="calibration-2",
                        courtOrientation="rotate_180",
                    ),
                ],
            ),
        )
    )
    store.update(job.id, orchestrationStatus="joint_ready")
    claimed = store.claim(job.id, "worker-a")
    assert claimed is not None

    # 模拟 Worker 持有的旧快照缺少场景引用；控制面当前行仍是 metric revision 3。
    stale_snapshot = claimed.model_copy(
        update={
            "sceneCalibrationMode": "approximate",
            "sceneCalibrationRevision": None,
            "sceneCalibrationStatus": "missing",
        }
    )
    completed = store.mark_succeeded(stale_snapshot, stages=stale_snapshot.stages)

    assert completed.sceneCalibrationMode == "metric"
    assert completed.sceneCalibrationRevision == 3
    assert completed.sceneCalibrationStatus == "ready"
    persisted = store.get(job.id)
    assert persisted is not None
    assert persisted.sceneCalibrationMode == "metric"
    assert persisted.sceneCalibrationRevision == 3


def test_concurrent_legacy_json_snapshots_use_independent_temp_files(tmp_path, monkeypatch):
    storage = make_storage(tmp_path)
    target = storage.job_json_path("concurrent-snapshot")

    from app.services import storage_service as storage_module

    barrier = threading.Barrier(2)
    replace_sources: list[Path] = []
    real_replace = storage_module.os.replace

    def synchronized_replace(source: str | bytes | Path, destination: str | bytes | Path) -> None:
        replace_sources.append(Path(source))
        barrier.wait(timeout=2)
        real_replace(source, destination)

    monkeypatch.setattr(storage_module.os, "replace", synchronized_replace)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(storage.write_json_atomic, target, {"writer": writer})
            for writer in (1, 2)
        ]
        for future in futures:
            future.result(timeout=5)

    assert len(replace_sources) == 2
    assert len(set(replace_sources)) == 2
    assert json.loads(target.read_text(encoding="utf-8"))["writer"] in {1, 2}
    assert list(target.parent.glob(f".{target.name}.*.tmp")) == []


def test_heartbeat_survives_legacy_snapshot_write_failure(tmp_path):
    storage = make_storage(tmp_path)
    store = JobStore(storage)
    claimed = store.claim(make_job(store).id, "worker-a")
    assert claimed is not None

    def fail_snapshot(_payload):
        raise OSError("simulated legacy snapshot failure")

    store._persist_payload = fail_snapshot  # type: ignore[method-assign]

    assert store.heartbeat(claimed.id, claimed.workerRunId) is True
    assert store.is_lease_current(claimed.id, claimed.workerRunId) is True
    refreshed = store.control_plane.get(claimed.id)
    assert refreshed is not None
    assert refreshed["workerHeartbeatAt"] is not None


def test_stale_running_is_marked_interrupted_and_terminal_cannot_regress(tmp_path):
    storage = make_storage(tmp_path)
    store = JobStore(storage)
    claimed = store.claim(make_job(store).id, "worker-a")
    assert claimed is not None

    old = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
    stale = store.update(
        claimed.id,
        workerHeartbeatAt=old,
        lastProgressAt=old,
        _expected_canonical_status="running",
        _expected_worker_run_id=claimed.workerRunId,
    )
    assert stale is not None
    assert store.recover_stale_running(timeout_seconds=30) == 1

    interrupted = store.get(claimed.id)
    assert interrupted is not None
    assert interrupted.status == "interrupted"
    assert interrupted.canonicalStatus == "interrupted"
    assert interrupted.interruptionCode == "worker_heartbeat_timeout"
    assert interrupted.interruptedAt is not None
    assert store.heartbeat(claimed.id, claimed.workerRunId) is False
    assert (
        store.update(
            claimed.id,
            canonicalStatus="running",
            status="processing",
            displayStatus="processing",
        )
        is None
    )
    assert store.get(claimed.id).canonicalStatus == "interrupted"


def test_stale_heartbeat_does_not_interrupt_live_external_worker(tmp_path, monkeypatch):
    storage = make_storage(tmp_path)
    store = JobStore(storage)
    claimed = store.claim(make_job(store).id, "analysis-worker-external")
    assert claimed is not None

    old = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
    stale = store.update(
        claimed.id,
        workerPid=987654,
        workerHeartbeatAt=old,
        lastProgressAt=old,
        _expected_canonical_status="running",
        _expected_worker_run_id=claimed.workerRunId,
    )
    assert stale is not None

    monkeypatch.setattr(
        "app.services.job_orchestration._is_local_process_alive",
        lambda pid: pid == 987654,
    )

    assert store.recover_stale_running(timeout_seconds=30) == 0
    retained = store.get(claimed.id)
    assert retained is not None
    assert retained.canonicalStatus == "running"
    assert retained.workerRunId == claimed.workerRunId


def test_worker_heartbeat_runs_without_stage_progress_callbacks(tmp_path):
    storage = make_storage(tmp_path)
    store = JobStore(storage)
    claimed = store.claim(make_job(store).id, "worker-a")
    assert claimed is not None

    calls: list[str] = []
    original_heartbeat = store.heartbeat

    def record_heartbeat(job_id: str, run_id: str, *, heartbeat_at: str | None = None) -> bool:
        calls.append(run_id)
        return original_heartbeat(job_id, run_id, heartbeat_at=heartbeat_at)

    store.heartbeat = record_heartbeat  # type: ignore[method-assign]
    runtime = AnalysisWorkerRuntime(
        store,
        pipeline_factory=lambda: None,
        on_completed=lambda _job, _result: None,
        worker_id="worker-a",
    )
    runtime.settings.analysis_worker_heartbeat_interval_seconds = 0.01
    stop_event = threading.Event()
    failed_event = threading.Event()
    thread = threading.Thread(
        target=runtime._heartbeat_loop,
        args=(claimed, stop_event, failed_event),
        daemon=True,
    )
    thread.start()
    time.sleep(0.05)
    stop_event.set()
    thread.join(timeout=1)

    assert thread.is_alive() is False
    assert failed_event.is_set() is False
    assert len(calls) >= 3
    assert all(run_id == claimed.workerRunId for run_id in calls)


def test_external_mode_does_not_start_embedded_worker(monkeypatch):
    from types import SimpleNamespace

    from app.core.config import get_settings
    from app.services import mock_analysis

    monkeypatch.setenv("PICKLEBALL_ANALYSIS_WORKER_MODE", "external")
    monkeypatch.setenv("PICKLEBALL_ENABLE_JOB_WORKER", "true")
    get_settings.cache_clear()
    started: list[str] = []
    worker = SimpleNamespace(
        start=lambda: started.append("started"),
        stop=lambda **_kwargs: None,
    )
    monkeypatch.setattr(mock_analysis, "_WORKER", worker)
    monkeypatch.setattr(mock_analysis, "_WORKER_STARTED", False)
    monkeypatch.setattr(mock_analysis, "_sync_orchestration_storage", lambda: None)
    monkeypatch.setattr(
        mock_analysis,
        "_get_coordinator",
        lambda: SimpleNamespace(reconcile_all=lambda: 0),
    )

    mock_analysis.start_analysis_worker()
    assert started == []

    mock_analysis.start_analysis_worker(force=True)
    assert started == ["started"]
    get_settings.cache_clear()
