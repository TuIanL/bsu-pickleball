"""CaptureSegment 服务层 —— 区间投影，最小 MVP 版本。"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.capture_segment import CaptureSegment, EditStatus, SegmentSource, SegmentStatus, SegmentType

# 区间 ID 前缀
_ID_PREFIX = "sg"


# 生成带前缀的唯一 ID（sg_ + 12 位随机十六进制）
def _generate_id() -> str:
    return f"{_ID_PREFIX}_{uuid4().hex[:12]}"


# 创建一条区间记录（默认状态为 open）
def create_segment(
    db: Session,
    *,
    capture_take_id: str,
    segment_type: str,
    ordinal: int,
    start_ms: int,
    start_event_id: str | None = None,
    parent_segment_id: str | None = None,
    label: str = "",
    source: str = "manual",
) -> CaptureSegment:
    seg = CaptureSegment(
        id=_generate_id(),
        capture_take_id=capture_take_id,
        segment_type=SegmentType(segment_type),
        ordinal=ordinal,
        start_ms=start_ms,
        start_event_id=start_event_id,
        parent_segment_id=parent_segment_id,
        label=label,
        status=SegmentStatus.open,
        source=SegmentSource(source),
    )
    db.add(seg)
    db.flush()
    return seg


# 关闭区间，填写结束时间与状态（默认 closed）
def close_segment(
    db: Session,
    segment: CaptureSegment,
    *,
    end_ms: int,
    end_event_id: str | None = None,
    status: str = "closed",
    close_reason: str | None = None,
) -> None:
    segment.end_ms = end_ms
    segment.end_event_id = end_event_id
    segment.status = SegmentStatus(status)
    segment.close_reason = close_reason
    db.flush()


# 获取某个 take 下所有未关闭的区间，按类型排序
def get_open_segments_for_take(db: Session, capture_take_id: str) -> list[CaptureSegment]:
    return (
        db.query(CaptureSegment)
        .filter(
            CaptureSegment.capture_take_id == capture_take_id,
            CaptureSegment.status == SegmentStatus.open,
            CaptureSegment.edit_status == EditStatus.active,
        )
        .order_by(CaptureSegment.segment_type.asc())
        .all()
    )


# 按类型获取某个 take 下唯一未关闭的区间
def get_open_segment_by_type(db: Session, capture_take_id: str, segment_type: str) -> CaptureSegment | None:
    return (
        db.query(CaptureSegment)
        .filter(
            CaptureSegment.capture_take_id == capture_take_id,
            CaptureSegment.segment_type == SegmentType(segment_type),
            CaptureSegment.status == SegmentStatus.open,
            CaptureSegment.edit_status == EditStatus.active,
        )
        .first()
    )


# 列出某个 take 的区间，可按类型过滤，按开始时间升序
def list_segments(
    db: Session,
    capture_take_id: str,
    segment_type: str | None = None,
) -> list[CaptureSegment]:
    q = db.query(CaptureSegment).filter(
        CaptureSegment.capture_take_id == capture_take_id,
        CaptureSegment.edit_status == EditStatus.active,
    )
    if segment_type:
        try:
            q = q.filter(CaptureSegment.segment_type == SegmentType(segment_type))
        except ValueError:
            pass
    return q.order_by(CaptureSegment.start_ms.asc()).all()


# 按 ID 获取单条区间
def get_segment(db: Session, segment_id: str) -> CaptureSegment | None:
    return db.query(CaptureSegment).filter(CaptureSegment.id == segment_id).first()


# 关闭某个 take 下所有未关闭区间（录制停止时，状态记为 inferred）
def close_all_open_for_take(db: Session, capture_take_id: str, end_ms: int) -> list[CaptureSegment]:
    open_segs = get_open_segments_for_take(db, capture_take_id)
    for seg in open_segs:
        close_segment(
            db,
            seg,
            end_ms=end_ms,
            status="inferred",
            close_reason="recording_stopped",
        )
    return open_segs
