"""分析运行轨迹（`analysis-run-trace.v1`）—— 每一次执行尝试的结构化事件留痕。

问题背景：阶段内重试（`job_orchestration._execute_pipeline` 的重试分支）过去会
直接吞掉异常再重跑整条执行体，既不留日志也不留字段，导致「任务反复跑」但
「为什么失败」在落盘数据上不可回答。

本模块只做两件事：
1. 把一次运行中的事件（起止 / 重试 / 失败 / 失联 / 取消）按 JSONL append-only 落盘；
2. 把日志文件按 job 维度读回来。

设计约束（见 openspec change `add-analysis-run-trace-and-error-reporting`）：
- 纯逻辑模块，不 import `cv2` / `ultralytics`，可独立单测；
- 写入必须 append + flush，进程被杀后已写入的行仍可解析；
- 目标不可写时**不静默改写**到别处，而是产出 `trace_sink_unavailable` 事件，
  由调用方把它记进任务摘要（控制面总是可写的）。
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

from app.utils.exception_policy import swallow

logger = logging.getLogger(__name__)

TRACE_SCHEMA_VERSION = "analysis-run-trace.v1"
TRACE_FILE_NAME = "run_trace.jsonl"

# 事件枚举：轨迹里只允许出现这些取值。
TRACE_EVENTS: tuple[str, ...] = (
    "start",
    "end",
    "retry",
    "fail",
    "lease_lost",
    "canceled",
    "trace_sink_unavailable",
)

EXCEPTION_MESSAGE_LIMIT = 2048
TRACEBACK_FRAME_LIMIT = 5

_DIGITS = re.compile(r"\d+")
_HOST_PATH_PATTERNS = (
    re.compile(
        r"(?<![A-Za-z0-9_])/(?:Users|Volumes|private|tmp|home|mnt|media|opt|srv|root|var|System|Library|Applications|workspace|workspaces|data|app)/[^\r\n\"'<>]*"
    ),
    re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:\\[^\r\n\"'<>]*"),
)


def redact_host_paths(value: str) -> str:
    """Replace host filesystem paths before returning diagnostics through the API."""
    text = str(value)
    for pattern in _HOST_PATH_PATTERNS:
        text = pattern.sub("<path>", text)
    return text


def redact_public_strings(value: Any) -> Any:
    """Recursively redact path-bearing strings in a public JSON payload."""
    if isinstance(value, str):
        return redact_host_paths(value)
    if isinstance(value, list):
        return [redact_public_strings(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_public_strings(item) for key, item in value.items()}
    return value


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def normalize_exception_message(message: str | None, *, limit: int = EXCEPTION_MESSAGE_LIMIT) -> str:
    """把异常消息截断到可长期留存的长度。"""
    text = "" if message is None else str(message)
    if len(text) <= limit:
        return text
    return text[:limit] + "…(truncated)"


def traceback_frames(exc: BaseException, *, limit: int = TRACEBACK_FRAME_LIMIT) -> list[str]:
    """取异常堆栈的末 N 帧，形如 `job_orchestration.py:1265`。

    完整堆栈已有 `internalErrorMessage` 通道承载；轨迹里只留定位所需的最小信息。
    """
    try:
        frames = traceback.extract_tb(exc.__traceback__)
    except Exception:  # noqa: BLE001 - 诊断代码自身绝不抛出
        return []
    tail = frames[-limit:] if limit > 0 else []
    return [f"{Path(frame.filename).name}:{frame.lineno}" for frame in tail]


def exception_digest(exception_type: str | None, message: str | None, frames: Sequence[str]) -> str:
    """同一根因的异常在多次出现时应得到同一个 digest。

    消息里的数字（帧号、耗时、数量）在两次运行中通常不同，会让同一个根因产生
    不同指纹，因此先做数字掩码再哈希。
    """
    masked = _DIGITS.sub("#", normalize_exception_message(message, limit=512))
    material = "|".join([exception_type or "", masked, ",".join(frames)])
    return hashlib.sha256(material.encode("utf-8", errors="replace")).hexdigest()[:16]


def describe_exception(exc: BaseException) -> dict[str, Any]:
    """把异常压成可直接写进轨迹的字段集。"""
    frames = traceback_frames(exc)
    exception_type = type(exc).__name__
    message = normalize_exception_message(str(exc))
    return {
        "exception_type": exception_type,
        "exception_message": message,
        "traceback_digest": exception_digest(exception_type, str(exc), frames),
        "traceback_frames": frames,
    }


@swallow(
    why="A malformed JSONL row is isolated so later valid trace events remain readable.",
    default=None,
)
def _parse_trace_event(line: str) -> dict[str, Any] | None:
    parsed = json.loads(line)
    return parsed if isinstance(parsed, dict) else None


def exception_summary(exc: BaseException, *, limit: int = 512) -> str:
    """给阶段 `internalMessage` 用的一行摘要（不读轨迹也能看到原因）。"""
    return f"{type(exc).__name__}: {normalize_exception_message(str(exc), limit=limit)}"


class RunTraceSink:
    """把事件按 JSONL 追加到指定文件；失败时降级而不抛给主流程。"""

    def __init__(
        self,
        path: Path,
        *,
        job_id: str,
        attempt: int,
        worker_id: str | None = None,
        worker_run_id: str | None = None,
    ) -> None:
        self.path = Path(path)
        self.job_id = job_id
        self.attempt = attempt
        self.worker_id = worker_id
        self.worker_run_id = worker_run_id
        self._lock = threading.Lock()
        self._seq = 0
        self._unavailable: dict[str, Any] | None = None

    @property
    def seq(self) -> int:
        return self._seq

    @property
    def sink_unavailable(self) -> dict[str, Any] | None:
        """目标不可写时的 `{availability, reason, target}`；可写时为 None。"""
        return self._unavailable

    def record(self, event: str, stage: str | None = None, **fields: Any) -> dict[str, Any] | None:
        """写一条事件；成功返回事件本身，失败返回 None 并记录不可用原因。"""
        if event not in TRACE_EVENTS:
            raise ValueError(f"unknown run trace event: {event}")
        with self._lock:
            self._seq += 1
            payload: dict[str, Any] = {
                "schema_version": TRACE_SCHEMA_VERSION,
                "seq": self._seq,
                "ts": utc_now(),
                "job_id": self.job_id,
                "attempt": self.attempt,
                "worker_id": self.worker_id,
                "worker_run_id": self.worker_run_id,
                "stage": stage,
                "event": event,
            }
            payload.update({key: value for key, value in fields.items() if value is not None})
            if self._append_line(payload):
                return payload
            return None

    def _append_line(self, payload: dict[str, Any]) -> bool:
        line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
                handle.flush()
            return True
        except OSError as exc:
            reason = f"{type(exc).__name__}: {exc}"
            if self._unavailable is None:
                self._unavailable = {
                    "availability": "unavailable",
                    "reason": "trace_sink_unwritable",
                    "target": str(self.path),
                    "detail": normalize_exception_message(reason, limit=512),
                }
                logger.warning(
                    "Run trace target is not writable for job %s; recording trace_sink_unavailable: %s",
                    self.job_id,
                    reason,
                )
            return False


def read_run_trace(path: Path) -> tuple[list[dict[str, Any]], str, str | None]:
    """读回轨迹。

    返回 `(events, availability, reason)`：
    - `available`：全部行都可解析；
    - `partial`：存在不可解析的行，已跳过并给出原因；
    - `unavailable`：文件不存在或完全不可读。
    """
    path = Path(path)
    if not path.exists():
        return [], "unavailable", "run_trace_missing"
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return [], "unavailable", "run_trace_unreadable"

    events: list[dict[str, Any]] = []
    malformed = 0
    for line in raw.splitlines():
        text = line.strip()
        if not text:
            continue
        parsed = _parse_trace_event(text)
        if parsed is None:
            malformed += 1
            continue
        events.append(parsed)

    if not events:
        if malformed:
            return [], "unavailable", "run_trace_unreadable"
        return [], "unavailable", "run_trace_empty"
    events.sort(key=lambda item: int(item.get("seq") or 0))
    if malformed:
        return events, "partial", "malformed_trace_lines_skipped"
    return events, "available", None


def read_job_run_trace(path: Path, *, legacy_job: bool = False) -> dict[str, Any]:
    """读取某个 job 的轨迹，并把「上线前的历史任务」翻译成明确原因。"""
    events, availability, reason = read_run_trace(path)
    if availability == "unavailable" and reason == "run_trace_missing" and legacy_job:
        reason = "legacy_job_without_trace"
    return {"events": events, "availability": availability, "reason": reason}


_TIMESTAMP_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})")


def _line_timestamp(line: str) -> datetime | None:
    match = _TIMESTAMP_PREFIX.match(line.strip())
    if match is None:
        return None
    try:
        return datetime.fromisoformat(match.group(1).replace(" ", "T")).replace(tzinfo=UTC)
    except ValueError:
        return None


def read_job_logs(
    *,
    log_paths: Iterable[Path],
    job_id: str,
    worker_run_id: str | None = None,
    window_start: str | None = None,
    window_end: str | None = None,
    max_lines: int = 200,
) -> dict[str, Any]:
    """按 job 维度读取运行日志。

    uvicorn 的访问日志行没有时间戳，Worker 日志行有；因此匹配以
    `job_id` / `worker_run_id` 子串为主，时间窗口只用于**能解析出时间戳**的行。
    """
    limit = max(1, int(max_lines))
    needles = [needle for needle in (job_id, worker_run_id) if needle]
    # 日志行的时间戳只有秒级精度，窗口边界必须按同一精度比较，否则同一次运行里
    # 亚秒级的 claimedAt 会把「本该落在窗口内」的第一秒整秒行排除掉。
    start = _parse_iso(window_start)
    if start is not None:
        start = start.replace(microsecond=0)
    end = _parse_iso(window_end)
    if end is not None:
        end = end.replace(microsecond=0)
    scanned: list[str] = []
    matched: list[str] = []

    for path in log_paths:
        candidate = Path(path)
        scanned.append(candidate.name)
        if not candidate.exists():
            continue
        try:
            text = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            if not any(needle in line for needle in needles):
                continue
            stamp = _line_timestamp(line)
            if stamp is not None:
                if start is not None and stamp < start:
                    continue
                if end is not None and stamp > end:
                    continue
            matched.append(redact_host_paths(f"[{candidate.name}] {line}"))

    truncated = len(matched) > limit
    if truncated:
        matched = matched[-limit:]

    if not matched:
        return {
            "lines": [],
            "availability": "partial",
            "reason": "no_matching_log_lines",
            "scanned_files": scanned,
            "truncated": False,
        }
    return {
        "lines": matched,
        "availability": "partial" if truncated else "available",
        "reason": "tail_truncated" if truncated else None,
        "scanned_files": scanned,
        "truncated": truncated,
    }


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed
