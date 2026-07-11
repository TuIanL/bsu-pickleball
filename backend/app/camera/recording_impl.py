"""录制协议生产实现 —— DbFragmentRepository、SystemClock"""
from __future__ import annotations

import hashlib
import os
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.database import get_session_factory
from app.models.media_fragment import MediaFragment, FragmentStatus
from app.models.ffmpeg_registry import FFmpegProcessRegistry


class DbFragmentRepository:
    def create_starting(self, *, capture_take_id: str, capture_track_id: str,
                        fragment_index: int, rotation_index: int,
                        file_path: str, take_start_offset_ms: int) -> str:
        fid = f"frag_{uuid.uuid4().hex[:12]}"
        db = get_session_factory()()
        try:
            f = MediaFragment(
                id=fid, capture_take_id=capture_take_id, capture_track_id=capture_track_id,
                fragment_index=fragment_index, rotation_index=rotation_index,
                file_path=file_path, status=FragmentStatus.starting,
                take_start_offset_ms=take_start_offset_ms,
            )
            db.add(f)
            db.commit()
            return fid
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def mark_recording(self, fragment_id: str) -> None:
        db = get_session_factory()()
        try:
            f = db.query(MediaFragment).filter(MediaFragment.id == fragment_id).first()
            if f:
                f.status = FragmentStatus.recording
                db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    def complete(self, fragment_id: str, *, status: str, file_size: int = 0,
                 media_duration_ms: int = 0, return_code: int = 0,
                 take_end_offset_ms: int = 0, stop_reason: str = "",
                 error_message: str = "") -> None:
        db = get_session_factory()()
        try:
            f = db.query(MediaFragment).filter(MediaFragment.id == fragment_id).first()
            if f:
                f.status = FragmentStatus(status)
                f.ended_at = datetime.now(timezone.utc)
                f.file_size = file_size
                f.media_duration_ms = media_duration_ms
                f.return_code = return_code
                f.take_end_offset_ms = take_end_offset_ms
                f.stop_reason = stop_reason
                f.error_message = error_message
                db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()


class SystemClock:
    def utc_now(self) -> datetime:
        return datetime.now(timezone.utc)

    def monotonic_ms(self) -> int:
        import time
        return int(time.monotonic() * 1000)


class DbProcessRegistry:
    def register_started(self, *, capture_take_id: str, capture_track_id: str,
                         fragment_id: str, pid: int, pgid: int,
                         command_fingerprint: str, output_path: str) -> int:
        db = get_session_factory()()
        try:
            rec = FFmpegProcessRegistry(
                capture_take_id=capture_take_id, track_id=capture_track_id,
                pid=pid, pgid=pgid, command_fingerprint=command_fingerprint,
                output_path=output_path, fragment_id=fragment_id,
                started_at=datetime.now(timezone.utc),
            )
            db.add(rec)
            db.commit()
            return rec.id
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def register_ended(self, registration_id: int, *, return_code: int,
                       exit_reason: str, ended_at: datetime) -> None:
        db = get_session_factory()()
        try:
            db.query(FFmpegProcessRegistry).filter(
                FFmpegProcessRegistry.id == registration_id,
            ).update({"return_code": return_code, "exit_reason": exit_reason,
                       "ended_at": ended_at})
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()
