"""CaptureStartCoordinator —— 统一录制启动编排，单事务创建 Take + Tracks + Leases。"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.models.capture_take import CaptureMode, CaptureTakeStatus, SourceSessionType


@dataclass
class CaptureTrackSpec:
    slot: str
    camera_id: str
    analysis_role: str = "default"


@dataclass(frozen=True)
class PreparedTrack:
    capture_track_id: str
    slot: str
    camera_id: str
    analysis_role: str


@dataclass
class PreparedCapture:
    capture_take_id: str
    field_session_id: str
    capture_mode: str
    source_session_type: str
    source_session_id: str
    tracks: list[PreparedTrack] = field(default_factory=list)


class CaptureStartCoordinator:
    def __init__(self, db_factory, lease_manager):
        self._db_factory = db_factory
        self._lease_manager = lease_manager

    def prepare_start(
        self,
        *,
        source_session_type: str,
        source_session_id: str,
        field_session_id: str,
        capture_mode: str,
        tracks: list[CaptureTrackSpec],
        storage_root: str | None = None,
        session_dir: str | None = None,
    ) -> PreparedCapture:
        """在单事务中创建 CaptureTake + N CaptureTrack + N CameraLease。"""
        from app.database import get_session_factory

        take_id = self._generate_take_id(source_session_type, source_session_id)
        camera_ids = [t.camera_id for t in tracks]

        db = self._db_factory()
        try:
            from app.models.capture_take import CaptureTake
            from app.models.capture_track import CaptureTrack, CaptureTrackSlot, AnalysisRole, TrackRole

            take = CaptureTake(
                id=take_id,
                field_session_id=field_session_id,
                capture_mode=CaptureMode(capture_mode),
                source_session_type=SourceSessionType(source_session_type),
                source_session_id=source_session_id,
                storage_root=storage_root,
                session_dir=session_dir,
                status=CaptureTakeStatus.starting,
                started_at=datetime.now(timezone.utc),
            )
            db.add(take)
            db.flush()
            from app.services.capture_take_service import initialize_capture_take_timeline
            initialize_capture_take_timeline(db, take)

            prepared_tracks: list[PreparedTrack] = []
            for spec in tracks:
                track_id = self._generate_track_id(take_id, spec.slot)
                track = CaptureTrack(
                    id=track_id,
                    capture_take_id=take_id,
                    camera_id=spec.camera_id,
                    role=TrackRole.primary if spec.analysis_role == "default" else TrackRole.secondary,
                    slot=CaptureTrackSlot(spec.slot),
                    analysis_role=AnalysisRole(spec.analysis_role),
                )
                db.add(track)
                prepared_tracks.append(PreparedTrack(
                    capture_track_id=track_id,
                    slot=spec.slot,
                    camera_id=spec.camera_id,
                    analysis_role=spec.analysis_role,
                ))

            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        try:
            self._lease_manager.acquire(camera_ids, take_id, source_session_id=source_session_id)
        except Exception:
            db = self._db_factory()
            try:
                take = db.query(CaptureTake).filter(CaptureTake.id == take_id).first()
                if take:
                    take.status = CaptureTakeStatus.failed
                    db.commit()
            except Exception:
                db.rollback()
            finally:
                db.close()
            raise

        return PreparedCapture(
            capture_take_id=take_id,
            field_session_id=field_session_id,
            capture_mode=capture_mode,
            source_session_type=source_session_type,
            source_session_id=source_session_id,
            tracks=prepared_tracks,
        )

    def activate(self, capture_take_id: str) -> None:
        """FFmpeg 启动成功后，将 CaptureTake 标记为 recording。"""
        db = self._db_factory()
        try:
            from app.models.capture_take import CaptureTake, CaptureTakeStatus
            take = db.query(CaptureTake).filter(CaptureTake.id == capture_take_id).first()
            if take and take.status == CaptureTakeStatus.starting:
                take.status = CaptureTakeStatus.recording
                db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    def mark_failed(self, capture_take_id: str) -> None:
        """FFmpeg 启动失败时标记。"""
        db = self._db_factory()
        try:
            from app.models.capture_take import CaptureTake, CaptureTakeStatus
            take = db.query(CaptureTake).filter(CaptureTake.id == capture_take_id).first()
            if take:
                take.status = CaptureTakeStatus.failed
                take.ended_at = datetime.now(timezone.utc)
                db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    @staticmethod
    def _generate_take_id(source_session_type: str, source_session_id: str) -> str:
        return f"take_{source_session_id}"

    @staticmethod
    def _generate_track_id(take_id: str, slot: str) -> str:
        return f"track_{take_id}_{slot}"
