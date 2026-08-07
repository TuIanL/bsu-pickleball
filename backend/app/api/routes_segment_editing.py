"""Segment 编辑 & AnalysisBatch API routes。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import analysis_batch_service, segment_edit_service
from app.services.capture_segment_service import get_segment
from app.services.capture_take_service import get_capture_take

router = APIRouter(prefix="/api/capture-segments", tags=["segment-editing"])

# ── Segment PATCH ──


@router.patch("/{segment_id}")
def patch_segment(
    segment_id: str,
    label: str | None = None,
    corrected_start_ms: int | None = None,
    corrected_end_ms: int | None = None,
    is_highlight: bool | None = None,
    expected_version: int | None = None,
    db: Session = Depends(get_db),
):
    seg = get_segment(db, segment_id)
    if seg is None:
        raise HTTPException(404, "Segment 不存在")
    try:
        seg = segment_edit_service.patch_segment(
            db,
            seg,
            label=label,
            corrected_start_ms=corrected_start_ms,
            corrected_end_ms=corrected_end_ms,
            is_highlight=is_highlight,
            expected_version=expected_version,
        )
        db.commit()
    except ValueError as e:
        db.rollback()
        msg = str(e)
        if "edit_version 冲突" in msg:
            raise HTTPException(409, msg) from e
        raise HTTPException(400, msg) from e
    return _seg_dict(seg)


@router.post("/{segment_id}/reset-boundary-correction")
def reset_boundary(segment_id: str, db: Session = Depends(get_db)):
    seg = get_segment(db, segment_id)
    if seg is None:
        raise HTTPException(404, "Segment 不存在")
    seg = segment_edit_service.reset_boundary(db, seg)
    db.commit()
    return _seg_dict(seg)


# ── Split / Merge ──


@router.post("/{segment_id}/split")
def split_segment(segment_id: str, split_ms: int, db: Session = Depends(get_db)):
    seg = get_segment(db, segment_id)
    if seg is None:
        raise HTTPException(404, "Segment 不存在")
    try:
        a, b = segment_edit_service.split_rally(db, seg, split_ms=split_ms)
        db.commit()
    except ValueError as e:
        db.rollback()
        raise HTTPException(400, str(e)) from e
    return {"segments": [_seg_dict(a), _seg_dict(b)]}


@router.post("/merge")
def merge_segments(segment_ids: list[str], db: Session = Depends(get_db)):
    if len(segment_ids) != 2:
        raise HTTPException(400, "必须提交恰好 2 个 segment_id")
    seg_a = get_segment(db, segment_ids[0])
    seg_b = get_segment(db, segment_ids[1])
    if seg_a is None or seg_b is None:
        raise HTTPException(404, "Segment 不存在")
    try:
        merged = segment_edit_service.merge_rallies(db, seg_a, seg_b)
        db.commit()
    except ValueError as e:
        db.rollback()
        raise HTTPException(400, str(e)) from e
    return _seg_dict(merged)


# ── Archive / Restore ──


@router.post("/{segment_id}/archive")
def archive_segment(segment_id: str, db: Session = Depends(get_db)):
    seg = get_segment(db, segment_id)
    if seg is None:
        raise HTTPException(404, "Segment 不存在")
    seg = segment_edit_service.archive_segment(db, seg)
    db.commit()
    return _seg_dict(seg)


@router.post("/{segment_id}/restore")
def restore_segment(segment_id: str, db: Session = Depends(get_db)):
    seg = get_segment(db, segment_id)
    if seg is None:
        raise HTTPException(404, "Segment 不存在")
    seg = segment_edit_service.restore_segment(db, seg)
    db.commit()
    return _seg_dict(seg)


@router.delete("/{segment_id}", status_code=204)
def delete_segment(segment_id: str, db: Session = Depends(get_db)):
    seg = get_segment(db, segment_id)
    if seg is None:
        raise HTTPException(404, "Segment 不存在")
    ok = segment_edit_service.hard_delete_segment(db, seg)
    if not ok:
        raise HTTPException(400, "不能删除该 Segment（有子节点、分析引用或编辑历史），请使用 archive")
    db.commit()


# ── AnalysisBatch ──

router2 = APIRouter(prefix="/api/capture-takes", tags=["analysis-batches"])


@router2.post("/{capture_take_id}/analysis-batches")
def create_batch(
    capture_take_id: str,
    segment_ids: list[str],
    analysis_profile: str = "match_default",
    db: Session = Depends(get_db),
):
    take = get_capture_take(db, capture_take_id)
    if take is None:
        raise HTTPException(404, "CaptureTake 不存在")
    try:
        batch, items = analysis_batch_service.create_analysis_batch(
            db,
            capture_take_id,
            segment_ids,
            analysis_profile=analysis_profile,
        )
        db.commit()
    except ValueError as e:
        db.rollback()
        raise HTTPException(400, str(e)) from e
    return {
        "batch_id": batch.id,
        "status": batch.status.value,
        "analysis_profile": batch.analysis_profile,
        "items": [
            {
                "id": it.id,
                "segment_id": it.segment_id,
                "segment_version": it.segment_version,
                "snapshot_start_ms": it.snapshot_start_ms,
                "snapshot_end_ms": it.snapshot_end_ms,
                "video_id": it.video_id,
                "status": it.status.value,
            }
            for it in items
        ],
    }


@router2.get("/{capture_take_id}/analysis-batches/{batch_id}")
def get_batch_detail(
    capture_take_id: str,
    batch_id: str,
    db: Session = Depends(get_db),
):
    batch = analysis_batch_service.get_batch(db, batch_id)
    if batch is None:
        raise HTTPException(404, "AnalysisBatch 不存在")
    items = analysis_batch_service.get_batch_items(db, batch_id)
    return {
        "batch_id": batch.id,
        "status": batch.status.value,
        "analysis_profile": batch.analysis_profile,
        "items": [
            {
                "id": it.id,
                "segment_id": it.segment_id,
                "analysis_job_id": it.analysis_job_id,
                "status": it.status.value,
                "error_message": it.error_message,
                "snapshot_start_ms": it.snapshot_start_ms,
                "snapshot_end_ms": it.snapshot_end_ms,
            }
            for it in items
        ],
    }


# ── helpers ──


def _seg_dict(seg) -> dict:
    return {
        "id": seg.id,
        "capture_take_id": seg.capture_take_id,
        "segment_type": seg.segment_type.value if hasattr(seg.segment_type, "value") else seg.segment_type,
        "parent_segment_id": seg.parent_segment_id,
        "ordinal": seg.ordinal,
        "label": seg.label,
        "start_ms": seg.start_ms,
        "end_ms": seg.end_ms,
        "corrected_start_ms": seg.corrected_start_ms,
        "corrected_end_ms": seg.corrected_end_ms,
        "effective_start_ms": seg.effective_start_ms if hasattr(seg, "effective_start_ms") else seg.start_ms,
        "effective_end_ms": seg.effective_end_ms if hasattr(seg, "effective_end_ms") else seg.end_ms,
        "edit_version": seg.edit_version if hasattr(seg, "edit_version") else 0,
        "edit_status": seg.edit_status.value
        if hasattr(seg.edit_status, "value")
        else getattr(seg, "edit_status", "active"),
        "status": seg.status.value if hasattr(seg.status, "value") else seg.status,
        "is_highlight": seg.is_highlight,
    }
