"""Startup backfill of missing source PTS sidecars for registered videos.

Historical sync-recording sessions (merged before the sidecar materialization
mechanism existed) permanently lack ``<media>.pts.jsonl``, which blocks the
sync-anchor workbench with a ``source_pts_missing`` 409.  This module scans
every registered video at startup and asynchronously backfills missing
sidecars on a daemon thread with a bounded concurrency, so a cold external
drive or a slow ffprobe never blocks server startup.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any

from app.services.multiview_acceptance import (
    materialize_registered_video_timing,
    timing_sidecar_path,
)

logger = logging.getLogger(__name__)

# Maximum number of videos materialized concurrently during the startup scan.
PTS_BACKFILL_CONCURRENCY = max(1, int(os.environ.get("PICKLEBALL_PTS_BACKFILL_CONCURRENCY", "1")))


def collect_registered_media(
    video_service: Any | None = None,
    sync_recording_service: Any | None = None,
) -> list[tuple[str, Path]]:
    """Return deduplicated ``(video_id, media_path)`` for every registered video.

    Sources:
    - the shared VideoService registry (all persisted + cached metadata), and
    - sync-recording session ``registered_video_ids`` that may reference media
      whose metadata has not been re-registered after a restart.

    Media that is missing or empty on disk is excluded from the result.
    """
    from app.services.video_service import video_service as default_video_service

    service = video_service or default_video_service
    candidates: dict[str, Path] = {}
    for metadata in service.list_videos():
        path = Path(metadata.path).expanduser().resolve(strict=False)
        if path.is_file() and path.stat().st_size > 0:
            candidates[metadata.id] = path

    if sync_recording_service is not None:
        try:
            for session in sync_recording_service.list_sessions():
                for video_id in (session.registered_video_ids or {}).values():
                    if not video_id or video_id in candidates:
                        continue
                    metadata = service.get_available_video(video_id)
                    if metadata is None:
                        continue
                    path = Path(metadata.path).expanduser().resolve(strict=False)
                    if path.is_file() and path.stat().st_size > 0:
                        candidates[video_id] = path
        except Exception as exc:  # noqa: BLE001
            logger.warning("PTS sidecar 启动扫描: 读取 sync-recording 会话失败: %s", exc)

    return list(candidates.items())


def _materialize_one(video_id: str, media_path: Path) -> str:
    """Materialize one sidecar, returning ``ok`` / ``skipped`` / ``failed``."""
    if timing_sidecar_path(media_path).is_file():
        return "skipped"
    result = materialize_registered_video_timing(media_path)
    if result.status == "ready" and result.timing_authority == "source_pts":
        logger.info("PTS sidecar 启动补写成功 %s (%s)", video_id, result.sidecar_path)
        return "ok"
    logger.warning("PTS sidecar 启动补写失败 %s: %s", video_id, result.reason or "unknown")
    return "failed"


def start_timing_backfill(
    video_service: Any | None = None,
    sync_recording_service: Any | None = None,
) -> threading.Thread:
    """Scan registered videos and backfill missing sidecars in the background.

    Returns the daemon thread immediately; the caller must not join it.
    Every failure is captured and logged as a warning so startup is never
    blocked, even when the external drive is not mounted.
    """

    def _run() -> None:
        try:
            candidates = collect_registered_media(video_service, sync_recording_service)
        except Exception as exc:  # noqa: BLE001
            logger.warning("PTS sidecar 启动扫描异常: %s", exc)
            return
        if not candidates:
            logger.info("PTS sidecar 启动扫描: 无 registered video，跳过")
            return
        missing = [
            (video_id, path)
            for video_id, path in candidates
            if not timing_sidecar_path(path).is_file()
        ]
        if not missing:
            logger.info("PTS sidecar 启动扫描: %d 个 registered video 全部就绪，无需补写", len(candidates))
            return
        logger.info(
            "PTS sidecar 启动扫描: %d/%d 个 registered video 缺失 sidecar，开始后台补写 (concurrency=%d)",
            len(missing),
            len(candidates),
            PTS_BACKFILL_CONCURRENCY,
        )

        semaphore = threading.Semaphore(PTS_BACKFILL_CONCURRENCY)
        counters = {"ok": 0, "skipped": 0, "failed": 0}
        counters_lock = threading.Lock()

        def _worker(video_id: str, path: Path) -> None:
            with semaphore:
                outcome = _materialize_one(video_id, path)
            with counters_lock:
                counters[outcome] = counters.get(outcome, 0) + 1

        threads = [
            threading.Thread(
                target=_worker,
                args=(video_id, path),
                name=f"pts-backfill-{video_id}",
                daemon=True,
            )
            for video_id, path in missing
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        logger.info(
            "PTS sidecar 启动扫描完成: 补写成功=%d, 跳过=%d, 失败=%d",
            counters["ok"],
            counters["skipped"],
            counters["failed"],
        )

    thread = threading.Thread(target=_run, name="pts-sidecar-startup-backfill", daemon=True)
    thread.start()
    return thread
