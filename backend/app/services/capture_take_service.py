"""CaptureTake 服务层 —— CRUD、生命周期管理、旧数据适配。"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.capture_take import (
    CaptureTake,
    CaptureTakeStatus,
    CaptureMode,
    SourceSessionType,
)

# 采集 take ID 前缀
_ID_PREFIX = "ct"


# 生成带前缀的唯一 ID（ct_ + 12 位随机十六进制）
def _generate_id() -> str:
    return f"{_ID_PREFIX}_{uuid4().hex[:12]}"


def initialize_capture_take_timeline(db: Session, take: CaptureTake) -> None:
    """Create the initial non-play state/event for every recording take."""
    from app.services import live_coding_state_service, timeline_event_service

    live_coding_state_service.upsert_state(
        db,
        take.id,
        revision=0,
        set_ordinal=0,
        game_ordinal=0,
        rally_ordinal=0,
        non_play=True,
        match_phase="intermission",
        intermission_kind="between_rallies",
    )
    timeline_event_service._add_timeline_event(
        db,
        take.field_session_id,
        "non_play_start",
        capture_take_id=take.id,
        timestamp_ms=0,
        payload_json={"intermission_kind": "between_rallies"},
    )


# 创建一条采集 take 记录（初始状态为 recording）
def create_capture_take(
    db: Session,
    *,
    field_session_id: str,
    capture_mode: str,
    source_session_type: str,
    source_session_id: str,
    storage_root: str | None = None,
    session_dir: str | None = None,
) -> CaptureTake:
    now = datetime.now(timezone.utc)
    take = CaptureTake(
        id=_generate_id(),
        field_session_id=field_session_id,
        capture_mode=CaptureMode(capture_mode),
        source_session_type=SourceSessionType(source_session_type),
        source_session_id=source_session_id,
        storage_root=storage_root,
        session_dir=session_dir,
        status=CaptureTakeStatus.recording,
        started_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(take)
    db.flush()

    initialize_capture_take_timeline(db, take)
    return take


def set_capture_take_storage(
    db: Session,
    take_id: str,
    *,
    storage_root: str,
    session_dir: str,
    storage_status: str = "available",
) -> CaptureTake | None:
    take = get_capture_take(db, take_id)
    if take is None:
        return None
    take.storage_root = storage_root
    take.session_dir = session_dir
    take.storage_status = storage_status
    return take


# 按 ID 获取单条采集 take
def get_capture_take(db: Session, take_id: str) -> CaptureTake | None:
    return db.query(CaptureTake).filter(CaptureTake.id == take_id).first()


# 按来源会话类型与 ID 查找采集 take（用于去重/关联旧数据）
def get_capture_take_by_source(
    db: Session, source_session_type: str, source_session_id: str
) -> CaptureTake | None:
    return (
        db.query(CaptureTake)
        .filter(
            CaptureTake.source_session_type == SourceSessionType(source_session_type),
            CaptureTake.source_session_id == source_session_id,
        )
        .first()
    )


# 列出采集 take，可按场地会话或状态过滤，按开始时间降序
def list_capture_takes(
    db: Session,
    field_session_id: str | None = None,
    status: str | None = None,
) -> list[CaptureTake]:
    q = db.query(CaptureTake)
    if field_session_id:
        q = q.filter(CaptureTake.field_session_id == field_session_id)
    if status:
        try:
            q = q.filter(CaptureTake.status == CaptureTakeStatus(status))
        except ValueError:
            pass
    return q.order_by(CaptureTake.started_at.desc()).all()


# 将无时区信息的 datetime 补全为 UTC 时区
def _ensure_aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


# 完成采集 take：置为 completed 并计算时长
def complete_capture_take(db: Session, take_id: str) -> CaptureTake | None:
    take = get_capture_take(db, take_id)
    if take is None:
        return None
    now = datetime.now(timezone.utc)
    take.status = CaptureTakeStatus.completed
    take.ended_at = now
    if take.started_at:
        started = _ensure_aware(take.started_at)
        take.duration_ms = int((now - started).total_seconds() * 1000)
    take.updated_at = now
    db.flush()
    return take


# 标记采集 take 失败：置为 failed 并计算时长
def fail_capture_take(db: Session, take_id: str) -> CaptureTake | None:
    take = get_capture_take(db, take_id)
    if take is None:
        return None
    now = datetime.now(timezone.utc)
    take.status = CaptureTakeStatus.failed
    take.ended_at = now
    if take.started_at:
        started = _ensure_aware(take.started_at)
        take.duration_ms = int((now - started).total_seconds() * 1000)
    take.updated_at = now
    db.flush()
    return take


# 取消采集 take：置为 canceled 并计算时长
def cancel_capture_take(db: Session, take_id: str) -> CaptureTake | None:
    take = get_capture_take(db, take_id)
    if take is None:
        return None
    now = datetime.now(timezone.utc)
    take.status = CaptureTakeStatus.canceled
    take.ended_at = now
    if take.started_at:
        started = _ensure_aware(take.started_at)
        take.duration_ms = int((now - started).total_seconds() * 1000)
    take.updated_at = now
    db.flush()
    return take


# 归档采集 take：记录归档时间
def archive_capture_take(db: Session, take_id: str) -> CaptureTake | None:
    take = get_capture_take(db, take_id)
    if take is None:
        return None
    take.archived_at = datetime.now(timezone.utc)
    take.updated_at = datetime.now(timezone.utc)
    db.flush()
    return take


_TERMINAL_STATUSES = {
    CaptureTakeStatus.completed,
    CaptureTakeStatus.partial,
    CaptureTakeStatus.failed,
    CaptureTakeStatus.canceled,
}


def finalize_capture_take(
    db: Session,
    capture_take_id: str,
    terminal_status: str,
    ended_at: datetime | None = None,
    duration_ms: int | None = None,
) -> CaptureTake | None:
    """幂等终态化：已终态的 Take 再次调用不覆盖。"""
    take = get_capture_take(db, capture_take_id)
    if take is None:
        return None
    if take.status in _TERMINAL_STATUSES:
        return take

    now = ended_at or datetime.now(timezone.utc)
    try:
        take.status = CaptureTakeStatus(terminal_status)
    except ValueError:
        return None
    take.ended_at = now
    if duration_ms is not None:
        take.duration_ms = duration_ms
    elif take.started_at:
        started = _ensure_aware(take.started_at)
        take.duration_ms = int((now - started).total_seconds() * 1000)
    take.updated_at = datetime.now(timezone.utc)
    db.flush()
    return take


def adapt_from_recording_session(
    db: Session,
    recording_session_id: str,
    field_session_id: str,
    started_at: datetime | None = None,
) -> CaptureTake:
    """从旧 RecordingSession 适配创建 CaptureTake（渐进迁移）。"""
    existing = get_capture_take_by_source(db, "recording", recording_session_id)
    if existing:
        return existing
    now = datetime.now(timezone.utc)
    take = CaptureTake(
        id=_generate_id(),
        field_session_id=field_session_id,
        capture_mode=CaptureMode.single,
        source_session_type=SourceSessionType.recording,
        source_session_id=recording_session_id,
        status=CaptureTakeStatus.recording,
        started_at=started_at or now,
        created_at=now,
        updated_at=now,
    )
    db.add(take)
    db.flush()
    return take
