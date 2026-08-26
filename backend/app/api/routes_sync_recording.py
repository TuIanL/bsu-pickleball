"""
双摄同步录制接口路由（/api/sync-recordings）

提供：
- 开始 / 停止 / 取消双摄同步录制
- 查询同步录制会话
- 双摄短录测试

底层依赖 sync_recorder_service 管理录制生命周期。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.camera.ffmpeg_utils import check_ffmpeg_available
from app.camera.models import (
    SessionDisplayUpdateRequest,
    SyncRecordingSession,
    SyncStartRequest,
    SyncTestRequest,
    SyncTestResult,
)
from app.camera.sync_recorder_service import sync_recording_service
from app.schemas.analysis import AnalysisDeleteResult
from app.schemas.capture_stop_result import CaptureStopResult, CaptureStopResultBuilder

router = APIRouter(prefix="/api/sync-recordings", tags=["sync-recordings"])


# 检查 FFmpeg 是否可用，不可用时抛出 503 异常
def _check_ffmpeg() -> None:
    if not check_ffmpeg_available():
        raise HTTPException(
            status_code=503,
            detail="FFmpeg 不可用，同步录制功能暂时无法使用。请安装 FFmpeg 后重试。",
        )


@router.post("/start", response_model=SyncRecordingSession, status_code=201)
def start_sync_recording(payload: SyncStartRequest) -> SyncRecordingSession:
    """
    开始双摄同步录制

    校验：
    - 两个摄像头不同
    - 两个摄像头都存在且未被占用（单摄或双摄）
    - FFmpeg 可用
    - Field Session 存在（若提供）

    成功后两路录制同步启动，开始写出 .ts 分段文件。
    """
    _check_ffmpeg()
    try:
        return sync_recording_service.start_session(payload)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@router.post("/{session_id}/stop", response_model=CaptureStopResult)
def stop_sync_recording(session_id: str) -> CaptureStopResult:
    """停止双摄同步录制并返回合并结果，含分析视频 ID 与警告信息。"""
    _check_ffmpeg()
    try:
        response = sync_recording_service.stop_session(session_id)
        session = response.session
        take = None
        tid = getattr(session, "capture_take_id", None)
        if tid:
            from app.database import get_session_factory
            from app.services.capture_take_service import get_capture_take

            db = get_session_factory()()
            try:
                take = get_capture_take(db, tid)
            finally:
                db.close()
        cam_slots = getattr(session, "camera_slots", {}) or {}
        for slot_name in ("cam_1", "cam_2"):
            slot_info = cam_slots.get(slot_name) if isinstance(cam_slots, dict) else getattr(cam_slots, slot_name, None)
            getattr(slot_info, "camera_id", None) if slot_info else None
        return CaptureStopResultBuilder.from_sync_session(
            session,
            capture_take=take,
            cam_1_video_id=getattr(response, "default_analysis_video_id", None),
            warnings=[] if response.analysis_available else [response.analysis_blocked_reason or "分析不可用"],
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{session_id}/cancel", response_model=SyncRecordingSession)
def cancel_sync_recording(session_id: str) -> SyncRecordingSession:
    """
    取消双摄同步录制

    与停止的区别：取消后不登记视频、不合并文件。
    """
    _check_ffmpeg()
    try:
        return sync_recording_service.cancel_session(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{session_id}/merge", response_model=SyncRecordingSession, status_code=202)
def merge_sync_recording(session_id: str) -> SyncRecordingSession:
    """提交双摄任务的两路 MP4 合并，后台执行且不阻塞请求。"""
    _check_ffmpeg()
    try:
        return sync_recording_service.request_merge(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@router.get("", response_model=list[SyncRecordingSession])
def list_sync_recordings(
    status: str | None = Query(default=None),
    field_session_id: str | None = Query(default=None),
) -> list[SyncRecordingSession]:
    """列出双摄同步录制会话，支持按 status / field_session_id 过滤"""
    return sync_recording_service.list_sessions(status=status, field_session_id=field_session_id)


@router.get("/active", response_model=SyncRecordingSession | None)
def get_active_sync_recording() -> SyncRecordingSession | None:
    """查询当前活跃的双摄同步录制会话（正在录制中）"""
    return sync_recording_service.get_active_session()


@router.get("/{session_id}", response_model=SyncRecordingSession)
def get_sync_recording(session_id: str) -> SyncRecordingSession:
    """读取单个双摄同步录制会话详情"""
    session = sync_recording_service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"同步录制会话 {session_id} 不存在")
    return session


@router.patch("/{session_id}", response_model=SyncRecordingSession)
def update_sync_recording_display(session_id: str, payload: SessionDisplayUpdateRequest) -> SyncRecordingSession:
    """更新双摄素材的用户自定义显示标题/日期（Library 卡片兜底真源；空值撤销覆盖）。"""
    session = sync_recording_service.update_display_metadata(
        session_id,
        display_title=payload.display_title,
        display_date=payload.display_date,
    )
    if session is None:
        raise HTTPException(status_code=404, detail=f"同步录制会话 {session_id} 不存在")
    return session


@router.post("/test", response_model=SyncTestResult)
def run_sync_test(payload: SyncTestRequest) -> SyncTestResult:
    """
    双摄短录测试

    对两个摄像头执行短时间（3~30秒）同步录制测试，提取首帧/尾帧，
    验证 RTSP 连通性、FFmpeg 可用性和输出文件完整性。
    测试结果不入正式录制列表。
    """
    _check_ffmpeg()
    try:
        return sync_recording_service.run_test(payload)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@router.delete("/{session_id}")
def delete_sync_recording(session_id: str) -> dict:
    """删除终态同步录制会话"""
    result = sync_recording_service.delete_session(session_id)
    if result["status"] == "not_found":
        raise HTTPException(status_code=404, detail=result["detail"])
    if result["status"] == "blocked":
        raise HTTPException(status_code=409, detail=result["detail"])
    return result


@router.delete("/{session_id}/analysis", response_model=list[AnalysisDeleteResult])
def delete_sync_recording_analysis(session_id: str) -> list[AnalysisDeleteResult]:
    """删除该双摄录制派生的所有分析任务及其本地产物（multiview Parent 级联 child + 单摄任务）。

    录制本身（session、双路视频、CaptureTake、同步校准）MUST 保留；活跃任务返回 `blocked`。
    """
    from app.services.mock_analysis import delete_analysis_by_recording_session

    session = sync_recording_service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="同步录制会话不存在")
    capture_take_id = getattr(session, "capture_take_id", None)
    return delete_analysis_by_recording_session(session_id, session_capture_take_id=capture_take_id)
