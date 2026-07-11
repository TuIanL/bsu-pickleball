"""CaptureCleanupService —— 统一的录制资源清理服务，单摄/双摄共用。"""
from __future__ import annotations

import logging
from pathlib import Path
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class CaptureCleanupService:
    """统一清理 CaptureTake 关联的全部资源。每一步幂等。"""

    def __init__(self, db_factory, lease_manager=None):
        self._db_factory = db_factory
        self._lease_manager = lease_manager

    def delete_take(
        self,
        capture_take_id: str,
        *,
        delete_media: bool = True,
        session_json_path: str | None = None,
        video_path: str | None = None,
        output_dir: str | None = None,
    ) -> dict:
        """级联删除 CaptureTake 及关联资源。"""
        db = self._db_factory()
        try:
            from app.models.capture_take import CaptureTake

            take = db.query(CaptureTake).filter(CaptureTake.id == capture_take_id).first()
            if take is None:
                return {"status": "not_found", "detail": "CaptureTake 不存在"}

            if take.status in ("recording", "starting"):
                return {"status": "blocked", "detail": "录制进行中，无法删除"}

            self._check_analysis_references(db, capture_take_id)

            self._delete_db_records(db, capture_take_id)

            take.deleted_at = datetime.now(timezone.utc)
            take.updated_at = datetime.now(timezone.utc)
            db.commit()

        except AnalysisReferenceError as exc:
            db.rollback()
            return {"status": "blocked", "detail": str(exc)}
        except Exception as exc:
            db.rollback()
            logger.warning("清理 DB 记录失败: %s", exc)
            return {"status": "error", "detail": str(exc)}
        finally:
            db.close()

        if delete_media:
            self._delete_media_files(video_path, output_dir)

        if session_json_path:
            self._delete_session_json(session_json_path)

        if self._lease_manager:
            try:
                self._lease_manager.release(capture_take_id)
            except Exception as exc:
                logger.warning("释放 Lease 失败: %s", exc)

        return {"status": "deleted", "detail": "录制资源已删除"}

    def _check_analysis_references(self, db, capture_take_id: str) -> None:
        from app.models.capture_track import CaptureTrack
        tracks = db.query(CaptureTrack).filter(
            CaptureTrack.capture_take_id == capture_take_id
        ).all()
        video_ids = [t.video_id for t in tracks if t.video_id]
        if not video_ids:
            return
        try:
            from app.models.analysis_job import AnalysisJob
            refs = db.query(AnalysisJob).filter(
                AnalysisJob.video_id.in_(video_ids),
                AnalysisJob.status.in_(["pending", "processing"]),
            ).count()
            if refs > 0:
                raise AnalysisReferenceError("视频被分析任务引用，无法删除")
        except ImportError:
            pass

    def _delete_db_records(self, db, capture_take_id: str) -> None:
        from app.models.timeline_event import SessionTimelineEvent
        from app.models.capture_track import CaptureTrack
        from app.models.capture_coding_action import CaptureCodingAction
        from app.models.capture_segment import CaptureSegment
        from app.models.track_timeline_span import TrackTimelineSpan
        from app.models.track_finalization import TrackFinalization
        from app.models.media_fragment import MediaFragment

        # 按外键依赖顺序删除
        db.query(SessionTimelineEvent).filter(
            SessionTimelineEvent.capture_take_id == capture_take_id
        ).delete()
        db.query(CaptureSegment).filter(
            CaptureSegment.capture_take_id == capture_take_id
        ).delete()
        db.query(CaptureCodingAction).filter(
            CaptureCodingAction.capture_take_id == capture_take_id
        ).delete()

        # TimelineSpan → Finalization → Fragment → Track
        track_ids = [t[0] for t in db.query(CaptureTrack.id).filter(
            CaptureTrack.capture_take_id == capture_take_id
        ).all()]
        for tid in track_ids:
            final_ids = [f[0] for f in db.query(TrackFinalization.id).filter(
                TrackFinalization.capture_track_id == tid
            ).all()]
            for fid in final_ids:
                db.query(TrackTimelineSpan).filter(
                    TrackTimelineSpan.track_finalization_id == fid
                ).delete()
            db.query(TrackFinalization).filter(
                TrackFinalization.capture_track_id == tid
            ).delete()
            db.query(MediaFragment).filter(
                MediaFragment.capture_track_id == tid
            ).delete()

        db.query(CaptureTrack).filter(
            CaptureTrack.capture_take_id == capture_take_id
        ).delete()

    def _delete_media_files(self, video_path: str | None, output_dir: str | None) -> None:
        import shutil
        import glob
        if output_dir:
            out = Path(output_dir)
            if out.exists():
                try:
                    # 删除 TS 片段 + concat manifest + 临时/最终 MP4
                    for pattern in ["*.ts", "*.concat.txt", "*.finalizing", "*.mp4"]:
                        for f in out.glob(pattern):
                            f.unlink(missing_ok=True)
                    shutil.rmtree(out, ignore_errors=True)
                except Exception as exc:
                    logger.warning("删除输出目录失败: %s", exc)
        if video_path:
            vp = Path(video_path)
            if vp.exists():
                try:
                    vp.unlink()
                except Exception as exc:
                    logger.warning("删除视频文件失败: %s", exc)

    def _delete_session_json(self, json_path: str) -> None:
        p = Path(json_path)
        if p.exists():
            try:
                p.unlink()
            except Exception as exc:
                logger.warning("删除 session JSON 失败: %s", exc)


class AnalysisReferenceError(RuntimeError):
    pass
