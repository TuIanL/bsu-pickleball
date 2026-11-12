"""Chunked, cancellable content hashing and read-only file inspection.

Reading a 1.2 GB take from an exFAT external disk must stay interruptible and
must never mutate the input. Every inspection therefore snapshots size and
mtime before and after the read, so a caller can prove the file was untouched.

Availability and verification stay separate: a permission error is
``unreachable`` and never ``mismatch``, and an interrupted hash is
``not_checked`` rather than a failed comparison.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .identity import normalize_sha256

DEFAULT_CHUNK_SIZE = 8 * 1024 * 1024

Availability = Literal["present", "missing", "unreachable", "not_checked"]
Verification = Literal["verified", "mismatch", "not_checked", "unknown"]
Interruption = Literal["none", "cancelled", "timeout"]


@dataclass(frozen=True)
class FileSnapshot:
    """Size and mtime used to prove a file was not modified during a read."""

    exists: bool
    size_bytes: int | None
    mtime_ns: int | None

    def matches(self, other: "FileSnapshot") -> bool:
        return (
            self.exists,
            self.size_bytes,
            self.mtime_ns,
        ) == (
            other.exists,
            other.size_bytes,
            other.mtime_ns,
        )


@dataclass(frozen=True)
class HashOutcome:
    """Result of a hash run. ``sha256`` is None when the run was interrupted."""

    sha256: str | None
    bytes_read: int
    interruption: Interruption

    @property
    def completed(self) -> bool:
        return self.interruption == "none"


@dataclass(frozen=True)
class FileInspection:
    """Combined availability, verification and read-only evidence."""

    availability: Availability
    verification: Verification
    sha256: str | None
    size_bytes: int | None
    detail: str | None
    input_unchanged: bool


def snapshot_file(path: Path) -> FileSnapshot:
    """Capture size and mtime without following into any mutation."""
    try:
        stat = Path(path).stat()
    except FileNotFoundError:
        return FileSnapshot(exists=False, size_bytes=None, mtime_ns=None)
    except OSError:
        # The path exists but its attributes cannot be read.
        return FileSnapshot(exists=True, size_bytes=None, mtime_ns=None)
    return FileSnapshot(exists=True, size_bytes=stat.st_size, mtime_ns=stat.st_mtime_ns)


def sha256_file(
    path: Path,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    deadline: float | None = None,
    cancel: Callable[[], bool] | None = None,
    on_progress: Callable[[int], None] | None = None,
) -> HashOutcome:
    """Hash a file in chunks, honouring a cancellation predicate and a deadline.

    ``deadline`` is an absolute ``time.monotonic()`` value. Interruption is
    reported as a value rather than an exception so the caller can record it as
    ``not_checked`` without losing what was already read.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    hasher = hashlib.sha256()
    bytes_read = 0
    with Path(path).open("rb") as handle:
        while True:
            if cancel is not None and cancel():
                return HashOutcome(None, bytes_read, "cancelled")
            if deadline is not None and time.monotonic() > deadline:
                return HashOutcome(None, bytes_read, "timeout")

            chunk = handle.read(chunk_size)
            if not chunk:
                break

            hasher.update(chunk)
            bytes_read += len(chunk)
            if on_progress is not None:
                on_progress(bytes_read)

    return HashOutcome(hasher.hexdigest(), bytes_read, "none")


def inspect_file(
    path: Path,
    *,
    expected_sha256: str | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    timeout_seconds: float | None = None,
    cancel: Callable[[], bool] | None = None,
) -> FileInspection:
    """Inspect one file without modifying it.

    Distinguishes the four outcomes that must never be conflated: missing path,
    unreachable file, digest mismatch and probe timeout.
    """
    before = snapshot_file(path)

    if not before.exists:
        return FileInspection("missing", "unknown", None, None, "路径不存在", True)
    if before.size_bytes is None:
        return FileInspection(
            "unreachable", "not_checked", None, None, "无法读取文件属性", True
        )

    deadline = (
        time.monotonic() + timeout_seconds if timeout_seconds is not None else None
    )
    try:
        outcome = sha256_file(
            path, chunk_size=chunk_size, deadline=deadline, cancel=cancel
        )
    except FileNotFoundError:
        return FileInspection(
            "missing", "unknown", None, None, "读取期间文件消失", True
        )
    except PermissionError:
        return FileInspection(
            "unreachable", "not_checked", None, None, "权限不足，无法读取", True
        )
    except OSError as error:
        return FileInspection(
            "unreachable", "not_checked", None, None, f"读取失败: {error}", True
        )

    after = snapshot_file(path)
    unchanged = before.matches(after)

    if not outcome.completed:
        reason = "已取消" if outcome.interruption == "cancelled" else "超时"
        detail = f"摘要计算{reason}，已读 {outcome.bytes_read} 字节"
        return FileInspection(
            "present", "not_checked", None, before.size_bytes, detail, unchanged
        )

    sha256 = outcome.sha256
    if expected_sha256 is None:
        return FileInspection(
            "present",
            "unknown",
            sha256,
            before.size_bytes,
            "已计算摘要，但无期望值可比对",
            unchanged,
        )

    expected = normalize_sha256(expected_sha256)
    verification: Verification = "verified" if sha256 == expected else "mismatch"
    detail = None if verification == "verified" else "摘要与期望值不符"
    return FileInspection(
        "present", verification, sha256, before.size_bytes, detail, unchanged
    )
