"""Capture Recovery —— 启动时恢复孤儿进程和 incomplete Capture"""
from __future__ import annotations

import logging
import os
import signal
from datetime import datetime, timedelta, timezone

from app.database import get_session_factory
from app.models.ffmpeg_registry import FFmpegProcessRegistry
from app.models.media_fragment import MediaFragment, FragmentStatus
from app.models.camera_lease import CameraLease, LeaseStatus

logger = logging.getLogger(__name__)


def recover_orphan_recordings() -> None:
    """应用启动时扫描并恢复孤儿进程和 incomplete Capture。"""
    db = get_session_factory()()

    try:
        stale_threshold = datetime.now(timezone.utc) - timedelta(seconds=30)

        # 1. 清理孤儿 FFmpeg 进程
        orphan_regs = db.query(FFmpegProcessRegistry).filter(
            FFmpegProcessRegistry.ended_at.is_(None),
            FFmpegProcessRegistry.started_at < stale_threshold,
        ).all()

        for reg in orphan_regs:
            try:
                os.killpg(reg.pgid, signal.SIGTERM)
                logger.info("清理孤儿 FFmpeg pgid=%d (reg_id=%d)", reg.pgid, reg.id)
            except (ProcessLookupError, OSError):
                pass

        # 2. 标记 lingering Fragment 为 interrupted
        lingering = db.query(MediaFragment).filter(
            MediaFragment.status.in_([FragmentStatus.starting, FragmentStatus.recording]),
            MediaFragment.started_at < stale_threshold,
        ).all()

        for frag in lingering:
            frag.status = FragmentStatus.interrupted
            frag.ended_at = datetime.now(timezone.utc)
            frag.error_message = "应用崩溃导致中断"
            logger.info("标记 Fragment %s 为 interrupted", frag.id)

        # 3. Release 过期 Lease
        stale_leases = db.query(CameraLease).filter(
            CameraLease.status == LeaseStatus.active,
            CameraLease.heartbeat_at < stale_threshold,
        ).all()

        for lease in stale_leases:
            lease.status = LeaseStatus.released
            logger.info("释放过期 Lease camera=%s take=%s", lease.camera_id, lease.capture_take_id)

        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning("recover_orphan_recordings failed: %s", e)
    finally:
        db.close()
