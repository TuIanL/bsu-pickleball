"""
Timeline Event API 路由 (/api/field-sessions/.../timeline-events 和 /api/timeline-events/...)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.timeline_event import (
    TimelineEventCreate,
    TimelineEventUpdate,
    TimelineEventSummary,
    TimelineEventDetail,
)
from app.services.timeline_event_service import (
    create_timeline_event,
    list_timeline_events,
    get_timeline_event,
    update_timeline_event,
    delete_timeline_event,
)
from app.services.field_session_service import get_field_session

router = APIRouter(tags=["timeline-events"])


@router.post(
    "/api/field-sessions/{field_session_id}/timeline-events",
    response_model=TimelineEventDetail,
    status_code=201,
)
def create(
    field_session_id: str,
    payload: TimelineEventCreate,
    db: Session = Depends(get_db),
) -> TimelineEventDetail:
    """在 Field Session 下创建时间线事件。"""
    # 校验 Field Session 存在
    fs = get_field_session(db, field_session_id)
    if fs is None:
        raise HTTPException(status_code=404, detail=f"Field Session {field_session_id} 不存在")

    try:
        event = create_timeline_event(
            db, field_session_id, payload.model_dump(exclude_none=False)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return TimelineEventDetail.model_validate(event)


@router.get(
    "/api/field-sessions/{field_session_id}/timeline-events",
    response_model=list[TimelineEventSummary],
)
def list_for_session(
    field_session_id: str,
    event_type: str | None = Query(default=None),
    source: str | None = Query(default=None),
    recording_session_id: str | None = Query(default=None),
    capture_take_id: str | None = Query(default=None),
    from_ms: int | None = Query(default=None),
    to_ms: int | None = Query(default=None),
    include_undone: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> list[TimelineEventSummary]:
    """列出 Field Session 下的事件，支持按类型/来源/时间范围筛选。"""
    fs = get_field_session(db, field_session_id)
    if fs is None:
        raise HTTPException(status_code=404, detail=f"Field Session {field_session_id} 不存在")

    events = list_timeline_events(
        db, field_session_id,
        event_type=event_type,
        source=source,
        recording_session_id=recording_session_id,
        capture_take_id=capture_take_id,
        from_ms=from_ms,
        to_ms=to_ms,
        include_undone=include_undone,
    )
    return [TimelineEventSummary.model_validate(e) for e in events]


@router.get(
    "/api/timeline-events/{event_id}",
    response_model=TimelineEventDetail,
)
def get_detail(event_id: str, db: Session = Depends(get_db)) -> TimelineEventDetail:
    """获取单个事件详情。"""
    event = get_timeline_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"Timeline Event {event_id} 不存在")
    return TimelineEventDetail.model_validate(event)


@router.patch(
    "/api/timeline-events/{event_id}",
    response_model=TimelineEventDetail,
)
def update(
    event_id: str,
    payload: TimelineEventUpdate,
    db: Session = Depends(get_db),
) -> TimelineEventDetail:
    """更新时间线事件的可编辑字段。不允许修改 field_session_id 归属。"""
    event = update_timeline_event(db, event_id, payload.model_dump(exclude_unset=True))
    if event is None:
        raise HTTPException(status_code=404, detail=f"Timeline Event {event_id} 不存在")
    return TimelineEventDetail.model_validate(event)


@router.delete(
    "/api/timeline-events/{event_id}",
    status_code=204,
    response_model=None,
)
def delete(event_id: str, db: Session = Depends(get_db)):
    """删除时间线事件。"""
    deleted = delete_timeline_event(db, event_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Timeline Event {event_id} 不存在")
