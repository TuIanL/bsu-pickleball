"""阶段内重试留痕与失败证据保真的 Worker 级测试。

对应 change `add-analysis-run-trace-and-error-reporting` 的 tasks 3.7 / 3.8 / 3.9。

回归对象（change 之前的行为）：
- 可重试阶段失败后，阶段 `internalMessage` 为 None、job 级无任何失败类别，失败原因被吞掉；
- 失败重试后取消，job 级 `errorCode` 被 `ANALYSIS_JOB_CANCELED` 覆盖，真实失败码消失。
"""

from __future__ import annotations

import threading

from app.schemas.analysis import AnalysisJobCreate, AnalysisJobSummary, AnalysisStage, AnalysisUploadMetadata
from app.services.analysis_progress import stage_ids
from app.services.analysis_run_trace import read_job_run_trace, read_run_trace
from app.services.job_orchestration import (
    RETRYABLE_STAGE_IDS,
    AnalysisWorkerRuntime,
    JobCanceledError,
    JobStore,
)
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
        fileName="trace.mp4",
        matchTitle="轨迹测试",
        venue="测试场",
        matchDate="2026-10-04",
        matchFormat="singles",
        cameraAngle="baseline",
        athleteLabel="测试球员",
        level="测试",
    )


def advance_to(store: JobStore, job: AnalysisJobSummary, stage_id: str) -> AnalysisJobSummary:
    """按阶段图顺序推进 active 阶段，保持快照自洽。

    直接跳到后面的阶段会被 `merge_stage_event` 判为非法回退并忽略，因此这里
    先把之前的阶段逐个标记 done，再把目标阶段标为 active。
    """
    ids = list(stage_ids("single_view"))
    assert stage_id in ids, f"{stage_id} 不属于 single_view 阶段图"
    current = job
    for earlier in ids[: ids.index(stage_id)]:
        current = store.mark_stage(
            current,
            AnalysisStage(id=earlier, label=earlier, status="done", detail="done", progress=100),
        )
    current = store.mark_stage(
        current,
        AnalysisStage(id=stage_id, label=stage_id, status="active", detail="running", progress=10),
    )
    assert current.stage == stage_id, f"阶段推进失败，仍停在 {current.stage}"
    return current


def _runtime(store: JobStore) -> AnalysisWorkerRuntime:
    return AnalysisWorkerRuntime(
        store,
        pipeline_factory=lambda: None,
        on_completed=lambda *_args: None,
    )


def _install_executor(monkeypatch, behaviour) -> dict:
    """注入一个假执行器；`behaviour(call_index)` 决定第 N 次调用抛什么。"""
    calls = {"n": 0}

    class _Executor:
        def execute(self, job, token, progress_callback):  # noqa: ANN001, ARG002
            calls["n"] += 1
            raise behaviour(calls["n"])

    monkeypatch.setattr(
        "app.services.analysis_executor_dispatch.resolve_executor",
        lambda *args, **kwargs: _Executor(),
    )
    return calls


# ── 3.7 可重试阶段失败必须留下真实原因 ────────────────────────────────────────


