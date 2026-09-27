"""Segment 编辑 & AnalysisBatch API routes。"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.segment_serialization import segment_to_api_dict
from app.core.config import get_settings
from app.database import get_db
from app.models.capture_segment import CaptureSegment, EditStatus, SegmentSource, SegmentType
from app.models.match_state_segmentation import MatchStateSegmentationRun
from app.schemas.match_state_candidate import MatchStateCandidateDecisionRequest
from app.schemas.segment_boundary_review import BOUNDARY_REVIEW_SCHEMA_VERSION, BoundaryReviewRequest
from app.schemas.segment_creation import RallyCreateRequest
from app.schemas.segment_ordinal import RALLY_ORDINAL_UPDATE_SCHEMA_VERSION, RallyOrdinalUpdateRequest
from app.services import analysis_batch_service, match_state_candidate_service, segment_edit_service
from app.services.capture_segment_service import get_segment
from app.services.capture_take_service import get_capture_take
from app.services.formal_segmentation_service import ACTIVE_SEGMENTATION_STATUSES

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
        take = get_capture_take(db, seg.capture_take_id)
        seg = segment_edit_service.patch_segment(
            db,
            seg,
            label=label,
            corrected_start_ms=corrected_start_ms,
            corrected_end_ms=corrected_end_ms,
            is_highlight=is_highlight,
            expected_version=expected_version,
            take_duration_ms=take.duration_ms if take is not None else None,
        )
        db.commit()
    except ValueError as e:
        db.rollback()
        msg = str(e)
        if "edit_version 冲突" in msg:
            raise HTTPException(409, msg) from e
        raise HTTPException(400, msg) from e
    return segment_to_api_dict(seg)


@router.post("/{segment_id}/reset-boundary-correction")
def reset_boundary(segment_id: str, db: Session = Depends(get_db)):
    seg = get_segment(db, segment_id)
    if seg is None:
        raise HTTPException(404, "Segment 不存在")
    seg = segment_edit_service.reset_boundary(db, seg)
    db.commit()
    return segment_to_api_dict(seg)


@router.post("/{segment_id}/boundary-review")
def review_boundary(segment_id: str, request: BoundaryReviewRequest, db: Session = Depends(get_db)):
    seg = get_segment(db, segment_id)
    if seg is None:
        raise HTTPException(404, "Segment 不存在")
    try:
        take = get_capture_take(db, seg.capture_take_id)
        seg = segment_edit_service.review_rally_boundary(
            db,
            seg,
            decision=request.decision,
            expected_version=request.expected_version,
            start_ms=request.start_ms,
            end_ms=request.end_ms,
            note=request.note,
            take_duration_ms=take.duration_ms if take is not None else None,
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        if "edit_version 冲突" in str(exc):
            raise HTTPException(409, str(exc)) from exc
        raise HTTPException(400, str(exc)) from exc
    records = segment_edit_service.boundary_review_records(db, seg.capture_take_id)
    return _boundary_review_seg_dict(seg, records.get(seg.id))


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
    return {"segments": [segment_to_api_dict(a), segment_to_api_dict(b)]}


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
    return segment_to_api_dict(merged)


# ── Archive / Restore ──


@router.post("/{segment_id}/archive")
def archive_segment(segment_id: str, db: Session = Depends(get_db)):
    seg = get_segment(db, segment_id)
    if seg is None:
        raise HTTPException(404, "Segment 不存在")
    seg = segment_edit_service.archive_segment(db, seg)
    db.commit()
    return segment_to_api_dict(seg)


@router.post("/{segment_id}/restore")
def restore_segment(segment_id: str, db: Session = Depends(get_db)):
    seg = get_segment(db, segment_id)
    if seg is None:
        raise HTTPException(404, "Segment 不存在")
    seg = segment_edit_service.restore_segment(db, seg)
    db.commit()
    return segment_to_api_dict(seg)


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


@router2.get("/{capture_take_id}/formal-segmentation-summary")
def get_formal_segmentation_summary(capture_take_id: str, db: Session = Depends(get_db)):
    """Return the product-facing summary for the latest formal segmentation run.

    Candidate/QA artifacts deliberately do not participate in this response.
    The endpoint is stable for old takes without a formal run: it returns an
    ``unavailable`` summary instead of making the segment page fail to render.
    """
    if get_capture_take(db, capture_take_id) is None:
        raise HTTPException(404, "CaptureTake 不存在")
    runs = (
        db.query(MatchStateSegmentationRun)
        .filter(MatchStateSegmentationRun.capture_take_id == capture_take_id)
        .order_by(
            MatchStateSegmentationRun.finished_at.desc(),
            MatchStateSegmentationRun.started_at.desc(),
        )
        .all()
    )
    if not runs:
        return {
            "capture_take_id": capture_take_id,
            "status": "unavailable",
            "run_id": None,
            "model_package_id": None,
            "model_version": None,
            "generated_at": None,
            "segment_count": 0,
            "window_plan_hash": None,
            "artifact_available": False,
            "detail": "formal_segmentation_not_run",
        }

    # A failed retry deliberately does not supersede the last published run.
    # The product summary therefore follows the active successful publication,
    # so the segment page keeps showing the preserved automatic rallies while
    # the failed retry remains auditable through its AnalysisJob/Run record.
    # 「已发布/可用」状态集合与切分复用共用服务层单一来源，此处只做一次判定，
    # 之后的分段计数与响应字段都复用它。
    run = next(
        (candidate for candidate in runs if candidate.status in ACTIVE_SEGMENTATION_STATUSES),
        runs[0],
    )
    published = run.status in ACTIVE_SEGMENTATION_STATUSES

    count = 0
    if published:
        count = (
            db.query(CaptureSegment)
            .filter(
                CaptureSegment.capture_take_id == capture_take_id,
                CaptureSegment.segmentation_run_id == run.id,
                CaptureSegment.source == SegmentSource.algorithm,
                CaptureSegment.edit_status == EditStatus.active,
            )
            .count()
        )
    artifact_available = bool(run.artifact_path)
    if run.artifact_path:
        try:
            from app.services.storage_service import StorageService

            artifact_available = StorageService().formal_segmentation_artifact_path(
                run.planning_job_id, capture_take_id, create_root=False
            ).is_file()
        except (OSError, ValueError):
            artifact_available = False
    detail = None
    try:
        diagnostics = json.loads(run.diagnostics_json or "{}")
        if isinstance(diagnostics, dict):
            detail = diagnostics.get("detail") or diagnostics.get("message") or diagnostics.get("reason")
    except (TypeError, ValueError, json.JSONDecodeError):
        detail = None
    return {
        "capture_take_id": capture_take_id,
        "status": run.status.value if hasattr(run.status, "value") else str(run.status),
        "run_id": run.id,
        "model_package_id": run.model_package_id,
        "model_version": run.model_package_version,
        "generated_at": run.finished_at.isoformat() if run.finished_at else None,
        "segment_count": count if published else 0,
        "window_plan_hash": run.window_plan_hash,
        "artifact_available": artifact_available,
        "detail": detail,
    }


@router2.post("/{capture_take_id}/segments")
def create_rally_segment(
    capture_take_id: str,
    request: RallyCreateRequest,
    db: Session = Depends(get_db),
):
    """从双摄复核工作台补录一条漏记 rally。"""
    take = get_capture_take(db, capture_take_id)
    if take is None:
        raise HTTPException(404, "CaptureTake 不存在")
    try:
        segment = segment_edit_service.create_manual_rally(
            db,
            capture_take_id=capture_take_id,
            start_ms=request.start_ms,
            end_ms=request.end_ms,
            label=request.label,
            take_duration_ms=take.duration_ms,
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc)) from exc
    return segment_to_api_dict(segment)


@router2.post("/{capture_take_id}/rally-ordinals")
def update_rally_ordinals(
    capture_take_id: str,
    request: RallyOrdinalUpdateRequest,
    db: Session = Depends(get_db),
):
    """在一个录像（一个比赛局）内修正 rally 的连续序号。"""
    take = get_capture_take(db, capture_take_id)
    if take is None:
        raise HTTPException(404, "CaptureTake 不存在")
    try:
        segments, operation_id = segment_edit_service.renumber_rally_ordinals(
            db,
            capture_take_id=capture_take_id,
            mode=request.mode,
            anchor_segment_id=request.anchor_segment_id,
            start_ordinal=request.start_ordinal,
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc)) from exc
    return {
        "schema_version": RALLY_ORDINAL_UPDATE_SCHEMA_VERSION,
        "capture_take_id": capture_take_id,
        "operation_id": operation_id,
        "mode": request.mode,
        "start_ordinal": request.start_ordinal,
        "segments": [segment_to_api_dict(segment) for segment in segments],
    }


@router2.get("/{capture_take_id}/boundary-review")
def get_boundary_review(capture_take_id: str, db: Session = Depends(get_db)):
    take = get_capture_take(db, capture_take_id)
    if take is None:
        raise HTTPException(404, "CaptureTake 不存在")
    candidate_segments = (
        db.query(CaptureSegment)
        .filter(
            CaptureSegment.capture_take_id == capture_take_id,
            CaptureSegment.segment_type == SegmentType.rally,
            CaptureSegment.edit_status != EditStatus.superseded,
        )
        .order_by(CaptureSegment.start_ms.asc())
        .all()
    )
    records = segment_edit_service.boundary_review_records(db, capture_take_id)
    segments = [
        segment
        for segment in candidate_segments
        if segment.edit_status == EditStatus.active
        or (records.get(segment.id) or {}).get("review_status") == "excluded"
    ]
    segments, suppressed_duplicate_ids = segment_edit_service.deduplicate_boundary_review_segments(
        segments, records
    )
    items = [_boundary_review_seg_dict(segment, records.get(segment.id)) for segment in segments]
    counts = {
        status: sum(item["boundary_review_status"] == status for item in items)
        for status in ("pending", "confirmed", "corrected", "excluded")
    }
    return {
        "schema_version": BOUNDARY_REVIEW_SCHEMA_VERSION,
        "capture_take_id": capture_take_id,
        "total_count": len(items),
        "pending_count": counts["pending"],
        "confirmed_count": counts["confirmed"],
        "corrected_count": counts["corrected"],
        "excluded_count": counts["excluded"],
        "suppressed_duplicate_count": len(suppressed_duplicate_ids),
        "suppressed_duplicate_segment_ids": suppressed_duplicate_ids,
        "segments": items,
    }


@router2.get("/{capture_take_id}/match-state-candidates")
def get_match_state_candidates(capture_take_id: str, db: Session = Depends(get_db)):
    """Return learned candidates independently from the authoritative segment timeline."""
    if get_capture_take(db, capture_take_id) is None:
        raise HTTPException(404, "CaptureTake 不存在")
    root = get_settings().resolved_match_state_candidate_dir
    return match_state_candidate_service.get_candidate_review(root, capture_take_id, db)


@router2.post("/{capture_take_id}/match-state-candidates/{candidate_id}/decision")
def decide_match_state_candidate(
    capture_take_id: str,
    candidate_id: str,
    request: MatchStateCandidateDecisionRequest,
    db: Session = Depends(get_db),
):
    """Accept/correct into the official timeline, or reject while retaining an audit record."""
    take = get_capture_take(db, capture_take_id)
    if take is None:
        raise HTTPException(404, "CaptureTake 不存在")
    if not request.artifact_version or "request_id" not in request.model_fields_set:
        raise HTTPException(422, "artifact_version and request_id are required")
    try:
        record, segment = match_state_candidate_service.decide_candidate(
            db,
            root=get_settings().resolved_match_state_candidate_dir,
            capture_take_id=capture_take_id,
            candidate_id=candidate_id,
            request=request,
            take_duration_ms=take.duration_ms,
            export_sidecar=False,
        )
        db.commit()
        try:
            match_state_candidate_service.export_review_record(
                get_settings().resolved_match_state_candidate_dir,
                capture_take_id,
                record,
                db=db,
            )
        except (OSError, ValueError, json.JSONDecodeError):
            # SQLite is authoritative; a later export can rebuild the sidecar.
            logging.getLogger(__name__).warning("Candidate review export failed for %s", capture_take_id, exc_info=True)
    except RuntimeError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(409, "candidate decision transaction failed") from exc
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        db.rollback()
        raise HTTPException(400, str(exc)) from exc
    return {
        "schema_version": "match-state-candidate-review.v1",
        "capture_take_id": capture_take_id,
        "record": record,
        "segment": segment_to_api_dict(segment) if segment is not None else None,
    }


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


def _boundary_review_seg_dict(seg, review: dict | None) -> dict:
    item = segment_to_api_dict(seg)
    status = str((review or {}).get("review_status") or "pending")
    if seg.edit_status == EditStatus.archived:
        status = "excluded"
    elif status == "excluded":
        # 恢复后的回合必须重新确认，不能沿用旧的排除决定。
        status = "pending"
    item.update(
        {
            "boundary_review_status": status,
            "boundary_review_note": (review or {}).get("note"),
            "boundary_reviewed_at": (review or {}).get("reviewed_at"),
            "boundary_review_operation_id": (review or {}).get("operation_id"),
        }
    )
    return item
