"""Coding Actions API routes —— 实时编码控制台的语义命令端点。"""

from __future__ import annotations

import json
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.coding_actions import (
    CodingActionRequest,
    CodingActionResponse,
    LiveCodingStateResponse,
    CaptureTakeSummary,
)
from app.services import coding_actions_service
from app.services import capture_take_service
from app.services import live_coding_state_service as state_svc
from app.services import capture_segment_service as seg_svc

router = APIRouter(prefix="/api/capture-takes", tags=["capture-takes"])


@router.post("/{capture_take_id}/coding-actions", response_model=CodingActionResponse)
def execute_action(
    capture_take_id: str,
    request: CodingActionRequest,
    db: Session = Depends(get_db),
) -> CodingActionResponse:
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
            raise HTTPException(status_code=409, detail="客户动作 ID 重复但 payload 不匹配")
        if "revision_conflict" in msg:
            raise HTTPException(status_code=409, detail="revision 冲突")
        if "不在录制中" in msg:
            raise HTTPException(status_code=400, detail=msg)
        raise HTTPException(status_code=400, detail=msg)

    if "error" in result:
        raise HTTPException(status_code=409, detail={
            "error": result["error"],
            "current_revision": result["current_revision"],
            "live_state": result["live_state"],
        })

    from app.services.capture_archive_service import snapshot_capture_timeline
    snapshot_capture_timeline(db, capture_take_id)

    return CodingActionResponse(**result)


@router.get("/{capture_take_id}/live-state", response_model=LiveCodingStateResponse)
def get_live_state(
    capture_take_id: str,
    db: Session = Depends(get_db),
) -> LiveCodingStateResponse:
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
    )


@router.get("/{capture_take_id}", response_model=CaptureTakeSummary)
def get_capture_take_detail(
    capture_take_id: str,
    db: Session = Depends(get_db),
) -> CaptureTakeSummary:
    take = capture_take_service.get_capture_take(db, capture_take_id)
    if take is None:
        raise HTTPException(status_code=404, detail="CaptureTake 不存在")
    return CaptureTakeSummary(
        id=take.id,
        field_session_id=take.field_session_id,
        capture_mode=take.capture_mode.value,
        source_session_type=take.source_session_type.value,
        source_session_id=take.source_session_id,
        status=take.status.value,
        started_at=take.started_at.isoformat() if take.started_at else "",
        ended_at=take.ended_at.isoformat() if take.ended_at else None,
        duration_ms=take.duration_ms,
        revision=take.revision,
    )


@router.get("/{capture_take_id}/segments")
def list_segments(
    capture_take_id: str,
    segment_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    segs = seg_svc.list_segments(db, capture_take_id, segment_type=segment_type)
    return [
        {
            "id": s.id, "segment_type": s.segment_type.value,
            "ordinal": s.ordinal, "label": s.label,
            "start_ms": s.start_ms, "end_ms": s.end_ms,
            "status": s.status.value, "source": s.source.value,
            "is_highlight": s.is_highlight,
            "parent_segment_id": s.parent_segment_id,
        }
        for s in segs
    ]
