"""轨迹读取与运行日志读取接口的测试。

对应 change `add-analysis-run-trace-and-error-reporting` 的 task 4.4。
"""

from __future__ import annotations

import threading

from fastapi.testclient import TestClient

import app.api.routes_analysis as routes
from app.main import app
from app.schemas.analysis import AnalysisJobCreate, AnalysisUploadMetadata
from app.services.job_orchestration import AnalysisWorkerRuntime, JobStore
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


def make_metadata() -> AnalysisUploadMetadata:
    return AnalysisUploadMetadata(
        fileName="trace-api.mp4",
        matchTitle="轨迹接口测试",
        venue="测试场",
        matchDate="2026-10-04",
        matchFormat="singles",
        cameraAngle="baseline",
        athleteLabel="测试球员",
        level="测试",
    )


def _install_failing_executor(monkeypatch, message: str = "OpenCV failed to decode stream: moov atom not found") -> None:
    class _Executor:
        def execute(self, job, token, progress_callback):  # noqa: ANN001, ARG002
            raise RuntimeError(message)

    monkeypatch.setattr(
        "app.services.analysis_executor_dispatch.resolve_executor",
        lambda *args, **kwargs: _Executor(),
    )


def _run_failing_job(tmp_path, monkeypatch, message: str | None = None) -> tuple[JobStore, str]:
    """跑一个真实会失败的 single_view 任务，返回 store 与 job_id。"""
    store = JobStore(make_storage(tmp_path))
    job = store.create_job(AnalysisJobCreate(metadata=make_metadata(), videoId="video-1"))
    claimed = store.claim(job.id, "worker-api")
    assert claimed is not None
    _install_failing_executor(monkeypatch, message or "OpenCV failed to decode stream: moov atom not found")
    runtime = AnalysisWorkerRuntime(store, pipeline_factory=lambda: None, on_completed=lambda *_a: None)
    runtime._execute_pipeline(claimed, threading.Event())
    assert store.get(job.id).canonicalStatus == "failed"
    return store, job.id


def test_run_trace_endpoint_returns_events_and_availability(tmp_path, monkeypatch):
    store, job_id = _run_failing_job(tmp_path, monkeypatch)
    monkeypatch.setattr(routes, "_STORAGE", store.storage)
    monkeypatch.setattr(routes, "get_mock_job", lambda _job_id: store.get(job_id))

    response = TestClient(app).get(f"/api/analysis/jobs/{job_id}/run-trace")

    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == job_id
    assert body["availability"] == "available"
    assert body["reason"] is None
    assert body["target"] == f"analysis/{job_id}/run_trace.jsonl"
    assert not body["target"].startswith("/")
    assert body["event_count"] == len(body["events"]) > 0
    events = body["events"]
    retries = [event for event in events if event["event"] == "retry"]
    assert len(retries) == 1
    assert retries[0]["exception_type"] == "RuntimeError"
    assert retries[0]["failure_class"] == "input_media"
    # 事件按 seq 有序
    assert [event["seq"] for event in events] == sorted(event["seq"] for event in events)


def test_run_trace_endpoint_marks_legacy_jobs_explicitly(tmp_path, monkeypatch):
    store = JobStore(make_storage(tmp_path))
    job = store.create_job(AnalysisJobCreate(metadata=make_metadata(), videoId="video-1"))
    monkeypatch.setattr(routes, "_STORAGE", store.storage)
    monkeypatch.setattr(routes, "get_mock_job", lambda _job_id: store.get(job.id))

    response = TestClient(app).get(f"/api/analysis/jobs/{job.id}/run-trace")

    assert response.status_code == 200
    body = response.json()
    assert body["events"] == []
    assert body["availability"] == "unavailable"
    assert body["reason"] == "legacy_job_without_trace"


def test_run_trace_endpoint_returns_404_for_unknown_job(monkeypatch):
    monkeypatch.setattr(routes, "get_mock_job", lambda _job_id: None)

    response = TestClient(app).get("/api/analysis/jobs/job-does-not-exist/run-trace")

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_job_summary_never_inlines_trace_events(tmp_path, monkeypatch):
    """任务摘要只带轨迹可用性摘要，绝不内联事件序列（轮询体积必须稳定）。"""
    store, job_id = _run_failing_job(tmp_path, monkeypatch)
    monkeypatch.setattr(routes, "_STORAGE", store.storage)
    monkeypatch.setattr(routes, "get_mock_job", lambda _job_id: store.get(job_id))

    body = TestClient(app).get(f"/api/analysis/jobs/{job_id}").json()

    assert "events" not in body
    assert body["runTrace"]["availability"] == "available"
    assert body["runTrace"]["eventCount"] > 0
    assert len(body["retryHistory"]) == 1
    assert body["failureEvidence"]["failureClass"] == "input_media"


