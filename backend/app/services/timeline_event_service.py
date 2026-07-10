"""
Timeline Event 服务层 —— 创建、列表、读取、更新和删除 Session Timeline Events。
重构：内部方法不提交事务，外部 API 方法负责事务控制。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.timeline_event import (
    SessionTimelineEvent,
    TimelineEventType,
    TimelineEventSource,
)

_ID_PREFIX = "te"


def _generate_id() -> str:
    return f"{_ID_PREFIX}_{uuid4().hex[:12]}"


def _dump_payload_json(payload_json: object | None) -> str:
    if payload_json is None:
        return "{}"
    if isinstance(payload_json, str):
        return payload_json
    return json.dumps(payload_json, ensure_ascii=False)


# ── 内部方法（不提交事务，供 coding-actions 内部调用）──

def _add_timeline_event(
    db: Session,
    field_session_id: str,
    event_type: str,
    *,
    capture_take_id: str | None = None,
    recording_session_id: str | None = None,
    timestamp_ms: int = 0,
    source: str = "manual",
    label: str = "",
    note: str = "",
    payload_json: object | None = None,
) -> SessionTimelineEvent:
    now = datetime.now(timezone.utc)
    event = SessionTimelineEvent(
        id=_generate_id(),
        field_session_id=field_session_id,
        capture_take_id=capture_take_id,
        recording_session_id=recording_session_id,
        timestamp_ms=timestamp_ms,
        occurred_at=now,
        event_type=TimelineEventType(event_type),
        source=TimelineEventSource(source),
        label=label,
        note=note,
        payload_json=_dump_payload_json(payload_json),
        created_at=now,
        updated_at=now,
    )
    db.add(event)
    db.flush()
    return event


# ── 外部 API 方法（负责事务控制）──

def create_timeline_event(
    db: Session,
    field_session_id: str,
    payload: dict,
) -> SessionTimelineEvent:
    """创建 Session Timeline Event，校验 Field Session 存在、录制归属、时间戳策略。"""
    from app.services.field_session_service import get_field_session
    from app.camera.session_service import session_service

    fs = get_field_session(db, field_session_id)
    if fs is None:
        raise ValueError(f"Field Session {field_session_id} 不存在")

    recording_session_id = payload.get("recording_session_id")
    capture_take_id = payload.get("capture_take_id")

    if capture_take_id:
        from app.services.capture_take_service import get_capture_take
        take = get_capture_take(db, capture_take_id)
        if take is None:
            raise ValueError(f"CaptureTake {capture_take_id} 不存在")
        if take.field_session_id != field_session_id:
            raise ValueError(
                f"CaptureTake {capture_take_id} 不属于 Field Session {field_session_id}"
            )

    if recording_session_id:
        recording = session_service.get_session(recording_session_id)
        if recording is None:
            raise ValueError(f"RecordingSession {recording_session_id} 不存在")
        if recording.field_session_id != field_session_id:
            raise ValueError(
                f"RecordingSession {recording_session_id} 不属于 Field Session {field_session_id}"
            )

    timestamp_ms = payload.get("timestamp_ms")
    if timestamp_ms is None:
        if capture_take_id:
            from app.services.capture_take_service import get_capture_take
            take = get_capture_take(db, capture_take_id)
            if take and take.started_at:
                elapsed = (datetime.now(timezone.utc) - take.started_at).total_seconds()
                timestamp_ms = max(0, int(elapsed * 1000))
            else:
                timestamp_ms = 0
        elif recording_session_id:
            recording = session_service.get_session(recording_session_id)
            if recording and recording.started_at:
                elapsed = (datetime.now(timezone.utc) - recording.started_at).total_seconds()
                timestamp_ms = max(0, int(elapsed * 1000))
            else:
                timestamp_ms = 0
        else:
            timestamp_ms = 0

    event = _add_timeline_event(
        db,
        field_session_id=field_session_id,
        event_type=payload["event_type"],
        capture_take_id=capture_take_id,
        recording_session_id=recording_session_id,
        timestamp_ms=timestamp_ms,
        source=payload.get("source", "manual"),
        label=payload.get("label", ""),
        note=payload.get("note", ""),
        payload_json=payload.get("payload_json"),
    )
    db.commit()
    db.refresh(event)
    return event


def list_timeline_events(
    db: Session,
    field_session_id: str,
    event_type: str | None = None,
    source: str | None = None,
    recording_session_id: str | None = None,
    capture_take_id: str | None = None,
    from_ms: int | None = None,
    to_ms: int | None = None,
    include_undone: bool = False,
) -> list[SessionTimelineEvent]:
    q = db.query(SessionTimelineEvent).filter(
        SessionTimelineEvent.field_session_id == field_session_id
    )
    if not include_undone:
        q = q.filter(SessionTimelineEvent.is_undone == False)  # noqa: E712
    if event_type:
        try:
            q = q.filter(SessionTimelineEvent.event_type == TimelineEventType(event_type))
        except ValueError:
            pass
    if source:
        try:
            q = q.filter(SessionTimelineEvent.source == TimelineEventSource(source))
        except ValueError:
            pass
    if capture_take_id:
        q = q.filter(SessionTimelineEvent.capture_take_id == capture_take_id)
    if recording_session_id:
        q = q.filter(SessionTimelineEvent.recording_session_id == recording_session_id)
    if from_ms is not None:
        q = q.filter(SessionTimelineEvent.timestamp_ms >= from_ms)
    if to_ms is not None:
        q = q.filter(SessionTimelineEvent.timestamp_ms <= to_ms)
    return q.order_by(
        SessionTimelineEvent.timestamp_ms.asc(),
        SessionTimelineEvent.created_at.asc(),
    ).all()


def get_timeline_event(db: Session, event_id: str) -> SessionTimelineEvent | None:
    return db.query(SessionTimelineEvent).filter(SessionTimelineEvent.id == event_id).first()


def update_timeline_event(
    db: Session,
    event_id: str,
    payload: dict,
) -> SessionTimelineEvent | None:
    event = get_timeline_event(db, event_id)
    if event is None:
        return None

    updatable = ("timestamp_ms", "event_type", "source", "label", "note", "payload_json")
    for key in updatable:
        if key in payload and payload[key] is not None:
            if key == "event_type":
                value = TimelineEventType(payload[key])
            elif key == "source":
                value = TimelineEventSource(payload[key])
            elif key == "payload_json":
                value = _dump_payload_json(payload[key])
            else:
                value = payload[key]
            setattr(event, key, value)
    event.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(event)
    return event


def delete_timeline_event(db: Session, event_id: str) -> bool:
    event = get_timeline_event(db, event_id)
    if event is None:
        return False
    db.delete(event)
    db.commit()
    return True


def count_events_for_field_session(db: Session, field_session_id: str) -> int:
    return (
        db.query(SessionTimelineEvent)
        .filter(SessionTimelineEvent.field_session_id == field_session_id)
        .count()
    )
