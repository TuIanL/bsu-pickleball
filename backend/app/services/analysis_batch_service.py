"""AnalysisBatch 服务 —— 批量创建按 Segment 裁剪的分析任务。"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.analysis_batch import AnalysisBatch, AnalysisBatchItem, BatchStatus, BatchItemStatus
from app.models.capture_segment import CaptureSegment, EditStatus
from app.models.capture_track import CaptureTrack

_BATCH_PREFIX = "ab"
_ITEM_PREFIX = "bi"
_DEFAULT_BATCH_LIMIT = 10


def _gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def create_analysis_batch(
    db: Session,
    capture_take_id: str,
    segment_ids: list[str],
    *,
    analysis_profile: str = "match_default",
    batch_limit: int = _DEFAULT_BATCH_LIMIT,
) -> tuple[AnalysisBatch, list[AnalysisBatchItem]]:
    if len(segment_ids) > batch_limit:
        raise ValueError(f"批量上限 {batch_limit}，提交了 {len(segment_ids)} 个")

    # 加载所有 segments
    segments = (
        db.query(CaptureSegment)
        .filter(
            CaptureSegment.id.in_(segment_ids),
            CaptureSegment.capture_take_id == capture_take_id,
            CaptureSegment.edit_status == EditStatus.active,
        )
        .all()
    )
    if len(segments) != len(segment_ids):
        raise ValueError("部分 segment 不存在或非 active 状态")

    # 校验同类型
    types = {s.segment_type.value for s in segments}
    if len(types) > 1:
        raise ValueError(f"一次 Batch 只能选同一种 segment_type，当前: {types}")

    # 校验无父子关系
    ids_set = set(segment_ids)
    for s in segments:
        if s.parent_segment_id and s.parent_segment_id in ids_set:
            raise ValueError(f"不能同时选择父 segment {s.parent_segment_id} 和子 segment {s.id}")

    # 获取 primary track
    track = (
        db.query(CaptureTrack)
        .filter(
            CaptureTrack.capture_take_id == capture_take_id,
            CaptureTrack.role == "primary",
        )
        .first()
    )
    if track is None:
        raise ValueError("未找到 primary CaptureTrack")

    video_id = track.video_id or ""
    track_id = track.id

    # 创建 Batch
    now = datetime.now(timezone.utc)
    batch = AnalysisBatch(
        id=_gen_id(_BATCH_PREFIX),
        capture_take_id=capture_take_id,
        status=BatchStatus.creating,
        analysis_profile=analysis_profile,
        created_at=now,
    )
    db.add(batch)
    db.flush()

    # 创建 BatchItems
    items: list[AnalysisBatchItem] = []
    for seg in segments:
        eff_start = seg.effective_start_ms
        eff_end = seg.effective_end_ms
        if eff_end is None:
            raise ValueError(f"Segment {seg.id} 没有 end_ms，无法创建分析任务")

        item = AnalysisBatchItem(
            id=_gen_id(_ITEM_PREFIX),
            batch_id=batch.id,
            segment_id=seg.id,
            segment_version=seg.edit_version,
            snapshot_start_ms=eff_start,
            snapshot_end_ms=eff_end,
            track_id=track_id,
            video_id=video_id,
            status=BatchItemStatus.pending,
            created_at=now,
        )
        db.add(item)
        items.append(item)

    batch.status = BatchStatus.queued
    db.flush()
    return batch, items


def get_batch(db: Session, batch_id: str) -> AnalysisBatch | None:
    return db.query(AnalysisBatch).filter(AnalysisBatch.id == batch_id).first()


def get_batch_items(db: Session, batch_id: str) -> list[AnalysisBatchItem]:
    return (
        db.query(AnalysisBatchItem)
        .filter(AnalysisBatchItem.batch_id == batch_id)
        .order_by(AnalysisBatchItem.created_at.asc())
        .all()
    )


def update_item_status(
    db: Session, item: AnalysisBatchItem, status: str, job_id: str | None = None, error: str | None = None
) -> None:
    item.status = BatchItemStatus(status)
    if job_id:
        item.analysis_job_id = job_id
    if error:
        item.error_message = error
    db.flush()

    # 更新 batch 状态
    items = get_batch_items(db, item.batch_id)
    statuses = {i.status for i in items}
    batch = get_batch(db, item.batch_id)
    if batch:
        if statuses == {BatchItemStatus.completed}:
            batch.status = BatchStatus.completed
        elif BatchItemStatus.failed in statuses:
            batch.status = BatchStatus.partial if BatchItemStatus.completed in statuses else BatchStatus.failed
        elif BatchItemStatus.running in statuses:
            batch.status = BatchStatus.running
        elif BatchItemStatus.queued in statuses:
            batch.status = BatchStatus.queued
        db.flush()
