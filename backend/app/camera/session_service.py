"""录制会话生命周期管理 —— 开始/停止/取消录制，持久化 session metadata。"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from app.camera.camera_registry import camera_registry
from app.camera.models import RecordingSession, RecordingStartRequest
from app.camera.recorder import Recorder, check_ffmpeg_available
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)

SESSIONS: dict[str, RecordingSession] = {}
_RECORDER = Recorder()
_ACTIVE_CAMERA: str | None = None
_ACTIVE_SESSION_ID: str | None = None


class SessionService:
    def __init__(self, storage: StorageService | None = None) -> None:
        self._storage = storage or StorageService()

    @property
    def sessions_dir(self) -> Path:
        return Path("data/recordings/sessions")

    @property
    def recordings_dir(self) -> Path:
        return Path("data/recordings")

    def _session_path(self, session_id: str) -> Path:
        return self.sessions_dir / f"{session_id}.json"

    def _generate_session_id(self) -> str:
        now = datetime.now(timezone.utc)
        return f"rec_{now.strftime('%Y%m%d_%H%M%S')}"

    def _output_path(self, session_id: str, camera_id: str) -> Path:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self.recordings_dir / date_str / camera_id / f"{session_id}.mp4"

    def find_active_session(self, camera_id: str) -> RecordingSession | None:
        global _ACTIVE_CAMERA, _ACTIVE_SESSION_ID
        if _ACTIVE_CAMERA == camera_id and _ACTIVE_SESSION_ID:
            return SESSIONS.get(_ACTIVE_SESSION_ID)
        return None

    def start_session(self, request: RecordingStartRequest) -> RecordingSession:
        global _ACTIVE_CAMERA, _ACTIVE_SESSION_ID

        if not check_ffmpeg_available():
            raise RuntimeError("FFmpeg 不可用，无法开始录制")

        camera = camera_registry.get(request.camera_id)
        if camera is None:
            raise ValueError(f"摄像头 {request.camera_id} 不存在")

        if self.find_active_session(request.camera_id) is not None:
            raise RuntimeError(f"摄像头 {request.camera_id} 正在录制中")

        session_id = self._generate_session_id()
        output_path = self._output_path(session_id, request.camera_id)

        session = RecordingSession(
            session_id=session_id,
            camera_id=request.camera_id,
            court_name=request.court_name,
            match_format=request.match_format,
            camera_angle=request.camera_angle,
            fps=request.fps,
            resolution=request.resolution,
            auto_analyze_after_stop=request.auto_analyze_after_stop,
            status="recording",
            started_at=datetime.now(timezone.utc),
        )

        _RECORDER.start(
            stream_url=camera.stream_url,
            output_path=output_path,
            username=camera.username,
            password=camera.password,
            fps=request.fps,
            resolution=request.resolution,
            on_exit=lambda code: self._on_recorder_exit(session_id, code),
        )

        _ACTIVE_CAMERA = request.camera_id
        _ACTIVE_SESSION_ID = session_id
        SESSIONS[session_id] = session
        self._persist(session)

        logger.info("录制会话已开始: %s (camera=%s)", session_id, request.camera_id)
        return session

    def stop_session(self, session_id: str) -> RecordingSession:
        session = SESSIONS.get(session_id)
        if session is None:
            session = self._load(session_id)
            if session is None:
                raise ValueError(f"录制会话 {session_id} 不存在")

        if session.status != "recording":
            raise RuntimeError(f"录制会话 {session_id} 状态为 {session.status}，无法停止")

        _RECORDER.stop()
        stopped_at = datetime.now(timezone.utc)
        duration = (stopped_at - session.started_at).total_seconds()

        output_path = self._output_path(session_id, session.camera_id)

        video_id = None
        if output_path.exists():
            try:
                from app.services.video_service import video_service, SUPPORTED_VIDEO_SUFFIXES
                from app.schemas.video import VideoMetadata

                file_size = output_path.stat().st_size
                suffix = output_path.suffix.lower()
                if suffix in SUPPORTED_VIDEO_SUFFIXES:
                    suffix = suffix
                else:
                    suffix = ".mp4"

                video_id = video_service.register_recording(
                    file_path=output_path,
                    original_filename=output_path.name,
                    file_size=file_size,
                )
            except Exception as exc:
                logger.error("注册录制视频到 VideoService 失败: %s", exc)

        job_id = None
        if session.auto_analyze_after_stop and video_id:
            try:
                job_id = self._trigger_analysis(session, video_id)
            except Exception as exc:
                logger.error("自动创建分析任务失败: %s", exc)

        session = session.model_copy(update={
            "status": "completed",
            "stopped_at": stopped_at,
            "duration_sec": duration,
            "video_path": str(output_path) if output_path.exists() else None,
            "video_id": video_id,
            "auto_analysis_job_id": job_id,
        })

        SESSIONS[session_id] = session
        self._persist(session)
        self._clear_active(session.camera_id)

        logger.info("录制会话已停止: %s (duration=%.1fs)", session_id, duration)
        return session

    def cancel_session(self, session_id: str) -> RecordingSession:
        session = SESSIONS.get(session_id)
        if session is None:
            session = self._load(session_id)
            if session is None:
                raise ValueError(f"录制会话 {session_id} 不存在")

        if session.status != "recording":
            raise RuntimeError(f"录制会话 {session_id} 状态为 {session.status}，无法取消")

        _RECORDER.cancel()
        stopped_at = datetime.now(timezone.utc)
        duration = (stopped_at - session.started_at).total_seconds()

        output_path = self._output_path(session_id, session.camera_id)
        if output_path.exists():
            try:
                output_path.unlink()
            except Exception as exc:
                logger.warning("删除部分录制文件失败: %s", exc)

        session = session.model_copy(update={
            "status": "canceled",
            "stopped_at": stopped_at,
            "duration_sec": duration,
        })

        SESSIONS[session_id] = session
        self._persist(session)
        self._clear_active(session.camera_id)

        logger.info("录制会话已取消: %s", session_id)
        return session

    def get_session(self, session_id: str) -> RecordingSession | None:
        cached = SESSIONS.get(session_id)
        if cached is not None:
            return cached
        return self._load(session_id)

    def list_sessions(self, camera_id: str | None = None, status: str | None = None) -> list[RecordingSession]:
        result: list[RecordingSession] = []

        if self.sessions_dir.exists():
            for path in sorted(self.sessions_dir.glob("*.json"), reverse=True):
                try:
                    session = RecordingSession.model_validate(self._storage.read_json(path))
                    SESSIONS[session.session_id] = session
                    if camera_id and session.camera_id != camera_id:
                        continue
                    if status and session.status != status:
                        continue
                    result.append(session)
                except Exception:
                    pass

        return result

    def _on_recorder_exit(self, session_id: str, returncode: int) -> None:
        session = SESSIONS.get(session_id)
        if session is None or session.status != "recording":
            return

        if returncode != 0:
            logger.error("录制会话 %s FFmpeg 异常退出, returncode=%d", session_id, returncode)
            session = session.model_copy(update={
                "status": "failed",
                "stopped_at": datetime.now(timezone.utc),
                "duration_sec": (datetime.now(timezone.utc) - session.started_at).total_seconds(),
                "error_message": f"FFmpeg 进程异常退出, returncode={returncode}",
            })
            SESSIONS[session_id] = session
            self._persist(session)
            self._clear_active(session.camera_id)

    def _clear_active(self, camera_id: str) -> None:
        global _ACTIVE_CAMERA, _ACTIVE_SESSION_ID
        if _ACTIVE_CAMERA == camera_id:
            _ACTIVE_CAMERA = None
            _ACTIVE_SESSION_ID = None

    def _persist(self, session: RecordingSession) -> None:
        self._storage.write_json(self._session_path(session.session_id), session.model_dump(mode="json"))

    def _load(self, session_id: str) -> RecordingSession | None:
        path = self._session_path(session_id)
        if not path.exists():
            return None
        try:
            return RecordingSession.model_validate(self._storage.read_json(path))
        except Exception:
            return None

    def _trigger_analysis(self, session: RecordingSession, video_id: str) -> str | None:
        from app.schemas.analysis import AnalysisJobCreate, AnalysisUploadMetadata
        from app.services.mock_analysis import create_analysis_job

        metadata = AnalysisUploadMetadata(
            fileName=session.session_id + ".mp4",
            matchTitle=f"{session.court_name} {session.started_at.strftime('%Y-%m-%d %H:%M')}",
            venue=session.court_name,
            matchDate=session.started_at.strftime("%Y-%m-%d"),
            matchFormat=session.match_format,
            cameraAngle=_map_camera_angle(session.camera_angle),
            athleteLabel="",
            level="",
        )

        job = create_analysis_job(AnalysisJobCreate(
            metadata=metadata,
            videoId=video_id,
            frameStride=1,
        ))

        return job.id


def _map_camera_angle(angle: str) -> str:
    mapping = {
        "baseline_high": "elevated",
        "baseline": "baseline",
        "sideline": "sideline",
        "elevated": "elevated",
        "overhead": "elevated",
        "side": "sideline",
    }
    return mapping.get(angle, "unknown")


session_service = SessionService()
