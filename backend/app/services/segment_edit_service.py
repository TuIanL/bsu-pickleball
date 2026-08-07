"""Segment 编辑服务 —— 非破坏式边界修正、拆分、合并、归档/恢复。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.capture_segment import CaptureSegment, EditStatus, SegmentStatus, SegmentType
from app.models.segment_edit_operation import EditOperationType, SegmentEditOperation

_OP_PREFIX = "eo"
_MIN_RALLY_MS = 500
_MAX_MERGE_GAP_MS = 500


def _gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


# ── effective helpers ──


def _eff_start(seg: CaptureSegment) -> int:
    return seg.corrected_start_ms if seg.corrected_start_ms is not None else seg.start_ms


def _eff_end(seg: CaptureSegment) -> int | None:
    return seg.corrected_end_ms if seg.corrected_end_ms is not None else seg.end_ms


# ── PATCH ──


def patch_segment(
    db: Session,
    segment: CaptureSegment,
    *,
    label: str | None = None,
    corrected_start_ms: int | None = None,
    corrected_end_ms: int | None = None,
    is_highlight: bool | None = None,
    expected_version: int | None = None,
) -> CaptureSegment:
    if expected_version is not None and segment.edit_version != expected_version:
        raise ValueError(f"edit_version 冲突: 期望 {expected_version}，当前 {segment.edit_version}")

    changed = False
    if label is not None:
        segment.label = label
        changed = True
    if is_highlight is not None:
        segment.is_highlight = is_highlight
        changed = True
    if corrected_start_ms is not None:
        segment.corrected_start_ms = corrected_start_ms
        segment.corrected_at = datetime.now(UTC)
        changed = True
    if corrected_end_ms is not None:
        segment.corrected_end_ms = corrected_end_ms
        segment.corrected_at = datetime.now(UTC)
        changed = True

    if changed:
        segment.edit_version += 1
        segment.updated_at = datetime.now(UTC)

    db.flush()
    return segment


def reset_boundary(db: Session, segment: CaptureSegment) -> CaptureSegment:
    segment.corrected_start_ms = None
    segment.corrected_end_ms = None
    segment.corrected_at = None
    segment.edit_version += 1
    segment.updated_at = datetime.now(UTC)
    db.flush()
    return segment


# ── 拆分 ──


def split_rally(
    db: Session,
    segment: CaptureSegment,
    *,
    split_ms: int,
) -> tuple[CaptureSegment, CaptureSegment]:
    if segment.segment_type != SegmentType.rally:
        raise ValueError("仅支持拆分 rally 类型")
    if segment.edit_status != EditStatus.active:
        raise ValueError("仅可拆分 active 的 segment")

    start = _eff_start(segment)
    end = _eff_end(segment)
    if end is None:
        raise ValueError("无法拆分 open rally")
    if split_ms - start < _MIN_RALLY_MS or end - split_ms < _MIN_RALLY_MS:
        raise ValueError(f"拆分点 {split_ms} 两侧时长不足 {_MIN_RALLY_MS}ms")

    now = datetime.now(UTC)
    op_id = _gen_id(_OP_PREFIX)

    # 原 segment → superseded
    segment.edit_status = EditStatus.superseded
    segment.superseded_by_operation_id = op_id
    segment.updated_at = now

    # 创建两个新 segment
    seg_a = CaptureSegment(
        id=_gen_id("sg"),
        capture_take_id=segment.capture_take_id,
        segment_type=SegmentType.rally,
        parent_segment_id=segment.parent_segment_id,
        ordinal=segment.ordinal,
        label=f"{segment.label}-A",
        start_ms=start,
        end_ms=split_ms,
        status=SegmentStatus.closed,
        source=segment.source,
        edit_status=EditStatus.active,
        created_by_operation_id=op_id,
    )
    seg_b = CaptureSegment(
        id=_gen_id("sg"),
        capture_take_id=segment.capture_take_id,
        segment_type=SegmentType.rally,
        parent_segment_id=segment.parent_segment_id,
        ordinal=segment.ordinal + 1,
        label=f"{segment.label}-B",
        start_ms=split_ms,
        end_ms=end,
        status=SegmentStatus.closed,
        source=segment.source,
        edit_status=EditStatus.active,
        created_by_operation_id=op_id,
    )
    db.add(seg_a)
    db.add(seg_b)

    # 审计记录
    _create_op(
        db,
        op_id,
        segment.capture_take_id,
        EditOperationType.split,
        [segment.id],
        [seg_a.id, seg_b.id],
        {"split_ms": split_ms, "original_segment_id": segment.id},
    )

    db.flush()
    return seg_a, seg_b


# ── 合并 ──


def merge_rallies(
    db: Session,
    seg_a: CaptureSegment,
    seg_b: CaptureSegment,
) -> CaptureSegment:
    if seg_a.segment_type != SegmentType.rally or seg_b.segment_type != SegmentType.rally:
        raise ValueError("仅支持合并 rally 类型")
    if seg_a.parent_segment_id != seg_b.parent_segment_id:
        raise ValueError("Rally 不属于同一父 game")
    if seg_a.edit_status != EditStatus.active or seg_b.edit_status != EditStatus.active:
        raise ValueError("仅可合并 active 的 segment")

    a_end = _eff_end(seg_a)
    b_start = _eff_start(seg_b)
    if a_end is None or b_start is None:
        raise ValueError("无法合并 open rally")
    gap = b_start - a_end
    if abs(gap) > _MAX_MERGE_GAP_MS:
        raise ValueError(f"Rally 间隙 {gap}ms 超过 {_MAX_MERGE_GAP_MS}ms 上限")

    # 检查中间是否有其他 active rally
    siblings = (
        db.query(CaptureSegment)
        .filter(
            CaptureSegment.parent_segment_id == seg_a.parent_segment_id,
            CaptureSegment.segment_type == SegmentType.rally,
            CaptureSegment.edit_status == EditStatus.active,
            CaptureSegment.id.notin_([seg_a.id, seg_b.id]),
            CaptureSegment.start_ms >= min(seg_a.start_ms, seg_b.start_ms),
            CaptureSegment.start_ms <= max((a_end or 0), (b_start or 0)),
        )
        .all()
    )
    if siblings:
        raise ValueError("两个 Rally 之间存在其他 active Rally")

    now = datetime.now(UTC)
    op_id = _gen_id(_OP_PREFIX)

    seg_a.edit_status = EditStatus.superseded
    seg_a.superseded_by_operation_id = op_id
    seg_a.updated_at = now
    seg_b.edit_status = EditStatus.superseded
    seg_b.superseded_by_operation_id = op_id
    seg_b.updated_at = now

    merged = CaptureSegment(
        id=_gen_id("sg"),
        capture_take_id=seg_a.capture_take_id,
        segment_type=SegmentType.rally,
        parent_segment_id=seg_a.parent_segment_id,
        ordinal=seg_a.ordinal,
        label=f"{seg_a.label}+{seg_b.label}",
        start_ms=min(seg_a.start_ms, seg_b.start_ms),
        end_ms=max(a_end, _eff_end(seg_b) or 0),
        status=SegmentStatus.closed,
        source=SegmentStatus.corrected,
        edit_status=EditStatus.active,
        created_by_operation_id=op_id,
    )
    db.add(merged)

    _create_op(
        db,
        op_id,
        seg_a.capture_take_id,
        EditOperationType.merge,
        [seg_a.id, seg_b.id],
        [merged.id],
        {"original_ids": [seg_a.id, seg_b.id]},
    )

    db.flush()
    return merged


# ── 归档/恢复 ──


def archive_segment(db: Session, segment: CaptureSegment) -> CaptureSegment:
    op_id = _gen_id(_OP_PREFIX)
    segment.edit_status = EditStatus.archived
    segment.updated_at = datetime.now(UTC)
    _create_op(db, op_id, segment.capture_take_id, EditOperationType.archive, [segment.id], [segment.id])
    db.flush()
    return segment


def restore_segment(db: Session, segment: CaptureSegment) -> CaptureSegment:
    op_id = _gen_id(_OP_PREFIX)
    segment.edit_status = EditStatus.active
    segment.updated_at = datetime.now(UTC)
    _create_op(db, op_id, segment.capture_take_id, EditOperationType.restore, [segment.id], [segment.id])
    db.flush()
    return segment


def hard_delete_segment(db: Session, segment: CaptureSegment) -> bool:
    if segment.edit_status != EditStatus.active:
        return False
    # 仅无子节点、无分析引用、无编辑历史的临时 segment 可硬删除
    has_children = (db.query(CaptureSegment).filter(CaptureSegment.parent_segment_id == segment.id).count()) > 0
    if has_children:
        return False
    op_count = (
        db.query(SegmentEditOperation)
        .filter(
            SegmentEditOperation.input_segment_ids.contains(segment.id)
            | SegmentEditOperation.output_segment_ids.contains(segment.id)
        )
        .count()
    )
    if op_count > 0:
        return False
    db.delete(segment)
    db.flush()
    return True


# ── 审计 ──


def _create_op(
    db: Session,
    op_id: str,
    capture_take_id: str,
    op_type: EditOperationType,
    input_ids: list[str],
    output_ids: list[str],
    payload: dict | None = None,
) -> SegmentEditOperation:
    op = SegmentEditOperation(
        id=op_id,
        capture_take_id=capture_take_id,
        operation_type=op_type,
        input_segment_ids=json.dumps(input_ids, ensure_ascii=False),
        output_segment_ids=json.dumps(output_ids, ensure_ascii=False),
        payload_json=json.dumps(payload or {}, ensure_ascii=False),
    )
    db.add(op)
    return op


# ── 层级约束校验 ──


def validate_bounds_in_take(seg: CaptureSegment, take_duration_ms: int) -> None:
    start = _eff_start(seg)
    end = _eff_end(seg)
    if start < 0:
        raise ValueError("effective_start_ms 不能小于 0")
    if end is not None:
        if end <= start:
            raise ValueError("effective_end_ms 必须大于 effective_start_ms")
        if end > take_duration_ms:
            raise ValueError(f"effective_end_ms {end} 超出录制时长 {take_duration_ms}")


def validate_child_in_parent(child: CaptureSegment, parent: CaptureSegment) -> None:
    if _eff_start(child) < _eff_start(parent):
        raise ValueError(f"子 segment 起点 {_eff_start(child)} 小于父起点 {_eff_start(parent)}")
    p_end = _eff_end(parent)
    c_end = _eff_end(child)
    if p_end is not None and c_end is not None and c_end > p_end:
        raise ValueError(f"子 segment 终点 {c_end} 超出父终点 {p_end}")


def validate_parent_contains_children(db: Session, parent: CaptureSegment, new_start: int, new_end: int) -> None:
    children = (
        db.query(CaptureSegment)
        .filter(
            CaptureSegment.parent_segment_id == parent.id,
            CaptureSegment.edit_status == EditStatus.active,
        )
        .all()
    )
    for child in children:
        c_start = _eff_start(child)
        c_end = _eff_end(child)
        if c_start < new_start or (c_end is not None and c_end > new_end):
            raise ValueError(f"父边界调整后不能包含子 segment {child.id} ({c_start}→{c_end})")
