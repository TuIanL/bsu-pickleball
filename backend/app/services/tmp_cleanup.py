"""Retention cleanup for abandoned per-job temporary data."""

from __future__ import annotations

import logging
import os
import shutil
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def purge_stale_tmp(
    max_age_hours: float,
    *,
    storage: Any,
    job_store: Any,
    now: float | None = None,
) -> int:
    """Remove old temporary entries that do not belong to a running job.

    Failure to read the durable job list is fail-closed: cleanup is skipped so
    an active worker's scratch data cannot be deleted on incomplete evidence.
    """
    if max_age_hours <= 0:
        raise ValueError("max_age_hours must be greater than zero")

    root = Path(storage.tmp_dir)
    if not root.exists():
        return 0

    try:
        active_job_ids = {
            str(job.id) for job in job_store.list() if getattr(job, "canonicalStatus", None) == "running"
        }
    except Exception:
        logger.exception("Could not read job state; skipping stale temporary cleanup")
        return 0

    cutoff = (now if now is not None else time.time()) - max_age_hours * 60 * 60
    removed = 0
    for entry in root.iterdir():
        if entry.name == ".gitkeep" or entry.name in active_job_ids:
            continue
        try:
            if _latest_mtime(entry) > cutoff:
                continue
            if entry.is_symlink() or not entry.is_dir():
                entry.unlink(missing_ok=True)
            else:
                shutil.rmtree(entry)
            removed += 1
        except FileNotFoundError:
            # Another API/worker process may have removed the same stale entry.
            continue
        except OSError:
            logger.warning("Could not remove stale temporary entry %s", entry, exc_info=True)

    if removed:
        logger.info("Purged %s stale temporary entries from %s", removed, root)
    return removed


def _latest_mtime(path: Path) -> float:
    """Return the newest mtime below a directory without following symlinks."""
    latest = path.lstat().st_mtime
    if path.is_symlink() or not path.is_dir():
        return latest
    for current, directories, files in os.walk(path, followlinks=False):
        current_path = Path(current)
        for name in [*directories, *files]:
            child = current_path / name
            try:
                latest = max(latest, child.lstat().st_mtime)
            except FileNotFoundError:
                continue
    return latest


class DailyTmpCleanup:
    """Run an already-invoked startup cleanup once per day in the background."""

    def __init__(self, cleanup: Callable[[], object], *, interval_seconds: float = 24 * 60 * 60) -> None:
        self._cleanup = cleanup
        self._interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="pickleball-tmp-cleanup", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.wait(self._interval_seconds):
            try:
                self._cleanup()
            except Exception:
                logger.exception("Daily stale temporary cleanup failed")

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=max(0.0, timeout))
            if not thread.is_alive():
                self._thread = None