def test_retryable_stage_failure_records_real_reason(tmp_path, monkeypatch):
    store = JobStore(make_storage(tmp_path))
    job = store.claim(
        store.create_job(AnalysisJobCreate(metadata=make_metadata(), videoId="video-1")).id,
        "worker-trace",
    )
    assert job is not None
    job = advance_to(store, job, "video-read")
    assert "video-read" in RETRYABLE_STAGE_IDS, "本用例前提：该阶段可重试"

    calls = _install_executor(
        monkeypatch,
        lambda _n: RuntimeError("OpenCV failed to decode stream: moov atom not found"),
    )

    final = _runtime(store)._execute_pipeline(job, threading.Event())

    # 重试一次后仍失败
    assert final.canonicalStatus == "failed"
    assert calls["n"] == 2

    failed_stage = next(stage for stage in final.stages if stage.id == "video-read")
    assert failed_stage.retryCount == 1
    # change 之前：阶段 internalMessage 恒为 None，失败原因被吞掉
    assert failed_stage.internalMessage is not None
    assert "moov atom not found" in failed_stage.internalMessage
    assert failed_stage.failureClass == "input_media"

    assert final.failureEvidence is not None
    assert final.failureEvidence.failureClass == "input_media"
    assert final.failureEvidence.errorCode == "ANALYSIS_STAGE_FAILED"
    assert final.failureEvidence.stage == "video-read"
    assert final.failureEvidence.attempt == final.attempt

    assert len(final.retryHistory) == 1
    entry = final.retryHistory[0]
    assert entry.stage == "video-read"
    assert entry.retryIndex == 1
    assert entry.retryLimit == 1
    assert entry.willRetry is False
    assert entry.exceptionType == "RuntimeError"
    assert entry.failureClass == "input_media"
    assert entry.exceptionDigest
    assert "moov atom not found" not in entry.exceptionDigest  # digest 是指纹，不是原文

    # 轨迹落盘且含完整 retry 事件
    trace_path = store.storage.resolve_run_trace_path(job.id)
    events, availability, reason = read_run_trace(trace_path)
    assert availability == "available", reason
    assert [event["seq"] for event in events] == sorted(event["seq"] for event in events)

    retries = [event for event in events if event["event"] == "retry"]
    assert len(retries) == 1
    retry_event = retries[0]
    assert retry_event["stage"] == "video-read"
    assert retry_event["exception_type"] == "RuntimeError"
    assert "moov atom not found" in retry_event["exception_message"]
    assert retry_event["failure_class"] == "input_media"
    assert retry_event["error_code"] == "ANALYSIS_STAGE_FAILED"
    assert retry_event["retry_index"] == 1
    assert retry_event["retry_limit"] == 1
    assert retry_event["will_retry"] is False
    assert retry_event["traceback_digest"] == entry.exceptionDigest
    assert retry_event["traceback_frames"]

    assert [event["event"] for event in events].count("fail") == 1

    # 轨迹可用性写进任务摘要（收尾的 finally 在返回之后执行，需重新读取）
    persisted = store.get(job.id)
    assert persisted is not None
    assert persisted.runTrace is not None
    assert persisted.runTrace.availability == "available"
    assert persisted.runTrace.eventCount == len(events)
    assert persisted.runTrace.target == f"analysis/{job.id}/run_trace.jsonl"


# ── 3.8 终态不得抹除运行中的失败证据 ─────────────────────────────────────────


def test_cancel_after_retry_keeps_real_failure_evidence(tmp_path, monkeypatch):
    store = JobStore(make_storage(tmp_path))
    job = store.claim(
        store.create_job(AnalysisJobCreate(metadata=make_metadata(), videoId="video-1")).id,
        "worker-trace",
    )
    assert job is not None
    job = advance_to(store, job, "video-read")

    def behaviour(call_index: int) -> BaseException:
        if call_index == 1:
            return RuntimeError("OpenCV failed to decode stream: moov atom not found")
        # 第二次执行时用户已经取消
        return JobCanceledError("Analysis job cancellation requested")

    calls = _install_executor(monkeypatch, behaviour)

    final = _runtime(store)._execute_pipeline(job, threading.Event())

    assert calls["n"] == 2
    assert final.canonicalStatus == "canceled"
    assert final.errorCode == "ANALYSIS_JOB_CANCELED"

    # 关键不变量：取消码不得掩盖真实失败证据
    assert final.failureEvidence is not None
    assert final.failureEvidence.failureClass == "input_media"
    assert final.failureEvidence.errorCode == "ANALYSIS_STAGE_FAILED"
    assert final.failureEvidence.stage == "video-read"
    assert len(final.retryHistory) == 1
    assert final.retryHistory[0].failureClass == "input_media"

    # 取消后的阶段仍保留这次运行的真实原因与重试次数
    canceled_stage = next(stage for stage in final.stages if stage.id == "video-read")
    assert canceled_stage.status == "canceled"
    assert canceled_stage.retryCount == 1
    assert canceled_stage.internalMessage is not None
    assert "moov atom not found" in canceled_stage.internalMessage

    events, availability, _reason = read_run_trace(store.storage.resolve_run_trace_path(job.id))
    assert availability == "available"
    assert [event["event"] for event in events].count("retry") == 1
    assert [event["event"] for event in events].count("canceled") >= 1


