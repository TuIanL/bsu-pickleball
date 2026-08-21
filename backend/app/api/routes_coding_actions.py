"""Coding Actions API routes —— 实时编码控制台的语义命令端点。"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.camera.capture_finalizer import get_merge_status
from app.camera.session_service import session_service
from app.camera.sync_recorder_service import sync_recording_service
from app.database import get_db
from app.models.field_session import FieldSession
from app.api.routes_segment_editing import _seg_dict
from app.schemas.capture_runtime_status import CaptureTakeRuntimeStatus
from app.schemas.coding_actions import (
    CaptureTakeSummary,
    CodingActionRequest,
    CodingActionResponse,
    LiveCodingStateResponse,
)
from app.schemas.sync_anchor import (
    SyncAnchorConfirmRequest,
    SyncAnchorDraftRequest,
    SyncAnchorError,
)
from app.services import capture_runtime_status_service, capture_take_service, coding_actions_service
from app.services.capture_track_service import get_tracks_for_take
from app.services.sync_anchor_service import (
    SyncAnchorAssetService,
    SyncAnchorConflictError,
    SyncAnchorNotFoundError,
    SyncAnchorValidationError,
)


def _ensure_utc(value: datetime | None) -> datetime | None:
    """确保 datetime 带 UTC 时区信息。"""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


from app.services import capture_segment_service as seg_svc  # noqa: E402
from app.services import live_coding_state_service as state_svc  # noqa: E402

router = APIRouter(prefix="/api/capture-takes", tags=["capture-takes"])


def _sync_anchor_error(
    status_code: int,
    code: str,
    message: str,
    *,
    current_revision: int | None = None,
    issues: list[object] | None = None,
) -> JSONResponse:
    payload = SyncAnchorError(
        code=code,
        message=message,
        current_revision=current_revision,
        issues=issues or [],
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump(mode="json"))


@router.get("/{capture_take_id}/sync-anchors/status")
def get_sync_anchor_status(
    capture_take_id: str,
    require_manual: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    try:
        return SyncAnchorAssetService(db).status(capture_take_id, require_manual=require_manual)
    except SyncAnchorNotFoundError as exc:
        return _sync_anchor_error(404, "capture_take_not_found", str(exc))


@router.get("/{capture_take_id}/sync-anchors/draft")
def get_sync_anchor_draft(capture_take_id: str, db: Session = Depends(get_db)):
    try:
        service = SyncAnchorAssetService(db)
        status = service.status(capture_take_id)
        if status.draft is None:
            return _sync_anchor_error(404, "draft_not_found", "当前 CaptureTake 没有同步锚点草稿")
        return {
            "capture_take_id": capture_take_id,
            "revision": status.revision,
            "draft": status.draft,
            "status": status,
        }
    except SyncAnchorNotFoundError as exc:
        return _sync_anchor_error(404, "capture_take_not_found", str(exc))


@router.put("/{capture_take_id}/sync-anchors/draft")
def put_sync_anchor_draft(
    capture_take_id: str,
    payload: SyncAnchorDraftRequest,
    db: Session = Depends(get_db),
):
    try:
        service = SyncAnchorAssetService(db)
        revision, status = service.save_draft(capture_take_id, payload)
        return {"capture_take_id": capture_take_id, "revision": revision, "draft": status.draft, "status": status}
    except SyncAnchorConflictError as exc:
        return _sync_anchor_error(409, "revision_conflict", str(exc), current_revision=exc.current_revision)
    except SyncAnchorNotFoundError as exc:
        return _sync_anchor_error(404, "capture_take_not_found", str(exc))


@router.post("/{capture_take_id}/sync-anchors/confirm")
def confirm_sync_anchors(
    capture_take_id: str,
    payload: SyncAnchorConfirmRequest,
    db: Session = Depends(get_db),
):
    try:
        return SyncAnchorAssetService(db).confirm(capture_take_id, payload)
    except SyncAnchorConflictError as exc:
        return _sync_anchor_error(409, "revision_conflict", str(exc), current_revision=exc.current_revision)
    except SyncAnchorValidationError as exc:
        return _sync_anchor_error(
            422,
            "validation_failed",
            str(exc),
            issues=[issue.model_dump(mode="json") for issue in exc.issues],
        )
    except SyncAnchorNotFoundError as exc:
        return _sync_anchor_error(404, "capture_take_not_found", str(exc))


@router.get("/{capture_take_id}/sync-anchors/export")
def export_sync_anchors(capture_take_id: str, db: Session = Depends(get_db)):
    try:
        return SyncAnchorAssetService(db).export(capture_take_id)
    except SyncAnchorNotFoundError as exc:
        return _sync_anchor_error(404, "anchors_not_found", str(exc))


@router.get("/active")
def get_active_capture_take(db: Session = Depends(get_db)):
    """查询当前活跃录制（状态为 starting 或 recording），全局最多一个。"""
    take = capture_take_service.get_active_capture_take(db)
    if take is None:
        return None

    fs = db.query(FieldSession).filter(FieldSession.id == take.field_session_id).first()
    started = _ensure_utc(take.started_at)
    server_now = datetime.now(UTC)

    return {
        "takeId": take.id,
        "fieldSessionId": take.field_session_id,
        "captureTakeId": take.id,
        "sourceSessionId": take.source_session_id,
        "sourceSessionType": take.source_session_type.value,
        "startedAt": started.isoformat() if started else None,
        "serverNow": server_now.isoformat(),
        "status": take.status.value,
        "title": fs.title if fs else None,
        "courtName": fs.court_name if fs else None,
        "captureMode": take.capture_mode.value,
        "videoSpec": None,
    }


@router.post("/active/force-finalize")
def force_finalize_active_capture_take(db: Session = Depends(get_db)):
    """强制终态化当前活跃 CaptureTake（用于孤儿录制无法通过正常 cancel/stop 清理时）。"""
    take = capture_take_service.get_active_capture_take(db)
    if take is None:
        return {"ok": True, "detail": "无活跃录制，无需清理"}

    take_id = take.id
    source_session_id = take.source_session_id
    source_session_type = take.source_session_type.value

    capture_take_service.finalize_capture_take(db, take_id, "failed")
    db.commit()

    # 尝试清理 source session（best-effort，孤儿 session 可能已不存在）
    try:
        if source_session_type == "sync_recording":
            from app.camera.sync_recorder_service import sync_recording_service

            try:
                sync_recording_service.cancel_session(source_session_id)
            except Exception:
                pass
        else:
            from app.camera.session_service import session_service

            try:
                session_service.cancel_session(source_session_id)
            except Exception:
                pass
    except Exception:
        pass

    return {"ok": True, "detail": f"已强制终止录制 {take_id}"}


@router.post("/{capture_take_id}/coding-actions", response_model=CodingActionResponse)
def execute_action(
    capture_take_id: str,
    request: CodingActionRequest,
    db: Session = Depends(get_db),
) -> CodingActionResponse:
    """执行编码动作（开始/结束集、局、回合等），验证 revision 并生成时间轴快照。"""
    try:
        result = coding_actions_service.execute_coding_action(
            db,
            capture_take_id=capture_take_id,
            action=request.action,
            client_action_id=request.client_action_id,
            expected_revision=request.expected_revision,
            timestamp_ms=request.timestamp_ms or 0,
            payload=request.payload,
        )
    except ValueError as exc:
        msg = str(exc)
        if "duplicate_action_mismatched_payload" in msg:
            raise HTTPException(status_code=409, detail="客户动作 ID 重复但 payload 不匹配") from exc
        if "revision_conflict" in msg:
            raise HTTPException(status_code=409, detail="revision 冲突") from exc
        if "不在录制中" in msg:
            raise HTTPException(status_code=400, detail=msg) from exc
        raise HTTPException(status_code=400, detail=msg) from exc

    if "error" in result:
        raise HTTPException(
            status_code=409,
            detail={
                "error": result["error"],
                "current_revision": result["current_revision"],
                "live_state": result["live_state"],
            },
        )

    from app.services.capture_archive_service import snapshot_capture_timeline

    snapshot_capture_timeline(db, capture_take_id)

    return CodingActionResponse(**result)


@router.get("/{capture_take_id}/live-state", response_model=LiveCodingStateResponse)
def get_live_state(
    capture_take_id: str,
    db: Session = Depends(get_db),
) -> LiveCodingStateResponse:
    """获取指定录制的最新实时编码状态（revision、集/局/回合序号等）。"""
    state = state_svc.get_state(db, capture_take_id)
    if state is None:
        raise HTTPException(status_code=404, detail="LiveCodingState 不存在")
    return LiveCodingStateResponse(
        capture_take_id=state.capture_take_id,
        revision=state.revision,
        set_ordinal=state.set_ordinal,
        game_ordinal=state.game_ordinal,
        rally_ordinal=state.rally_ordinal,
        non_play=state.non_play,
        match_phase=getattr(state, "match_phase", "intermission" if state.non_play else "idle"),
        intermission_kind=getattr(state, "intermission_kind", None),
        current_set_segment_id=state.current_set_segment_id,
        current_game_segment_id=state.current_game_segment_id,
        current_rally_segment_id=state.current_rally_segment_id,
        server_team=getattr(state, "server_team", None),
        score_a=getattr(state, "score_a", 0),
        score_b=getattr(state, "score_b", 0),
        scoring_mode=getattr(state, "scoring_mode", "none"),
        scoring_ruleset_version=getattr(state, "scoring_ruleset_version", None),
        recent_results=json.loads(state.recent_results)
        if isinstance(state.recent_results, str)
        else (state.recent_results or []),
        games_won_a=getattr(state, "games_won_a", 0),
        games_won_b=getattr(state, "games_won_b", 0),
        scoring_phase=getattr(state, "scoring_phase", "rally"),
        serving_side=getattr(state, "serving_side", None),
        match_status=getattr(state, "match_status", "not_started"),
        match_winner=getattr(state, "match_winner", None),
    )


@router.get("/{capture_take_id}", response_model=CaptureTakeSummary)
def get_capture_take_detail(
    capture_take_id: str,
    db: Session = Depends(get_db),
) -> CaptureTakeSummary:
    """获取录制摘要信息（模式、来源、状态、时长、revision 等）。"""
    take = capture_take_service.get_capture_take(db, capture_take_id)
    if take is None:
        raise HTTPException(status_code=404, detail="CaptureTake 不存在")
    started = _ensure_utc(take.started_at)
    ended = _ensure_utc(take.ended_at)
    try:
        sync_anchor_status = SyncAnchorAssetService(db).status(take.id)
    except SyncAnchorNotFoundError:
        sync_anchor_status = None
    # 可播放视频源：优先取已注册 video_id 的轨道（按机位 cam_1→cam_2 排序）。
    # 轨道无 video_id（legacy/测试 take）时回退到来源会话的已注册视频，保证仍可播放。
    slot_order = {"cam_1": 0, "cam_2": 1}
    video_ids = [
        track.video_id
        for track in sorted(
            get_tracks_for_take(db, take.id),
            key=lambda t: slot_order.get(t.slot.value, 99),
        )
        if track.video_id
    ]
    if not video_ids:
        if take.source_session_type.value == "sync_recording":
            sync = sync_recording_service.get_session(take.source_session_id)
            if sync is not None:
                video_ids = [
                    v
                    for v in (
                        sync.registered_video_ids.get("cam_1"),
                        sync.registered_video_ids.get("cam_2"),
                        sync.default_analysis_video_id,
                    )
                    if v
                ]
        else:
            rec = session_service.get_session(take.source_session_id)
            if rec is not None and rec.video_id:
                video_ids = [rec.video_id]
    return CaptureTakeSummary(
        id=take.id,
        field_session_id=take.field_session_id,
        capture_mode=take.capture_mode.value,
        display_mode=getattr(
            getattr(take, "display_mode", "standard"),
            "value",
            getattr(take, "display_mode", "standard"),
        ),
        source_session_type=take.source_session_type.value,
        source_session_id=take.source_session_id,
        status=take.status.value,
        started_at=started.isoformat() if started else "",
        ended_at=ended.isoformat() if ended else None,
        duration_ms=take.duration_ms,
        revision=take.revision,
        sync_anchor_status=sync_anchor_status,
        video_ids=video_ids,
    )


@router.get("/{capture_take_id}/finalization-status")
def get_finalization_status(capture_take_id: str):
    """查询后台合并进度。"""
    status = get_merge_status(capture_take_id)
    if status is None:
        return {"capture_take_id": capture_take_id, "status": "not_started"}
    return status


@router.get(
    "/{capture_take_id}/runtime-status",
    response_model=CaptureTakeRuntimeStatus,
)
def get_capture_take_runtime_status(
    capture_take_id: str,
    db: Session = Depends(get_db),
) -> CaptureTakeRuntimeStatus:
    """返回指定 CaptureTake 的运行状态快照，供录制工作台轮询消费。

    快照包含 storage / recording / tracks / sync / updated_at 五个区域，
    每个指标独立表达 ready/collecting/unavailable/error 可用性状态。

    安全边界：仅通过 CaptureTake 记录的会话目录解析存储信息，
    不接受任意客户端路径；CaptureTake 不存在时返回 404。
    """
    status = capture_runtime_status_service.get_capture_take_runtime_status(
        db,
        capture_take_id,
    )
    if status is None:
        raise HTTPException(status_code=404, detail="CaptureTake 不存在")
    return status


@router.get("/{capture_take_id}/segments")
def list_segments(
    capture_take_id: str,
    segment_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """列出录制下的所有分段（集/局/回合），可按 segment_type 过滤。"""
    segs = seg_svc.list_segments(db, capture_take_id, segment_type=segment_type)
    # 复用权威序列化器，暴露 edit_status/edit_version/corrected_*/effective_* 完整契约
    return [_seg_dict(s) for s in segs]
