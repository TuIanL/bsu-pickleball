"""Capture Recovery —— 启动时恢复孤儿进程和 incomplete Capture"""

from __future__ import annotations

import logging
import os
import signal
from datetime import UTC, datetime, timedelta

from app.database import get_session_factory
from app.models.camera_lease import CameraLease, LeaseStatus
from app.models.capture_take import CaptureTake, CaptureTakeStatus
from app.models.ffmpeg_registry import FFmpegProcessRegistry
from app.models.media_fragment import FragmentStatus, MediaFragment

logger = logging.getLogger(__name__)


def recover_orphan_recordings() -> None:
    """应用启动时扫描并恢复孤儿进程和 incomplete Capture。"""
    db = get_session_factory()()

    try:
        stale_threshold = datetime.now(UTC) - timedelta(seconds=30)

        # 1. 清理孤儿 FFmpeg 进程
        orphan_regs = (
            db.query(FFmpegProcessRegistry)
            .filter(
                FFmpegProcessRegistry.ended_at.is_(None),
                FFmpegProcessRegistry.started_at < stale_threshold,
            )
            .all()
        )

        for reg in orphan_regs:
            try:
                os.killpg(reg.pgid, signal.SIGTERM)
                logger.info("清理孤儿 FFmpeg pgid=%d (reg_id=%d)", reg.pgid, reg.id)
            except (ProcessLookupError, OSError):
                pass

        # 2. 标记 lingering Fragment 为 interrupted
        lingering = (
            db.query(MediaFragment)
            .filter(
                MediaFragment.status.in_([FragmentStatus.starting, FragmentStatus.recording]),
                MediaFragment.started_at < stale_threshold,
            )
            .all()
        )

        for frag in lingering:
            frag.status = FragmentStatus.interrupted
            frag.ended_at = datetime.now(UTC)
            frag.error_message = "应用崩溃导致中断"
            logger.info("标记 Fragment %s 为 interrupted", frag.id)

        # 3. Release 过期 Lease
        stale_leases = (
            db.query(CameraLease)
            .filter(
                CameraLease.status == LeaseStatus.active,
                CameraLease.heartbeat_at < stale_threshold,
            )
            .all()
        )

        for lease in stale_leases:
            lease.status = LeaseStatus.released
            logger.info("释放过期 Lease camera=%s take=%s", lease.camera_id, lease.capture_take_id)

        # 4. 终态化孤儿 CaptureTake：启动时任何仍为 starting/recording 的 Take 都是孤儿
        from app.services.capture_take_service import finalize_capture_take

        orphan_takes = (
            db.query(CaptureTake)
            .filter(
                CaptureTake.status.in_([CaptureTakeStatus.starting, CaptureTakeStatus.recording]),
            )
            .all()
        )

        fixed_count = 0
        for take in orphan_takes:
            try:
                finalize_capture_take(db, take.id, "failed")
                fixed_count += 1
                logger.info("修复孤儿 CaptureTake %s (status=%s → failed)", take.id, take.status.value)
            except Exception as exc:
                logger.warning("修复孤儿 CaptureTake %s 失败: %s", take.id, exc)

        if fixed_count > 0:
            logger.info("启动恢复：共修复 %d 条孤儿 CaptureTake", fixed_count)

        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning("recover_orphan_recordings failed: %s", e)
    finally:
        db.close()