# ── 3.9 不可重试阶段不得产生 retry 事件 ──────────────────────────────────────


def test_non_retryable_stage_failure_emits_no_retry(tmp_path, monkeypatch):
    store = JobStore(make_storage(tmp_path))
    job = store.claim(
        store.create_job(AnalysisJobCreate(metadata=make_metadata(), videoId="video-1")).id,
        "worker-trace",
    )
    assert job is not None
    job = advance_to(store, job, "detection")
    assert "detection" not in RETRYABLE_STAGE_IDS

    calls = _install_executor(monkeypatch, lambda _n: RuntimeError("boom"))

    final = _runtime(store)._execute_pipeline(job, threading.Event())

    assert final.canonicalStatus == "failed"
    assert calls["n"] == 1, "不可重试阶段必须一次都不重跑"

    assert final.retryHistory == []

    events, availability, _reason = read_run_trace(store.storage.resolve_run_trace_path(job.id))
    assert availability == "available"
    assert [event["event"] for event in events].count("retry") == 0
    assert [event["event"] for event in events].count("fail") == 1

    failed_stage = next(stage for stage in final.stages if stage.id == "detection")
    assert failed_stage.failureClass == "internal_defect"
    assert final.failureEvidence is not None
    assert final.failureEvidence.failureClass == "internal_defect"


# ── 轨迹目标不可写时不阻塞任务 ───────────────────────────────────────────────


def test_unwritable_trace_target_does_not_break_the_job(tmp_path, monkeypatch):
    """外接盘未挂载时：任务照跑，轨迹不可用必须显式记录，不静默改写位置。"""
    store = JobStore(make_storage(tmp_path))
    job = store.claim(
        store.create_job(AnalysisJobCreate(metadata=make_metadata(), videoId="video-1")).id,
        "worker-trace",
    )
    assert job is not None
    job = advance_to(store, job, "video-read")

    # 让轨迹路径指向一个「父级是普通文件」的位置 → mkdir 必然失败
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    monkeypatch.setattr(
        store.storage,
        "resolve_run_trace_path",
        lambda _job_id, _capture_take_id=None: blocker / "run_trace.jsonl",
    )

    _install_executor(monkeypatch, lambda _n: RuntimeError("boom"))
    final = _runtime(store)._execute_pipeline(job, threading.Event())

    assert final.canonicalStatus == "failed"
    # 失败证据仍然完整：轨迹不可用不等于失败原因不可用
    assert final.failureEvidence is not None
    assert final.failureEvidence.failureClass == "internal_defect"

    persisted = store.get(job.id)
    assert persisted is not None
    assert persisted.runTrace is not None
    assert persisted.runTrace.availability == "unavailable"
    assert persisted.runTrace.reason == "trace_sink_unwritable"
    assert persisted.runTrace.target == f"analysis/{job.id}/run_trace.jsonl"
    assert not (blocker / "run_trace.jsonl").exists()
    assert not (tmp_path / "outputs" / job.id / "run_trace.jsonl").exists()


def test_legacy_job_without_trace_gets_explicit_reason(tmp_path):
    """历史任务（无轨迹）必须给出明确原因，而不是静默空结果。"""
    store = JobStore(make_storage(tmp_path))
    job = store.create_job(AnalysisJobCreate(metadata=make_metadata(), videoId="video-1"))

    result = read_job_run_trace(store.storage.resolve_run_trace_path(job.id), legacy_job=True)
    assert result["events"] == []
    assert result["availability"] == "unavailable"
    assert result["reason"] == "legacy_job_without_trace"


