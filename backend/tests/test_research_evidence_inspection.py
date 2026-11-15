"""Chunked hashing, read-only inspection and bounded media probing.

Covers the 2.1 requirements: interrupted reads stay ``not_checked``, the four
outcomes (missing, unreachable, mismatch, timeout) stay distinct, and the input
file is provably untouched.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.research_evidence.hashing import (
    inspect_file,
    sha256_file,
    snapshot_file,
)
from app.research_evidence.media_probe import probe_media


@pytest.fixture
def tmp_path() -> Iterator[Path]:
    """Override the plugin factory: its numbered mkdir collides with the sandbox shim."""
    with tempfile.TemporaryDirectory(prefix="pe-inspection-") as tmp:
        yield Path(tmp)


def _write(path: Path, payload: bytes) -> Path:
    path.write_bytes(payload)
    return path


# --- chunked hashing --------------------------------------------------------


def test_hash_matches_hashlib(tmp_path):
    payload = b"pickleball" * 1000
    target = _write(tmp_path / "clip.bin", payload)

    outcome = sha256_file(target, chunk_size=1024)

    assert outcome.completed
    assert outcome.sha256 == hashlib.sha256(payload).hexdigest()
    assert outcome.bytes_read == len(payload)


@pytest.mark.parametrize("chunk_size", [1, 7, 1024, 8 * 1024 * 1024])
def test_chunk_size_does_not_change_the_digest(tmp_path, chunk_size):
    payload = bytes(range(256)) * 40
    target = _write(tmp_path / "clip.bin", payload)

    assert sha256_file(target, chunk_size=chunk_size).sha256 == hashlib.sha256(
        payload
    ).hexdigest()


def test_expired_deadline_interrupts_without_a_digest(tmp_path):
    target = _write(tmp_path / "clip.bin", b"x" * 4096)

    outcome = sha256_file(target, deadline=time.monotonic() - 1)

    assert outcome.interruption == "timeout"
    assert outcome.sha256 is None
    assert outcome.bytes_read == 0


def test_cancellation_stops_the_read(tmp_path):
    target = _write(tmp_path / "clip.bin", b"x" * 4096)

    outcome = sha256_file(target, cancel=lambda: True)

    assert outcome.interruption == "cancelled"
    assert outcome.sha256 is None


def test_progress_callback_sees_cumulative_bytes(tmp_path):
    target = _write(tmp_path / "clip.bin", b"x" * 300)
    seen: list[int] = []

    sha256_file(target, chunk_size=100, on_progress=seen.append)

    assert seen == [100, 200, 300]


def test_invalid_chunk_size_is_rejected(tmp_path):
    target = _write(tmp_path / "clip.bin", b"x")

    with pytest.raises(ValueError):
        sha256_file(target, chunk_size=0)


def test_snapshot_reports_absence(tmp_path):
    snapshot = snapshot_file(tmp_path / "nothing.bin")

    assert snapshot.exists is False
    assert snapshot.size_bytes is None


# --- read-only inspection ---------------------------------------------------


def test_missing_file_is_reported_as_missing(tmp_path):
    result = inspect_file(tmp_path / "nothing.mp4")

    assert result.availability == "missing"
    assert result.verification == "unknown"
    assert result.sha256 is None


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file permissions")
def test_unreadable_file_is_unreachable_not_mismatch(tmp_path):
    target = _write(tmp_path / "locked.mp4", b"data")
    target.chmod(0o000)
    try:
        result = inspect_file(target)
    finally:
        target.chmod(0o644)

    assert result.availability == "unreachable"
    assert result.verification == "not_checked"


def test_matching_digest_is_verified(tmp_path):
    payload = b"real bytes"
    target = _write(tmp_path / "clip.mp4", payload)
    expected = hashlib.sha256(payload).hexdigest()

    result = inspect_file(target, expected_sha256=expected)

    assert result.availability == "present"
    assert result.verification == "verified"
    assert result.sha256 == expected
    assert result.size_bytes == len(payload)


def test_different_digest_is_mismatch(tmp_path):
    target = _write(tmp_path / "clip.mp4", b"real bytes")

    result = inspect_file(target, expected_sha256="a" * 64)

    assert result.availability == "present"
    assert result.verification == "mismatch"
    assert result.sha256 is not None


def test_digest_without_expectation_stays_unknown(tmp_path):
    target = _write(tmp_path / "clip.mp4", b"real bytes")

    result = inspect_file(target)

    assert result.verification == "unknown"
    assert result.sha256 is not None


def test_timeout_is_recorded_as_not_checked(tmp_path):
    target = _write(tmp_path / "clip.mp4", b"x" * 4096)

    result = inspect_file(target, timeout_seconds=-1)

    assert result.availability == "present"
    assert result.verification == "not_checked"
    assert result.sha256 is None
    assert "超时" in (result.detail or "")


def test_cancellation_is_recorded_as_not_checked(tmp_path):
    target = _write(tmp_path / "clip.mp4", b"x" * 4096)

    result = inspect_file(target, cancel=lambda: True)

    assert result.availability == "present"
    assert result.verification == "not_checked"
    assert "取消" in (result.detail or "")


def test_inspection_does_not_modify_the_input(tmp_path):
    target = _write(tmp_path / "clip.mp4", b"payload" * 500)
    before = snapshot_file(target)

    result = inspect_file(target)

    after = snapshot_file(target)
    assert result.input_unchanged is True
    assert before.matches(after)
    assert after.mtime_ns == before.mtime_ns


# --- bounded media probing --------------------------------------------------


class _CompletedProcess:
    def __init__(self, stdout: bytes, returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = b""
        self.returncode = returncode


def test_probe_timeout_is_distinct_from_error(monkeypatch, tmp_path):
    def _raise(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="ffprobe", timeout=1)

    monkeypatch.setattr("app.research_evidence.media_probe.subprocess.run", _raise)

    probe = probe_media(tmp_path / "clip.mp4", timeout_seconds=1)

    assert probe.status == "timeout"


def test_probe_reports_skipped_when_ffprobe_is_absent(monkeypatch, tmp_path):
    def _raise(*_args, **_kwargs):
        raise FileNotFoundError("ffprobe")

    monkeypatch.setattr("app.research_evidence.media_probe.subprocess.run", _raise)

    probe = probe_media(tmp_path / "clip.mp4")

    assert probe.status == "skipped"


def test_probe_parses_container_metadata(monkeypatch, tmp_path):
    payload = {
        "streams": [
            {
                "width": 1920,
                "height": 1080,
                "r_frame_rate": "60/1",
                "nb_frames": "N/A",
                "duration": "698.800000",
            }
        ]
    }

    monkeypatch.setattr(
        "app.research_evidence.media_probe.subprocess.run",
        lambda *_args, **_kwargs: _CompletedProcess(json.dumps(payload).encode()),
    )

    probe = probe_media(tmp_path / "clip.mp4")

    assert probe.status == "ok"
    assert (probe.width, probe.height) == (1920, 1080)
    assert probe.fps_nominal == 60.0
    assert probe.duration_seconds == 698.8
    assert probe.frame_count is None
    assert "未执行解码" in (probe.detail or "")


def test_probe_rejects_output_without_streams(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.research_evidence.media_probe.subprocess.run",
        lambda *_args, **_kwargs: _CompletedProcess(b'{"streams": []}'),
    )

    assert probe_media(tmp_path / "clip.mp4").status == "error"


def test_probe_reports_non_zero_exit_as_error(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.research_evidence.media_probe.subprocess.run",
        lambda *_args, **_kwargs: _CompletedProcess(b"", returncode=1),
    )

    assert probe_media(tmp_path / "clip.mp4").status == "error"


def test_text_file_is_not_probed_as_video(tmp_path):
    """With a real ffprobe this must fail; without one it is skipped."""
    fake = _write(tmp_path / "fake.mp4", b"definitely not a video")

    assert probe_media(fake).status in {"error", "skipped"}


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file permissions")
def test_state_matrix_matches_documented_rules(tmp_path):
    """Verify every row of the 状态映射 table in research-evidence-contract.md."""
    payload = b"state matrix"
    expected_digest = hashlib.sha256(payload).hexdigest()

    # 路径不存在
    absent = inspect_file(tmp_path / "absent.mp4")
    assert (absent.availability, absent.verification) == ("missing", "unknown")

    # 存在但权限不足
    locked = _write(tmp_path / "locked.mp4", payload)
    locked.chmod(0o000)
    try:
        unreachable = inspect_file(locked)
    finally:
        locked.chmod(0o644)
    assert (unreachable.availability, unreachable.verification) == (
        "unreachable",
        "not_checked",
    )

    target = _write(tmp_path / "clip.mp4", payload)

    # 摘要计算超时
    timed_out = inspect_file(target, timeout_seconds=-1)
    assert (timed_out.availability, timed_out.verification) == (
        "present",
        "not_checked",
    )

    # 摘要计算被取消
    cancelled = inspect_file(target, cancel=lambda: True)
    assert (cancelled.availability, cancelled.verification) == (
        "present",
        "not_checked",
    )

    # 摘要与期望值不符
    mismatch = inspect_file(target, expected_sha256="b" * 64)
    assert (mismatch.availability, mismatch.verification) == ("present", "mismatch")

    # 摘要与期望值相符
    verified = inspect_file(target, expected_sha256=expected_digest)
    assert (verified.availability, verified.verification) == ("present", "verified")

    # 算出摘要但无期望值
    unknown = inspect_file(target)
    assert (unknown.availability, unknown.verification) == ("present", "unknown")
