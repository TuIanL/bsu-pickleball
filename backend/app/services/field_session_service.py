"""
Field Session 服务层 —— 封装创建、列表、读取、更新和状态流转逻辑。
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.field_session import FieldSession, FieldSessionStatus, CaptureMode, MatchFormat, CameraSetup
from app.schemas.field_session import FieldSessionCreate, FieldSessionUpdate

# 前缀 + 时间戳生成可读 ID
_ID_PREFIX = "fs"


def _generate_id() -> str:
    return f"{_ID_PREFIX}_{uuid4().hex[:12]}"


# ---- 允许的状态流转 ----
_ALLOWED_TRANSITIONS: dict[FieldSessionStatus, set[FieldSessionStatus]] = {
    FieldSessionStatus.planned: {FieldSessionStatus.live, FieldSessionStatus.completed},
    FieldSessionStatus.live: {FieldSessionStatus.completed},
    FieldSessionStatus.completed: {FieldSessionStatus.archived},
    FieldSessionStatus.archived: set(),
}


def create_field_session(db: Session, payload: FieldSessionCreate) -> FieldSession:
    """创建 Field Session，状态默认为 planned。"""
    now = datetime.now(timezone.utc)
    session = FieldSession(
        id=_generate_id(),
        title=payload.title,
        venue=payload.venue,
        court_name=payload.court_name,
        capture_mode=CaptureMode(payload.capture_mode),
        match_format=MatchFormat(payload.match_format),
        camera_setup=CameraSetup(payload.camera_setup),
        status=FieldSessionStatus.planned,
        notes=payload.notes,
        created_at=now,
        updated_at=now,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def list_field_sessions(
    db: Session,
    status: str | None = None,
    capture_mode: str | None = None,
    match_format: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[FieldSession]:
    """列出 Field Session，支持按状态/模式/格式筛选，按创建时间倒序。"""
    q = db.query(FieldSession)
    if status:
        try:
            q = q.filter(FieldSession.status == FieldSessionStatus(status))
        except ValueError:
            pass
    if capture_mode:
        try:
            q = q.filter(FieldSession.capture_mode == CaptureMode(capture_mode))
        except ValueError:
            pass
    if match_format:
        try:
            q = q.filter(FieldSession.match_format == MatchFormat(match_format))
        except ValueError:
            pass
    return q.order_by(FieldSession.created_at.desc()).offset(offset).limit(limit).all()


def get_field_session(db: Session, field_session_id: str) -> FieldSession | None:
    """根据 ID 获取 Field Session。"""
    return db.query(FieldSession).filter(FieldSession.id == field_session_id).first()


def update_field_session(db: Session, field_session_id: str, payload: FieldSessionUpdate) -> FieldSession | None:
    """更新 Field Session 元数据（不改变状态）。"""
    fs = get_field_session(db, field_session_id)
    if fs is None:
        return None
    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if value is not None:
            if key == "capture_mode":
                value = CaptureMode(value)
            elif key == "match_format":
                value = MatchFormat(value)
            elif key == "camera_setup":
                value = CameraSetup(value)
            setattr(fs, key, value)
    fs.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(fs)
    return fs


def _transition(db: Session, field_session_id: str, target: FieldSessionStatus) -> FieldSession | None:
    """执行状态流转，校验合法性。"""
    fs = get_field_session(db, field_session_id)
    if fs is None:
        return None
    allowed = _ALLOWED_TRANSITIONS.get(fs.status, set())
    if target not in allowed:
        raise ValueError(f"不允许从 {fs.status.value} 流转到 {target.value}")

    fs.status = target
    now = datetime.now(timezone.utc)
    if target == FieldSessionStatus.live:
        fs.started_at = now
    if target == FieldSessionStatus.completed:
        fs.ended_at = now
        if fs.started_at is None:
            fs.started_at = now
    fs.updated_at = now
    db.commit()
    db.refresh(fs)
    return fs


def start_field_session(db: Session, field_session_id: str) -> FieldSession | None:
    return _transition(db, field_session_id, FieldSessionStatus.live)


def complete_field_session(db: Session, field_session_id: str) -> FieldSession | None:
    return _transition(db, field_session_id, FieldSessionStatus.completed)


def archive_field_session(db: Session, field_session_id: str) -> FieldSession | None:
    return _transition(db, field_session_id, FieldSessionStatus.archived)


def delete_field_session(db: Session, field_session_id: str, recording_count: int = 0) -> dict:
    fs = get_field_session(db, field_session_id)
    if fs is None:
        return {"id": field_session_id, "status": "not_found", "detail": "Field Session 不存在"}
    if fs.status == FieldSessionStatus.live:
        return {"id": field_session_id, "status": "blocked", "detail": "采集任务进行中，无法删除"}
    if recording_count > 0:
        return {
            "id": field_session_id,
            "status": "blocked",
            "detail": f"采集任务下已有 {recording_count} 条录制记录，无法删除",
        }

    db.delete(fs)
    db.commit()
    return {"id": field_session_id, "status": "deleted", "detail": "采集任务已删除"}
