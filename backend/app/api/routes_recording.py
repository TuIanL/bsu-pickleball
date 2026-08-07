"""
录制控制接口路由（/api/recordings）

本文件负责"录制会话"的控制，基于前面 routes_camera.py 里已登记的摄像头：
- 开始录制：把摄像头的视频流录成文件
- 停止录制：正常结束并保存
- 取消录制：放弃本次录制
- 查询：列出/查看录制会话

底层实现依赖外部工具 FFmpeg 来真正抓取并保存视频流。
"""

from __future__ import annotations

# Query：用于从网址的查询参数（形如 ?camera_id=xxx&status=done）里取可选的过滤条件
from fastapi import APIRouter, HTTPException, Query

# 检查当前系统是否安装了 FFmpeg 这个外部工具
from app.camera.ffmpeg_utils import check_ffmpeg_available
from app.camera.models import RecordingDeleteResult, RecordingSession, RecordingStartRequest

# 录制会话服务：真正管理录制生命周期（开始/停止/取消/查询）的对象
from app.camera.session_service import session_service

# 数据库会话工厂，用于停止时查询 CaptureTake
from app.database import get_session_factory
from app.schemas.capture_stop_result import CaptureStopResult, CaptureStopResultBuilder

# 创建路由表，前缀 /api/recordings
router = APIRouter(prefix="/api/recordings", tags=["recordings"])


def _check_ffmpeg() -> None:
    """
    前置检查：确认 FFmpeg 可用。

    所有录制接口都依赖 FFmpeg 这个外部程序。如果没装，录制根本无法工作。
    因此把检查统一抽成函数，在每个录制接口开头调用，避免重复写判断逻辑。
    """
    if not check_ffmpeg_available():
        # 503 表示"服务暂时不可用"——这里指录制所依赖的 FFmpeg 缺失
        raise HTTPException(
            status_code=503,
            detail="FFmpeg 不可用，录制功能暂时无法使用。请安装 FFmpeg 后重试。",
        )


@router.post("/start", response_model=RecordingSession, status_code=201)
def start_recording(payload: RecordingStartRequest) -> RecordingSession:
    """
    开始录制

    请求体里指定要录制的摄像头 id 等参数。可能的错误：
    - 摄像头不存在              → 404
    - 该摄像头已经在录制中      → 409（冲突）
    """
    # 先确认 FFmpeg 可用
    _check_ffmpeg()
    try:
        return session_service.start_session(payload)
    except ValueError as e:
        # 业务层用 ValueError 表示"找不到目标"（如摄像头不存在）
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        # 业务层用 RuntimeError 表示"状态冲突"（如已在录制）
        raise HTTPException(status_code=409, detail=str(e)) from e


@router.post("/{session_id}/stop", response_model=CaptureStopResult)
def stop_recording(session_id: str) -> CaptureStopResult:
    _check_ffmpeg()
    try:
        session = session_service.stop_session(session_id)
        take = None
        tid = getattr(session, "capture_take_id", None)
        if tid:
            db = get_session_factory()()
            try:
                from app.services.capture_take_service import get_capture_take

                take = get_capture_take(db, tid)
            finally:
                db.close()
        return CaptureStopResultBuilder.from_single_session(
            session,
            capture_take=take,
            video_id=getattr(session, "video_id", None),
            duration_ms=int((getattr(session, "duration_sec", 0) or 0) * 1000),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{session_id}/cancel", response_model=RecordingSession)
def cancel_recording(session_id: str) -> RecordingSession:
    """
    取消录制

    与"停止"的区别：取消通常表示放弃本次录制（不保留或标记为作废），
    而停止是正常收尾并保留文件。
    """
    _check_ffmpeg()
    try:
        return session_service.cancel_session(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("", response_model=list[RecordingSession])
def list_recordings(
    camera_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    field_session_id: str | None = Query(default=None),
) -> list[RecordingSession]:
    """
    列出录制会话

    支持三个可选过滤条件：
    - camera_id：只看某个摄像头的录制
    - status：按状态过滤（如 recording / done / failed）
    - field_session_id：只看某个 Field Session 下的录制
    """
    return session_service.list_sessions(camera_id=camera_id, status=status, field_session_id=field_session_id)


@router.get("/{session_id}", response_model=RecordingSession)
def get_recording(session_id: str) -> RecordingSession:
    """
    读取单个录制会话的详情
    """
    session = session_service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"录制会话 {session_id} 不存在")
    return session


@router.delete("/{session_id}", response_model=RecordingDeleteResult)
def delete_recording(session_id: str) -> RecordingDeleteResult:
    """
    删除录制会话

    只允许删除终态（completed / failed / canceled）的录制。
    正在录制中的会话返回 409。
    """
    result = session_service.delete_session(session_id)
    if result["status"] == "not_found":
        raise HTTPException(status_code=404, detail=result["detail"])
    if result["status"] == "blocked":
        raise HTTPException(status_code=409, detail=result["detail"])
    return RecordingDeleteResult(**result)
