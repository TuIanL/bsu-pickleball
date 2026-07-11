"""
Field Session API 路由 (/api/field-sessions)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.field_session import (
    FieldSessionCreate,
    FieldSessionUpdate,
    FieldSessionSummary,
    FieldSessionDetail,
    FieldSessionDeleteResult,
)
from app.services.field_session_service import (
    create_field_session,
    list_field_sessions,
    get_field_session,
    update_field_session,
    start_field_session,
    complete_field_session,
    archive_field_session,
    delete_field_session,
)
from app.camera.session_service import session_service
from app.camera.sync_recorder_service import sync_recording_service
from app.models.field_session import FieldSessionStatus

router = APIRouter(prefix="/api/field-sessions", tags=["field-sessions"])


@router.post("", response_model=FieldSessionDetail, status_code=201)
def create(payload: FieldSessionCreate, db: Session = Depends(get_db)) -> FieldSessionDetail:
    """创建 Field Session"""
    return FieldSessionDetail.model_validate(create_field_session(db, payload))


@router.get("", response_model=list[FieldSessionSummary])
def list_all(
    status: str | None = Query(default=None),
    capture_mode: str | None = Query(default=None),
    match_format: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[FieldSessionSummary]:
    """列出 Field Session"""
    sessions = list_field_sessions(db, status=status, capture_mode=capture_mode, match_format=match_format, limit=limit, offset=offset)
    return [FieldSessionSummary.model_validate(s) for s in sessions]


@router.get("/{field_session_id}", response_model=FieldSessionDetail)
def get_detail(field_session_id: str, db: Session = Depends(get_db)) -> FieldSessionDetail:
    """获取 Field Session 详情"""
    fs = get_field_session(db, field_session_id)
    if fs is None:
        raise HTTPException(status_code=404, detail=f"Field Session {field_session_id} 不存在")
    return FieldSessionDetail.model_validate(fs)


@router.patch("/{field_session_id}", response_model=FieldSessionDetail)
def update(field_session_id: str, payload: FieldSessionUpdate, db: Session = Depends(get_db)) -> FieldSessionDetail:
    """更新 Field Session 元数据"""
    fs = update_field_session(db, field_session_id, payload)
    if fs is None:
        raise HTTPException(status_code=404, detail=f"Field Session {field_session_id} 不存在")
    return FieldSessionDetail.model_validate(fs)


@router.post("/{field_session_id}/start", response_model=FieldSessionDetail)
def start(field_session_id: str, db: Session = Depends(get_db)) -> FieldSessionDetail:
    """开始 Field Session (planned -> live)"""
    try:
        fs = start_field_session(db, field_session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if fs is None:
        raise HTTPException(status_code=404, detail=f"Field Session {field_session_id} 不存在")
    return FieldSessionDetail.model_validate(fs)


@router.post("/{field_session_id}/complete", response_model=FieldSessionDetail)
def complete(field_session_id: str, db: Session = Depends(get_db)) -> FieldSessionDetail:
    """完成 Field Session (planned/live -> completed)"""
    try:
        fs = complete_field_session(db, field_session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if fs is None:
        raise HTTPException(status_code=404, detail=f"Field Session {field_session_id} 不存在")
    return FieldSessionDetail.model_validate(fs)


@router.post("/{field_session_id}/archive", response_model=FieldSessionDetail)
def archive(field_session_id: str, db: Session = Depends(get_db)) -> FieldSessionDetail:
    """归档 Field Session (completed -> archived)"""
    try:
        fs = archive_field_session(db, field_session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if fs is None:
        raise HTTPException(status_code=404, detail=f"Field Session {field_session_id} 不存在")
    return FieldSessionDetail.model_validate(fs)


@router.delete("/{field_session_id}", response_model=FieldSessionDeleteResult)
def delete(field_session_id: str, db: Session = Depends(get_db)) -> FieldSessionDeleteResult:
    """删除 Field Session。有视频的录制会被保护，无视频的孤立数据将级联清理。"""
    from app.models.field_session import FieldSession
    from pathlib import Path

    fs = db.query(FieldSession).filter(FieldSession.id == field_session_id).first()
    if fs is None:
        raise HTTPException(status_code=404, detail=f"Field Session {field_session_id} 不存在")
    if fs.status == FieldSessionStatus.live:
        raise HTTPException(status_code=409, detail="采集任务进行中，无法删除")

    # 收集关联录制
    recordings = session_service.list_sessions(field_session_id=field_session_id)
    sync_recordings = sync_recording_service.list_sessions(field_session_id=field_session_id)

    # 检查是否存在有视频的录制
    has_video = any(
        r.video_id or (r.video_path and Path(r.video_path).exists())
        for r in recordings
    ) or any(
        s.registered_video_ids
        for s in sync_recordings
    )

    if has_video:
        raise HTTPException(
            status_code=409,
            detail="采集任务下存在已录制视频，请先删除视频再删除任务",
        )

    # 无视频 → 级联删除
    from app.services.field_session_service import cascade_delete_field_session
    cascade_delete_field_session(db, field_session_id, recordings, sync_recordings)

    return FieldSessionDeleteResult(
        id=field_session_id, status="deleted", detail="采集任务已删除"
    )