# ── 落盘位置：外接存储离线时写入独立降级目录 ────────────────────────────────


def test_run_trace_target_uses_separate_degraded_path_when_drive_is_offline(tmp_path, monkeypatch):
    """外接盘离线时轨迹显式落入独立降级目录，不与本地正式任务混写。"""
    storage = make_storage(tmp_path)
    external_session = tmp_path / "fake-external" / "take_sync_offline"
    monkeypatch.setattr(
        StorageService,
        "_read_capture_session_dir",
        classmethod(lambda _cls, _take_id: external_session),
    )

    path = storage.resolve_run_trace_path("job-external-offline", "ct_external_offline")

    assert path == storage.outputs_dir / "_degraded" / "job-external-offline" / "run_trace.jsonl"
    assert storage.capture_job_degradation_reason("job-external-offline") == "capture_storage_unavailable"


def test_run_trace_target_falls_back_locally_without_capture_take(tmp_path):
    """非采集任务（没有 CaptureTake）才落到本地产物目录。"""
    storage = make_storage(tmp_path)

    path = storage.resolve_run_trace_path("job-local-only")

    assert path == storage.outputs_dir / "job-local-only" / "run_trace.jsonl"


def test_real_pipeline_lease_loss_preserves_classification_and_worker_continuity(tmp_path, monkeypatch):
    """Persisted job -> real dispatcher/pipeline -> revoked lease -> next queued job.

    Models are not involved: revoke at the first tracking callback, inside the
    exact pipeline try/except that used to turn control signals into failures.
    """
    from types import SimpleNamespace

    from app.services.analysis_pipeline import AnalysisPipeline

    store = JobStore(make_storage(tmp_path))
    first = store.create_job(AnalysisJobCreate(metadata=make_metadata(), videoId="video-lease", calibrationId="cal-lease"))
    second = store.create_job(AnalysisJobCreate(metadata=make_metadata(), videoId="video-next", calibrationId="cal-next"))
    handled_second = threading.Event()
    callbacks = []

    class LeaseProbePipeline(AnalysisPipeline):
        def __init__(self, **_kwargs):
            self.settings = SimpleNamespace(player_analysis_hard_limit=4)
            self.video_service = SimpleNamespace(get_video=lambda _id: SimpleNamespace(id=_id))
            self.calibration_service = SimpleNamespace(get_calibration=lambda _id: SimpleNamespace(id=_id))

        def _notify_progress(self, callback, stage):
            callbacks.append(stage.id)
            if stage.id == "frame-sampling":
                current = store.get(first.id)
                store.mark_interrupted(current, reason="worker_heartbeat_timeout")
            return super()._notify_progress(callback, stage)

        def run(self, **kwargs):
            if kwargs["job_id"] == second.id:
                # Stop the second job cooperatively after proving it was claimed.
                handled_second.set()
                raise JobCanceledError("acceptance probe complete")
            return super().run(**kwargs)

    runtime = AnalysisWorkerRuntime(store, pipeline_factory=LeaseProbePipeline, on_completed=lambda *_: None)
    runtime.start()
    try:
        assert handled_second.wait(timeout=5), "worker did not execute the second queued job"
    finally:
        runtime.stop()

    first_final = store.get(first.id)
    assert "frame-sampling" in callbacks
    assert first_final.canonicalStatus == "interrupted"
    assert first_final.failureEvidence.failureClass == "worker_lease"
    assert first_final.retryHistory == []
    assert store.get(second.id).canonicalStatus == "canceled"
    events, availability, _ = read_run_trace(store.storage.resolve_run_trace_path(first.id))
    assert availability == "available"
    lease_events = [event for event in events if event["event"] == "lease_lost"]
    assert len(lease_events) == 1
    assert lease_events[0]["failure_class"] == "worker_lease"
    assert not any(event.get("failure_class") == "internal_defect" for event in events)
