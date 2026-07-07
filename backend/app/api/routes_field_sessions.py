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
    """删除空的 Field Session。已有录制或进行中的任务会被保护。"""
    recording_count = len(session_service.list_sessions(field_session_id=field_session_id))
    result = delete_field_session(db, field_session_id, recording_count=recording_count)
    if result["status"] == "not_found":
        raise HTTPException(status_code=404, detail=result["detail"])
    if result["status"] == "blocked":
        raise HTTPException(status_code=409, detail=result["detail"])
    return FieldSessionDeleteResult(**result)
