"""录制控制 API 路由。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.camera.models import RecordingSession, RecordingStartRequest
from app.camera.recorder import check_ffmpeg_available
from app.camera.session_service import session_service

router = APIRouter(prefix="/api/recordings", tags=["recordings"])


def _check_ffmpeg() -> None:
    if not check_ffmpeg_available():
        raise HTTPException(
            status_code=503,
            detail="FFmpeg 不可用，录制功能暂时无法使用。请安装 FFmpeg 后重试。",
        )


@router.post("/start", response_model=RecordingSession, status_code=201)
def start_recording(payload: RecordingStartRequest) -> RecordingSession:
    _check_ffmpeg()
    try:
        return session_service.start_session(payload)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/{session_id}/stop", response_model=RecordingSession)
def stop_recording(session_id: str) -> RecordingSession:
    _check_ffmpeg()
    try:
        return session_service.stop_session(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{session_id}/cancel", response_model=RecordingSession)
def cancel_recording(session_id: str) -> RecordingSession:
    _check_ffmpeg()
    try:
        return session_service.cancel_session(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=list[RecordingSession])
def list_recordings(
    camera_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> list[RecordingSession]:
    return session_service.list_sessions(camera_id=camera_id, status=status)


@router.get("/{session_id}", response_model=RecordingSession)
def get_recording(session_id: str) -> RecordingSession:
    session = session_service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"录制会话 {session_id} 不存在")
    return session
