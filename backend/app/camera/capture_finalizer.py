"""CaptureFinalizer —— 片段合并、校验、Video 注册"""
from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path

from app.database import get_session_factory
from app.models.media_fragment import MediaFragment, FragmentStatus
from app.models.track_finalization import TrackFinalization, FinalizationStatus
from app.models.track_timeline_span import TrackTimelineSpan

logger = logging.getLogger(__name__)


@dataclass
class TrackFinalizationResult:
    capture_track_id: str
    status: str  # succeeded / reused / failed / no_media
    video_id: str | None = None
    output_path: str | None = None
    fragment_count: int = 0
    warnings: list[str] = field(default_factory=list)


class CaptureFinalizer:
    def __init__(self, finalizer_timeout: int = 60):
        self._timeout = finalizer_timeout

    def finalize_track(self, capture_track_id: str,
                       fragment_infos: list[dict]) -> TrackFinalizationResult:
        valid = []
        for f in fragment_infos:
            path = f.get("file_path", "")
            if os.path.exists(path) and os.path.getsize(path) > 0:
                valid.append(f)

        if not valid:
            return TrackFinalizationResult(
                capture_track_id=capture_track_id,
                status="no_media",
                warnings=["无有效片段"],
            )

        valid.sort(key=lambda f: f.get("fragment_index", 0))
        manifest_hash = self._compute_manifest_hash(valid)

        existing = self._find_existing_finalization(capture_track_id, manifest_hash)
        if existing and existing.status == FinalizationStatus.completed:
            return TrackFinalizationResult(
                capture_track_id=capture_track_id,
                status="reused", video_id=existing.video_id,
                output_path=existing.output_path,
                fragment_count=len(valid),
            )

        finalization_id = self._create_finalization_record(capture_track_id, manifest_hash)

        output_path = Path(f"data/recordings/finalized/{capture_track_id}.mp4")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = Path(str(output_path) + ".finalizing")

        concat_file = temp_path.with_suffix(".concat.txt")
        try:
            self._write_concat_manifest(concat_file, valid)
            success = self._run_concat(concat_file, temp_path)
            if not success:
                self._mark_finalization_failed(finalization_id, "concat failed")
                return TrackFinalizationResult(
                    capture_track_id=capture_track_id,
                    status="failed", fragment_count=len(valid),
                    warnings=["合并失败"],
                )

            if not self._validate_output(temp_path):
                self._mark_finalization_failed(finalization_id, "ffprobe validation failed")
                return TrackFinalizationResult(
                    capture_track_id=capture_track_id,
                    status="failed", fragment_count=len(valid),
                    warnings=["输出校验失败"],
                )

            os.replace(temp_path, output_path)

            video_id = self._register_video(output_path, capture_track_id)

            self._generate_timeline_spans(finalization_id, valid)

            self._mark_finalization_completed(finalization_id, str(output_path), video_id)

            return TrackFinalizationResult(
                capture_track_id=capture_track_id,
                status="succeeded", video_id=video_id,
                output_path=str(output_path), fragment_count=len(valid),
            )
        finally:
            if concat_file.exists():
                concat_file.unlink(missing_ok=True)
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)

    def _compute_manifest_hash(self, fragments: list[dict]) -> str:
        data = "".join(f"{f.get('file_path')}:{f.get('fragment_index')}" for f in fragments)
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def _find_existing_finalization(self, track_id: str, manifest_hash: str) -> TrackFinalization | None:
        db = get_session_factory()()
        try:
            return db.query(TrackFinalization).filter(
                TrackFinalization.capture_track_id == track_id,
                TrackFinalization.manifest_hash == manifest_hash,
            ).first()
        finally:
            db.close()

    def _create_finalization_record(self, track_id: str, manifest_hash: str) -> str:
        fid = f"fin_{uuid.uuid4().hex[:12]}"
        db = get_session_factory()()
        try:
            f = TrackFinalization(
                id=fid, capture_track_id=track_id,
                manifest_hash=manifest_hash,
                status=FinalizationStatus.running,
            )
            db.add(f)
            db.commit()
            return fid
        except Exception:
            db.rollback()
            return fid
        finally:
            db.close()

    def _write_concat_manifest(self, path: Path, fragments: list[dict]) -> None:
        with open(path, "w") as f:
            for frag in fragments:
                f.write(f"file '{frag['file_path']}'\n")

    def _run_concat(self, manifest: Path, output: Path) -> bool:
        try:
            result = subprocess.run(
                ["ffmpeg", "-f", "concat", "-safe", "0", "-i", str(manifest),
                 "-c", "copy", "-y", str(output)],
                capture_output=True, timeout=self._timeout,
            )
            return result.returncode == 0 and output.exists() and output.stat().st_size > 0
        except Exception as e:
            logger.warning("concat failed: %s", e)
            return False

    def _validate_output(self, path: Path) -> bool:
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_format", str(path)],
                capture_output=True, timeout=10,
            )
            return result.returncode == 0 and path.exists() and path.stat().st_size > 0
        except Exception:
            return False

    def _register_video(self, path: Path, track_id: str) -> str | None:
        try:
            from app.services.video_service import video_service
            vid = video_service.register_recording(
                file_path=path,
                original_filename=path.name,
                file_size=path.stat().st_size,
            )
            return vid
        except Exception as e:
            logger.warning("video register failed: %s", e)
            return None

    def _generate_timeline_spans(self, finalization_id: str, fragments: list[dict]) -> None:
        db = get_session_factory()()
        try:
            output_ms = 0
            for frag in fragments:
                take_start = frag.get("take_start_offset_ms", output_ms)
                media_dur = self._get_fragment_duration(frag.get("file_path", ""))
                take_end = take_start + media_dur
                gap = frag.get("gap_before_ms", 0)

                span = TrackTimelineSpan(
                    track_finalization_id=finalization_id,
                    fragment_id=frag.get("fragment_id", ""),
                    take_start_ms=take_start,
                    take_end_ms=take_end,
                    output_start_ms=output_ms,
                    output_end_ms=output_ms + media_dur,
                    gap_before_ms=gap,
                )
                db.add(span)
                output_ms += media_dur

            db.commit()
        except Exception as e:
            db.rollback()
            logger.warning("timeline span generation failed: %s", e)
        finally:
            db.close()

    def _get_fragment_duration(self, file_path: str) -> int:
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", file_path],
                capture_output=True, timeout=10,
            )
            if result.returncode == 0:
                return int(float(result.stdout.decode().strip()) * 1000)
        except Exception:
            pass
        return 0

    def _mark_finalization_failed(self, f_id: str, error: str) -> None:
        db = get_session_factory()()
        try:
            f = db.query(TrackFinalization).filter(TrackFinalization.id == f_id).first()
            if f:
                f.status = FinalizationStatus.failed
                f.error_message = error
                f.completed_at = datetime.now(timezone.utc)
                db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    def _mark_finalization_completed(self, f_id: str, output_path: str, video_id: str | None) -> None:
        db = get_session_factory()()
        try:
            f = db.query(TrackFinalization).filter(TrackFinalization.id == f_id).first()
            if f:
                f.status = FinalizationStatus.completed
                f.output_path = output_path
                f.video_id = video_id
                f.completed_at = datetime.now(timezone.utc)
                db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()
