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

from app.camera.models import RecordingSession, RecordingStartRequest
# 检查当前系统是否安装了 FFmpeg 这个外部工具
from app.camera.recorder import check_ffmpeg_available
# 录制会话服务：真正管理录制生命周期（开始/停止/取消/查询）的对象
from app.camera.session_service import session_service

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
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        # 业务层用 RuntimeError 表示"状态冲突"（如已在录制）
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/{session_id}/stop", response_model=RecordingSession)
def stop_recording(session_id: str) -> RecordingSession:
    """
    停止录制

    正常结束录制并保存文件。可能的错误：
    - 会话不存在          → 404
    - 当前状态不允许停止  → 400（请求有误）
    """
    _check_ffmpeg()
    try:
        return session_service.stop_session(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


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
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=list[RecordingSession])
def list_recordings(
    camera_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> list[RecordingSession]:
    """
    列出录制会话

    支持两个可选过滤条件：
    - camera_id：只看某个摄像头的录制
    - status：按状态过滤（如 recording / done / failed）
    两个都不传则返回全部录制会话。
    """
    return session_service.list_sessions(camera_id=camera_id, status=status)


@router.get("/{session_id}", response_model=RecordingSession)
def get_recording(session_id: str) -> RecordingSession:
    """
    读取单个录制会话的详情
    """
    session = session_service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"录制会话 {session_id} 不存在")
    return session
