"""分析运行轨迹与失败归因的单测。

对应 change `add-analysis-run-trace-and-error-reporting` 的 tasks 1.4 / 2.3 / 2.4。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.analysis_failure_taxonomy import (
    DEFAULT_FAILURE_CLASS,
    FAILURE_CLASSES,
    classify_failure,
)
from app.services.analysis_run_trace import (
    TRACE_SCHEMA_VERSION,
    RunTraceSink,
    exception_digest,
    describe_exception,
    exception_summary,
    read_job_logs,
    read_job_run_trace,
    read_run_trace,
)


def _sink(path: Path, **overrides) -> RunTraceSink:
    kwargs = {
        "job_id": "job-test0001",
        "attempt": 1,
        "worker_id": "worker-1",
        "worker_run_id": "worker-1-run-1",
    }
    kwargs.update(overrides)
    return RunTraceSink(path, **kwargs)


# ── 1.2 / 1.4 轨迹 sink ──────────────────────────────────────────────────────


def test_sink_appends_in_order_with_monotonic_seq(tmp_path: Path) -> None:
    trace = tmp_path / "run_trace.jsonl"
    sink = _sink(trace)

    sink.record("start", "multiview-joint")
    sink.record("end", "multiview-joint")
    sink.record("retry", "multiview-ball-analysis", retry_index=1)

    events, availability, reason = read_run_trace(trace)

    assert availability == "available"
    assert reason is None
    assert [event["seq"] for event in events] == [1, 2, 3]
    assert [event["event"] for event in events] == ["start", "end", "retry"]
    assert all(event["schema_version"] == TRACE_SCHEMA_VERSION for event in events)
    assert all(event["job_id"] == "job-test0001" for event in events)
    assert events[2]["retry_index"] == 1
    assert sink.sink_unavailable is None


def test_truncated_prefix_keeps_complete_lines_readable(tmp_path: Path) -> None:
    """进程被杀时，已写入的完整行必须仍可解析。"""
    trace = tmp_path / "run_trace.jsonl"
    sink = _sink(trace)
    for index in range(4):
        sink.record("start", f"stage-{index}")

    raw = trace.read_text(encoding="utf-8")
    trace.write_text(raw[: len(raw) - 7], encoding="utf-8")

    events, availability, reason = read_run_trace(trace)

    assert [event["seq"] for event in events] == [1, 2, 3]
    assert availability == "partial"
    assert reason == "malformed_trace_lines_skipped"


def test_each_line_is_independently_parseable_json(tmp_path: Path) -> None:
    trace = tmp_path / "run_trace.jsonl"
    sink = _sink(trace)
    sink.record("start", "multiview-joint", detail="中文 detail")
    sink.record("fail", "multiview-joint", exception_type="cv2.error")

    for line in trace.read_text(encoding="utf-8").splitlines():
        assert isinstance(json.loads(line), dict)


def test_unwritable_target_degrades_without_raising(tmp_path: Path) -> None:
    """目标不可写时不得静默改写位置，也不得把异常抛给主流程。"""
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("i am a file", encoding="utf-8")
    trace = blocker / "run_trace.jsonl"

    sink = _sink(trace)
    assert sink.record("start", "multiview-joint") is None

    unavailable = sink.sink_unavailable
    assert unavailable is not None
    assert unavailable["availability"] == "unavailable"
    assert unavailable["reason"] == "trace_sink_unwritable"
    assert unavailable["target"] == str(trace)
    assert not trace.exists()


def test_unknown_event_is_rejected(tmp_path: Path) -> None:
    sink = _sink(tmp_path / "run_trace.jsonl")
    with pytest.raises(ValueError):
        sink.record("not-a-real-event", "stage")


# ── 1.4 读取状态 ─────────────────────────────────────────────────────────────


def test_read_missing_trace_reports_reason(tmp_path: Path) -> None:
    events, availability, reason = read_run_trace(tmp_path / "nope.jsonl")
    assert events == []
    assert availability == "unavailable"
    assert reason == "run_trace_missing"


def test_legacy_job_reason_is_explicit(tmp_path: Path) -> None:
    result = read_job_run_trace(tmp_path / "nope.jsonl", legacy_job=True)
    assert result["availability"] == "unavailable"
    assert result["reason"] == "legacy_job_without_trace"

    # 非历史任务不得伪装成 legacy
    assert read_job_run_trace(tmp_path / "nope.jsonl")["reason"] == "run_trace_missing"


# ── 2.3 失败归因 ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"exception_type": "WorkerLeaseLostError"}, "worker_lease"),
        ({"error_code": "ANALYSIS_WORKER_HEARTBEAT_TIMEOUT"}, "worker_lease"),
        ({"exception_type": "StageTimeoutError"}, "resource_timeout"),
        ({"error_code": "ANALYSIS_STAGE_TIMEOUT"}, "resource_timeout"),
        ({"exception_type": "MemoryError"}, "resource_timeout"),
        ({"exception_type": "FileNotFoundError", "message": "/x/a.mp4"}, "input_media"),
        ({"error_code": "ANALYSIS_VIDEO_NOT_FOUND"}, "input_media"),
        ({"exception_type": "cv2.error", "message": "OpenCV failed to decode stream"}, "input_media"),
        ({"message": "homography for court projection is missing"}, "calibration"),
        ({"message": "标定点位不足"}, "calibration"),
        ({"exception_type": "ModuleNotFoundError", "message": "No module named 'mmpose'"}, "model_environment"),
        ({"message": "rtmpose checkpoint not found"}, "model_environment"),
        ({"message": "Parent job has no frozen multiview view contract"}, "orchestration"),
        ({"message": "segmentation window plan mapping failed"}, "orchestration"),
        ({"exception_type": "KeyError", "message": "unexpected"}, DEFAULT_FAILURE_CLASS),
        ({}, DEFAULT_FAILURE_CLASS),
    ],
)
def test_classify_failure_covers_every_class(kwargs: dict, expected: str) -> None:
    assert classify_failure(**kwargs) == expected
    assert expected in FAILURE_CLASSES


def test_classify_failure_never_drops_original_detail() -> None:
    """归因只是分类，原始异常信息必须仍然可读。"""
    exc = KeyError("missing key 'player_id'")
    described = describe_exception(exc)

    assert classify_failure(
        exception_type=described["exception_type"], message=described["exception_message"]
    ) == DEFAULT_FAILURE_CLASS
    assert described["exception_type"] == "KeyError"
    assert "player_id" in described["exception_message"]


# ── 2.4 digest 稳定性 ────────────────────────────────────────────────────────


def test_digest_is_stable_across_numeric_variation() -> None:
    """同一根因在两次运行里帧号/耗时不同，digest 仍须一致。"""
    frames = ["job_orchestration.py:1265", "analysis_pipeline.py:1102"]

    first = exception_digest("RuntimeError", "stage failed after 87 frames", frames)
    second = exception_digest("RuntimeError", "stage failed after 132 frames", frames)

    assert first == second


def test_digest_differs_for_different_root_cause() -> None:
    frames = ["a.py:1"]
    assert exception_digest("RuntimeError", "boom", frames) != exception_digest("ValueError", "boom", frames)
    assert exception_digest("RuntimeError", "boom", frames) != exception_digest(
        "RuntimeError", "boom", ["b.py:2"]
    )


def test_describe_exception_shape_and_summary() -> None:
    try:
        raise RuntimeError("multiview ball analysis exploded")
    except RuntimeError as exc:
        described = describe_exception(exc)
        summary = exception_summary(exc)

    assert described["exception_type"] == "RuntimeError"
    assert described["traceback_digest"]
    assert len(described["traceback_digest"]) == 16
    assert isinstance(described["traceback_frames"], list)
    assert all(":" in frame for frame in described["traceback_frames"])
    assert summary.startswith("RuntimeError: ")
    assert "exploded" in summary


def test_long_exception_message_is_truncated() -> None:
    try:
        raise RuntimeError("x" * 5000)
    except RuntimeError as exc:
        described = describe_exception(exc)

    assert described["exception_message"].endswith("…(truncated)")
    assert len(described["exception_message"]) < 5000


# ── 4.2 日志读取 ─────────────────────────────────────────────────────────────


def test_read_job_logs_filters_by_job_and_window(tmp_path: Path) -> None:
    worker_log = tmp_path / "analysis-worker.log"
    worker_log.write_text(
        "\n".join(
            [
                "2026-10-04 10:00:00,000 INFO [__main__] analysis-worker started",
                "2026-10-04 10:28:05,000 WARNING something for job-dc737801f5 happened",
                "2026-10-04 12:00:00,000 WARNING late line for job-dc737801f5",
                "2026-10-04 10:28:06,000 WARNING unrelated job-other0001 line",
            ]
        ),
        encoding="utf-8",
    )
    backend_log = tmp_path / "backend.log"
    backend_log.write_text(
        'INFO:     127.0.0.1:53332 - "GET /api/analysis/jobs/job-dc737801f5 HTTP/1.1" 200 OK\n',
        encoding="utf-8",
    )

    result = read_job_logs(
        log_paths=[worker_log, backend_log],
        job_id="job-dc737801f5",
        window_start="2026-10-04T10:28:04Z",
        window_end="2026-10-04T11:12:03Z",
        max_lines=50,
    )

    assert result["availability"] == "available"
    assert len(result["lines"]) == 2
    joined = "\n".join(result["lines"])
    assert "10:28:05" in joined
    assert "GET /api/analysis/jobs/job-dc737801f5" in joined
    # 窗口外（12:00）与无关任务的行都不得出现
    assert "12:00:00" not in joined
    assert "job-other0001" not in joined


def test_read_job_logs_reports_partial_when_nothing_matches(tmp_path: Path) -> None:
    path = tmp_path / "backend.log"
    path.write_text("INFO: unrelated line\n", encoding="utf-8")

    result = read_job_logs(log_paths=[path], job_id="job-missing")

    assert result["lines"] == []
    assert result["availability"] == "partial"
    assert result["reason"] == "no_matching_log_lines"


def test_read_job_logs_redacts_host_paths_and_returns_only_file_names(tmp_path: Path) -> None:
    path = tmp_path / "backend.log"
    path.write_text(
        "ERROR job-path0001 Could not read /Users/alice/Private Match/video.mp4\n",
        encoding="utf-8",
    )

    result = read_job_logs(log_paths=[path], job_id="job-path0001")

    assert result["scanned_files"] == ["backend.log"]
    assert len(result["lines"]) == 1
    assert "/Users/" not in result["lines"][0]
    assert "<path>" in result["lines"][0]


def test_read_job_logs_enforces_line_limit(tmp_path: Path) -> None:
    path = tmp_path / "backend.log"
    path.write_text(
        "\n".join(f"line {index} for job-limit0001" for index in range(50)) + "\n",
        encoding="utf-8",
    )

    result = read_job_logs(log_paths=[path], job_id="job-limit0001", max_lines=5)

    assert len(result["lines"]) == 5
    assert result["truncated"] is True
    assert result["availability"] == "partial"
    assert result["reason"] == "tail_truncated"
    assert "line 49" in result["lines"][-1]
