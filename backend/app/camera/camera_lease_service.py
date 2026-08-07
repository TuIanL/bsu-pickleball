"""CameraLeaseManager —— 摄像机录制资源租约统一管理。"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.camera_lease import CameraLease, LeaseStatus

logger = logging.getLogger(__name__)


class LeaseConflictError(RuntimeError):
    def __init__(self, camera_id: str):
        super().__init__(f"摄像头 {camera_id} 已被占用")


class CameraLeaseManager:
    def __init__(self, db_factory):
        self._db_factory = db_factory

    def acquire(
        self,
        camera_ids: list[str],
        capture_take_id: str,
        source_session_id: str = "",
        owner_instance_id: str = "default",
    ) -> list[CameraLease]:
        """在事务中原子获取多路 Lease。任一冲突则整体回滚。"""
        db: Session = self._db_factory()
        try:
            for camera_id in camera_ids:
                result = db.execute(
                    text(
                        "INSERT INTO camera_leases (camera_id, capture_take_id, source_session_id, "
                        "owner_instance_id, status, acquired_at, heartbeat_at) "
                        "SELECT :cid, :tid, :sid, :oid, 'active', :ts, :ts "
                        "WHERE NOT EXISTS ("
                        "  SELECT 1 FROM camera_leases WHERE camera_id = :cid2 AND status = 'active'"
                        ") "
                        "RETURNING camera_id"
                    ),
                    {
                        "cid": camera_id,
                        "tid": capture_take_id,
                        "sid": source_session_id,
                        "oid": owner_instance_id,
                        "ts": datetime.now(UTC),
                        "cid2": camera_id,
                    },
                )
                if result.rowcount == 0:
                    raise LeaseConflictError(camera_id)
            db.commit()
            leases = (
                db.query(CameraLease)
                .filter(
                    CameraLease.capture_take_id == capture_take_id,
                    CameraLease.status == LeaseStatus.active,
                )
                .all()
            )
            return leases
        except LeaseConflictError:
            db.rollback()
            raise
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def release(self, capture_take_id: str) -> None:
        db: Session = self._db_factory()
        try:
            db.execute(
                text("UPDATE camera_leases SET status = 'released' WHERE capture_take_id = :tid AND status = 'active'"),
                {"tid": capture_take_id},
            )
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning("释放 CameraLease 失败: %s", exc)
        finally:
            db.close()

    def heartbeat(self, capture_take_id: str) -> None:
        db: Session = self._db_factory()
        try:
            db.execute(
                text("UPDATE camera_leases SET heartbeat_at = :ts WHERE capture_take_id = :tid AND status = 'active'"),
                {"tid": capture_take_id, "ts": datetime.now(UTC)},
            )
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    def find_active_lease(self, camera_id: str) -> CameraLease | None:
        db: Session = self._db_factory()
        try:
            return (
                db.query(CameraLease)
                .filter(
                    CameraLease.camera_id == camera_id,
                    CameraLease.status == LeaseStatus.active,
                )
                .first()
            )
        finally:
            db.close()

    def is_camera_available(self, camera_id: str) -> bool:
        return self.find_active_lease(camera_id) is None

    def cleanup_stale_leases(self) -> None:
        """扫描过期 Lease，清理孤儿 FFmpeg 进程并释放 Lease。"""
        import os
        import signal
        from datetime import timedelta

        db: Session = self._db_factory()
        try:
            stale_threshold = datetime.now(UTC) - timedelta(seconds=30)
            stale = (
                db.query(CameraLease)
                .filter(
                    CameraLease.status == LeaseStatus.active,
                    CameraLease.heartbeat_at < stale_threshold,
                )
                .all()
            )

            from app.models.ffmpeg_registry import FFmpegProcessRegistry

            for lease in stale:
                procs = (
                    db.query(FFmpegProcessRegistry)
                    .filter(
                        FFmpegProcessRegistry.capture_take_id == lease.capture_take_id,
                        FFmpegProcessRegistry.ended_at.is_(None),
                    )
                    .all()
                )
                for proc in procs:
                    try:
                        os.killpg(proc.pgid, signal.SIGTERM)
                        logger.info("清理孤儿 FFmpeg 进程 pgid=%d", proc.pgid)
                    except (ProcessLookupError, OSError):
                        pass
                lease.status = LeaseStatus.released
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning("cleanup_stale_leases 失败: %s", exc)
        finally:
            db.close()
