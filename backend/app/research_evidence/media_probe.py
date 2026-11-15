"""Bounded ffprobe metadata probing.

A metadata probe is not a decode. It reports what the container declares and
records its own coverage limit, so a successful probe can never be upgraded into
"fully decoded" by a caller.

Timeouts and failures are distinct outcomes: on a sleeping external disk the
probe may time out while the file itself is perfectly readable later.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

DEFAULT_PROBE_TIMEOUT_SECONDS = 15.0

ProbeStatus = Literal["ok", "timeout", "error", "skipped"]


@dataclass(frozen=True)
class MediaProbe:
    """Container-declared metadata plus an explicit probe status."""

    status: ProbeStatus
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None
    fps_nominal: float | None = None
    frame_count: int | None = None
    detail: str | None = None


def _parse_rate(value: object) -> float | None:
    """Parse ffprobe rational rates such as ``60/1`` or ``30000/1001``."""
    if not isinstance(value, str) or "/" not in value:
        return None
    numerator, _, denominator = value.partition("/")
    try:
        denominator_value = float(denominator)
        if denominator_value == 0:
            return None
        return float(numerator) / denominator_value
    except ValueError:
        return None


def _parse_float(value: object) -> float | None:
    if value is None or value == "N/A":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_int(value: object) -> int | None:
    if value is None or value == "N/A":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _redact_input_path(text: str, path: Path) -> str:
    """ffprobe echoes the input path in errors; a shareable manifest must not carry it."""
    redacted = text
    for candidate in {str(path), str(Path(path).resolve())}:
        if candidate:
            redacted = redacted.replace(candidate, "<source>")
    return redacted


def probe_media(
    path: Path,
    *,
    timeout_seconds: float = DEFAULT_PROBE_TIMEOUT_SECONDS,
) -> MediaProbe:
    """Read stream metadata with a hard timeout. Never decodes the file."""
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,r_frame_rate,nb_frames,duration",
        "-of",
        "json",
        str(path),
    ]

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return MediaProbe(
            status="timeout",
            detail=f"ffprobe 在 {timeout_seconds:g} 秒内未返回",
        )
    except FileNotFoundError:
        return MediaProbe(status="skipped", detail="环境中没有 ffprobe")
    except OSError as error:
        return MediaProbe(status="error", detail=f"无法启动 ffprobe: {error}")

    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", "replace").strip()
        raw_detail = stderr.splitlines()[-1] if stderr else "ffprobe 返回非零状态"
        return MediaProbe(
            status="error",
            detail=_redact_input_path(raw_detail, path),
        )

    try:
        payload = json.loads(completed.stdout.decode("utf-8", "replace") or "{}")
    except json.JSONDecodeError:
        return MediaProbe(status="error", detail="ffprobe 输出不是合法 JSON")

    streams = payload.get("streams") or []
    if not streams:
        return MediaProbe(status="error", detail="未找到视频流")

    stream = streams[0]
    return MediaProbe(
        status="ok",
        duration_seconds=_parse_float(stream.get("duration")),
        width=_parse_int(stream.get("width")),
        height=_parse_int(stream.get("height")),
        fps_nominal=_parse_rate(stream.get("r_frame_rate")),
        frame_count=_parse_int(stream.get("nb_frames")),
        detail="仅读取容器元数据，未执行解码",
    )