def test_job_and_trace_api_redact_host_paths_but_store_internal_cause(tmp_path, monkeypatch):
    source_path = "/Users/tuian/recordings/private match.mp4"
    store, job_id = _run_failing_job(tmp_path, monkeypatch, f"Could not read uploaded video: {source_path}")
    job = store.get(job_id)
    assert job is not None
    assert job.publicErrorMessage == "分析任务执行失败，请检查输入视频和模型配置。"
    assert source_path in (job.internalErrorMessage or "")

    monkeypatch.setattr(routes, "_STORAGE", store.storage)
    monkeypatch.setattr(routes, "get_mock_job", lambda _job_id: store.get(job_id))
    monkeypatch.setattr(routes, "list_analysis_jobs", lambda **_kwargs: [store.get(job_id)])
    client = TestClient(app)
    summary_response = client.get(f"/api/analysis/jobs/{job_id}")
    list_response = client.get("/api/analysis/jobs?include_internal=true")
    trace_response = client.get(f"/api/analysis/jobs/{job_id}/run-trace")

    assert summary_response.status_code == list_response.status_code == trace_response.status_code == 200
    summary_body = summary_response.json()
    assert source_path not in str(summary_body)
    assert "<path>" in summary_body["internalErrorMessage"]
    assert source_path not in str(list_response.json())
    trace_body = trace_response.json()
    assert trace_body["target"] == f"analysis/{job_id}/run_trace.jsonl"
    assert source_path not in str(trace_body)
    assert "<path>" in str(trace_body)


def test_logs_endpoint_is_bounded_and_reports_partial(tmp_path, monkeypatch):
    store, job_id = _run_failing_job(tmp_path, monkeypatch)
    job = store.get(job_id)
    assert job.workerRunId

    runtime_dir = tmp_path / "runtime"
    log_dir = runtime_dir / "logs"
    log_dir.mkdir(parents=True)
    # 日志行只有秒级时间戳；这里用任务自己的领取时间来构造窗口内的行。
    assert job.claimedAt
    stamp = job.claimedAt[:19].replace("T", " ")
    (log_dir / "analysis-worker.log").write_text(
        "\n".join(
            [
                f"2020-01-01 00:00:00,000 WARNING outside window for {job_id}",
                f"{stamp},000 WARNING first retry for {job_id}",
                f"{stamp},000 WARNING second retry for {job.workerRunId}",
                f"{stamp},000 WARNING third retry for {job_id}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (log_dir / "backend.log").write_text(
        f'INFO:     127.0.0.1:1 - "GET /api/analysis/jobs/{job_id} HTTP/1.1" 200 OK\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(routes, "_STORAGE", store.storage)
    monkeypatch.setattr(routes, "get_mock_job", lambda _job_id: store.get(job_id))
    monkeypatch.setenv("PICKLEBALL_RUNTIME_DIR", str(runtime_dir))
    monkeypatch.setenv("PICKLEBALL_ANALYSIS_JOB_LOGS_ENABLED", "1")

    response = TestClient(app).get(f"/api/analysis/jobs/{job_id}/logs?tail=2")

    assert response.status_code == 200
    body = response.json()
    assert len(body["lines"]) == 2, body["lines"]
    assert body["truncated"] is True
    assert body["availability"] == "partial"
    assert body["reason"] == "tail_truncated"
    joined = "\n".join(body["lines"])
    assert job_id in joined
    assert "2020-01-01" not in joined  # 窗口外的行不得混入
    assert "backend.log" in body["scanned_files"]


def test_logs_endpoint_reports_partial_when_nothing_matches(tmp_path, monkeypatch):
    store = JobStore(make_storage(tmp_path))
    job = store.create_job(AnalysisJobCreate(metadata=make_metadata(), videoId="video-1"))

    runtime_dir = tmp_path / "runtime"
    log_dir = runtime_dir / "logs"
    log_dir.mkdir(parents=True)
    (log_dir / "backend.log").write_text("INFO: unrelated\n", encoding="utf-8")

    monkeypatch.setattr(routes, "_STORAGE", store.storage)
    monkeypatch.setattr(routes, "get_mock_job", lambda _job_id: store.get(job.id))
    monkeypatch.setenv("PICKLEBALL_RUNTIME_DIR", str(runtime_dir))
    monkeypatch.setenv("PICKLEBALL_ANALYSIS_JOB_LOGS_ENABLED", "1")

    body = TestClient(app).get(f"/api/analysis/jobs/{job.id}/logs").json()

    assert body["lines"] == []
    assert body["availability"] == "partial"
    assert body["reason"] == "no_matching_log_lines"


def test_logs_endpoint_can_be_disabled(tmp_path, monkeypatch):
    store = JobStore(make_storage(tmp_path))
    job = store.create_job(AnalysisJobCreate(metadata=make_metadata(), videoId="video-1"))
    monkeypatch.setattr(routes, "get_mock_job", lambda _job_id: store.get(job.id))
    monkeypatch.delenv("PICKLEBALL_ANALYSIS_JOB_LOGS_ENABLED", raising=False)

    response = TestClient(app).get(f"/api/analysis/jobs/{job.id}/logs")

    assert response.status_code == 403
    assert response.json()["code"] == "job_logs_disabled"
