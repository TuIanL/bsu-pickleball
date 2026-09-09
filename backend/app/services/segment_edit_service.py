"""Segment 编辑服务 —— 非破坏式边界修正、拆分、合并、归档/恢复。"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.capture_segment import CaptureSegment, EditStatus, SegmentSource, SegmentStatus, SegmentType
from app.models.segment_edit_operation import EditOperationType, SegmentEditOperation
from app.schemas.segment_creation import RALLY_CREATION_SCHEMA_VERSION
from app.schemas.segment_boundary_review import BOUNDARY_REVIEW_SCHEMA_VERSION, BoundaryReviewDecision
from app.schemas.segment_ordinal import RALLY_ORDINAL_UPDATE_SCHEMA_VERSION

_OP_PREFIX = "eo"
_MIN_RALLY_MS = 500
_MAX_MERGE_GAP_MS = 500
_DEFAULT_RALLY_LABEL = re.compile(r"^第\d+分$")


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
    take_duration_ms: int | None = None,
) -> CaptureSegment:
    if expected_version is not None and segment.edit_version != expected_version:
        raise ValueError(f"edit_version 冲突: 期望 {expected_version}，当前 {segment.edit_version}")

    boundary_changed = corrected_start_ms is not None or corrected_end_ms is not None
    if boundary_changed:
        candidate_start = corrected_start_ms if corrected_start_ms is not None else _eff_start(segment)
        candidate_end = corrected_end_ms if corrected_end_ms is not None else _eff_end(segment)
        _validate_candidate_bounds(candidate_start, candidate_end, take_duration_ms)

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


# ── 有效回合边界人工复核 ──


def create_manual_rally(
    db: Session,
    *,
    capture_take_id: str,
    start_ms: int,
    end_ms: int,
    label: str = "",
    take_duration_ms: int | None = None,
    provenance: dict | None = None,
) -> CaptureSegment:
    """从复核工作台补录一条完整的、尚未确认的 rally。"""

    _validate_candidate_bounds(start_ms, end_ms, take_duration_ms)
    existing = (
        db.query(CaptureSegment)
        .filter(
            CaptureSegment.capture_take_id == capture_take_id,
            CaptureSegment.segment_type == SegmentType.rally,
            CaptureSegment.edit_status == EditStatus.active,
        )
        .order_by(CaptureSegment.start_ms.asc(), CaptureSegment.id.asc())
        .all()
    )

    for current in existing:
        current_start = _eff_start(current)
        current_end = _eff_end(current)
        overlaps = (
            current_start < end_ms and current_end is None
        ) or (
            current_end is not None and current_start < end_ms and current_end > start_ms
        )
        if overlaps:
            raise ValueError(f"新增回合与已有第{current.ordinal}分时间重叠，请先检查已有边界")

    ordered = sorted(existing, key=lambda segment: (_eff_start(segment), _eff_end(segment) or 2**63, segment.id))
    insert_index = sum(1 for current in ordered if _eff_start(current) < start_ms)
    ordinal = insert_index + 1
    renumbered: list[dict[str, int | str]] = []
    now = datetime.now(UTC)
    for index, current in enumerate(ordered):
        next_ordinal = index + 1 if index < insert_index else index + 2
        if current.ordinal == next_ordinal:
            continue
        previous_ordinal = current.ordinal
        current.ordinal = next_ordinal
        current.updated_at = now
        # 保留已有自定义标签；只同步系统默认的“第 N 分”标签，避免覆盖人工命名。
        if _DEFAULT_RALLY_LABEL.fullmatch((current.label or "").strip()):
            current.label = f"第{next_ordinal}分"
        renumbered.append({"segment_id": current.id, "from": previous_ordinal, "to": next_ordinal})

    operation_id = _gen_id(_OP_PREFIX)
    created_label = label.strip() or f"第{ordinal}分"
    segment = CaptureSegment(
        id=_gen_id("sg"),
        capture_take_id=capture_take_id,
        segment_type=SegmentType.rally,
        ordinal=ordinal,
        label=created_label,
        start_ms=start_ms,
        end_ms=end_ms,
        status=SegmentStatus.closed,
        source=SegmentSource.manual,
        edit_status=EditStatus.active,
        created_by_operation_id=operation_id,
    )
    db.add(segment)
    _create_op(
        db,
        operation_id,
        capture_take_id,
        EditOperationType.create,
        [],
        [segment.id],
        {
            "schema_version": RALLY_CREATION_SCHEMA_VERSION,
            "operation": "manual_rally_create",
            "start_ms": start_ms,
            "end_ms": end_ms,
            "ordinal": ordinal,
            "label": created_label,
            "renumbered_ordinals": renumbered,
            "provenance": provenance,
        },
    )
    db.flush()
    return segment


def record_candidate_rejection(
    db: Session,
    *,
    capture_take_id: str,
    candidate_id: str,
    provenance: dict,
    note: str | None = None,
) -> str:
    """Record a rejected learned candidate without mutating the authoritative timeline."""

    operation_id = _gen_id(_OP_PREFIX)
    _create_op(
        db,
        operation_id,
        capture_take_id,
        EditOperationType.boundary_correction,
        [],
        [],
        {
            "schema_version": "match-state-candidate-review.v1",
            "operation": "learned_candidate_rejected",
            "candidate_id": candidate_id,
            "decision": "rejected",
            "note": note or None,
            "provenance": provenance,
        },
    )
    db.flush()
    return operation_id


def renumber_rally_ordinals(
    db: Session,
    *,
    capture_take_id: str,
    mode: str,
    anchor_segment_id: str | None = None,
    start_ordinal: int = 1,
) -> tuple[list[CaptureSegment], str | None]:
    """修正一个录像（一个比赛局）内 rally 的序号，并保留操作审计。

    ordinal 的实际顺序以 take 时间为准。``from_anchor`` 只修改选中的
    rally 及其后续 rally，``whole_take`` 则从整段视频的第一条 active rally
    开始连续编号。边界字段完全不参与修改。
    """

    if mode not in {"from_anchor", "whole_take"}:
        raise ValueError("不支持的 rally 序号修正模式")
    if start_ordinal < 1:
        raise ValueError("起始分序号必须大于等于 1")
    if mode == "from_anchor" and not anchor_segment_id:
        raise ValueError("从当前分开始连续编号时必须指定 anchor_segment_id")

    existing = (
        db.query(CaptureSegment)
        .filter(
            CaptureSegment.capture_take_id == capture_take_id,
            CaptureSegment.segment_type == SegmentType.rally,
            CaptureSegment.edit_status == EditStatus.active,
        )
        .all()
    )
    ordered = sorted(
        existing,
        key=lambda segment: (_eff_start(segment), _eff_end(segment) or 2**63, segment.id),
    )

    if mode == "whole_take":
        anchor_index = 0
    else:
        anchor_index = next(
            (index for index, segment in enumerate(ordered) if segment.id == anchor_segment_id),
            None,
        )
        if anchor_index is None:
            raise ValueError("当前分不存在、不是 rally 或已被排除，无法修正序号")

        preserved_ordinals = {segment.ordinal for segment in ordered[:anchor_index]}
        requested_ordinals = range(start_ordinal, start_ordinal + len(ordered) - anchor_index)
        collision = next((ordinal for ordinal in requested_ordinals if ordinal in preserved_ordinals), None)
        if collision is not None:
            raise ValueError(f"第{collision}分已存在于当前分之前，请输入不重复的起始序号")

    changes: list[dict[str, int | str | None]] = []
    changed_ids: list[str] = []
    now = datetime.now(UTC)
    for offset, segment in enumerate(ordered[anchor_index:]):
        next_ordinal = start_ordinal + offset
        previous_ordinal = segment.ordinal
        previous_label = segment.label
        next_label = previous_label
        if _DEFAULT_RALLY_LABEL.fullmatch((previous_label or "").strip()):
            next_label = f"第{next_ordinal}分"

        if previous_ordinal == next_ordinal and previous_label == next_label:
            continue

        segment.ordinal = next_ordinal
        segment.label = next_label
        segment.edit_version += 1
        segment.updated_at = now
        changed_ids.append(segment.id)
        changes.append(
            {
                "segment_id": segment.id,
                "from_ordinal": previous_ordinal,
                "to_ordinal": next_ordinal,
                "from_label": previous_label,
                "to_label": next_label,
            }
        )

    operation_id: str | None = None
    if changes:
        operation_id = _gen_id(_OP_PREFIX)
        _create_op(
            db,
            operation_id,
            capture_take_id,
            EditOperationType.ordinal_renumber,
            changed_ids,
            changed_ids,
            {
                "schema_version": RALLY_ORDINAL_UPDATE_SCHEMA_VERSION,
                "operation": "manual_rally_ordinal_renumber",
                "mode": mode,
                "anchor_segment_id": anchor_segment_id,
                "start_ordinal": start_ordinal,
                "changes": changes,
            },
        )

    db.flush()
    return ordered, operation_id


def review_rally_boundary(
    db: Session,
    segment: CaptureSegment,
    *,
    decision: BoundaryReviewDecision,
    expected_version: int,
    start_ms: int | None = None,
    end_ms: int | None = None,
    note: str | None = None,
    take_duration_ms: int | None = None,
) -> CaptureSegment:
    """复核一个 rally，保留原始边界并写入现有编辑审计表。"""

    if segment.segment_type != SegmentType.rally:
        raise ValueError("仅支持复核 rally 类型")
    if segment.edit_status == EditStatus.superseded:
        raise ValueError("已被替代的 rally 不能复核")
    if segment.edit_version != expected_version:
        raise ValueError(f"edit_version 冲突: 期望 {expected_version}，当前 {segment.edit_version}")
    if decision != BoundaryReviewDecision.excluded and segment.edit_status != EditStatus.active:
        raise ValueError("已排除的 rally 请先恢复后再复核")

    before_start = _eff_start(segment)
    before_end = _eff_end(segment)
    now = datetime.now(UTC)

    if decision == BoundaryReviewDecision.excluded:
        reviewed_start = before_start
        reviewed_end = before_end
        segment.edit_status = EditStatus.archived
    else:
        reviewed_start = before_start if start_ms is None else start_ms
        reviewed_end = before_end if end_ms is None else end_ms
        _validate_candidate_bounds(reviewed_start, reviewed_end, take_duration_ms)
        if reviewed_end is None:
            raise ValueError("开放中的 rally 不能标记为已复核")
        segment.corrected_start_ms = reviewed_start
        segment.corrected_end_ms = reviewed_end
        segment.corrected_at = now
        segment.status = SegmentStatus.corrected

    segment.edit_version += 1
    segment.updated_at = now
    _create_op(
        db,
        _gen_id(_OP_PREFIX),
        segment.capture_take_id,
        EditOperationType.boundary_correction,
        [segment.id],
        [segment.id],
        {
            "schema_version": BOUNDARY_REVIEW_SCHEMA_VERSION,
            "review_status": decision.value,
            "source_start_ms": segment.start_ms,
            "source_end_ms": segment.end_ms,
            "before_start_ms": before_start,
            "before_end_ms": before_end,
            "reviewed_start_ms": reviewed_start,
            "reviewed_end_ms": reviewed_end,
            "note": note or None,
        },
    )
    db.flush()
    return segment


def boundary_review_records(db: Session, capture_take_id: str) -> dict[str, dict]:
    """返回每个 segment 最新的边界复核记录。"""

    operations = (
        db.query(SegmentEditOperation)
        .filter(
            SegmentEditOperation.capture_take_id == capture_take_id,
            SegmentEditOperation.operation_type == EditOperationType.boundary_correction,
        )
        .order_by(SegmentEditOperation.created_at.asc())
        .all()
    )
    latest: dict[str, dict] = {}
    for operation in operations:
        try:
            payload = json.loads(operation.payload_json or "{}")
            segment_ids = json.loads(operation.input_segment_ids or "[]")
        except (TypeError, ValueError):
            continue
        if payload.get("schema_version") != BOUNDARY_REVIEW_SCHEMA_VERSION:
            continue
        for segment_id in segment_ids:
            latest[str(segment_id)] = {
                **payload,
                "operation_id": operation.id,
                "reviewed_at": operation.created_at.isoformat() if operation.created_at else None,
            }
    return latest


def deduplicate_boundary_review_segments(
    segments: list[CaptureSegment], records: dict[str, dict]
) -> tuple[list[CaptureSegment], list[str]]:
    """隐藏不同标注版本产生的近乎完全重叠回合，保留更可信的一条。"""

    kept: list[CaptureSegment] = []
    suppressed_ids: list[str] = []
    for segment in sorted(segments, key=lambda item: (_eff_start(item), _eff_end(item) or 2**63)):
        duplicate_index = next(
            (index for index, current in enumerate(kept) if _near_duplicate_rallies(current, segment)),
            None,
        )
        if duplicate_index is None:
            kept.append(segment)
            continue

        current = kept[duplicate_index]
        if _boundary_review_preference(segment, records) > _boundary_review_preference(current, records):
            kept[duplicate_index] = segment
            suppressed_ids.append(current.id)
        else:
            suppressed_ids.append(segment.id)

    kept.sort(key=lambda item: (_eff_start(item), _eff_end(item) or 2**63))
    return kept, suppressed_ids


def _near_duplicate_rallies(first: CaptureSegment, second: CaptureSegment) -> bool:
    # 用不可变的原始边界判断“标注版本副本”；人工修正可能已让两个副本的有效边界拉开。
    first_end = first.end_ms
    second_end = second.end_ms
    if first_end is None or second_end is None:
        return False

    first_start = first.start_ms
    second_start = second.start_ms
    if abs(first_start - second_start) <= 250 and abs(first_end - second_end) <= 250:
        return True

    overlap = max(0, min(first_end, second_end) - max(first_start, second_start))
    union = max(first_end, second_end) - min(first_start, second_start)
    return union > 0 and overlap / union >= 0.95


def _boundary_review_preference(segment: CaptureSegment, records: dict[str, dict]) -> tuple[int, ...]:
    review_status = str((records.get(segment.id) or {}).get("review_status") or "pending")
    review_rank = {"corrected": 4, "confirmed": 3, "pending": 2, "excluded": 1}.get(review_status, 0)
    source_rank = {
        SegmentSource.corrected: 4,
        SegmentSource.manual: 3,
        SegmentSource.vidat_import: 2,
        SegmentSource.algorithm: 1,
    }.get(segment.source, 0)
    return (
        review_rank,
        source_rank,
        int(segment.annotation_package_id is None),
        int(segment.parent_segment_id is not None),
        segment.edit_version,
    )


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
    _validate_candidate_bounds(_eff_start(seg), _eff_end(seg), take_duration_ms)


def _validate_candidate_bounds(start: int, end: int | None, take_duration_ms: int | None) -> None:
    if start < 0:
        raise ValueError("effective_start_ms 不能小于 0")
    if end is not None:
        if end <= start:
            raise ValueError("effective_end_ms 必须大于 effective_start_ms")
        if end - start < _MIN_RALLY_MS:
            raise ValueError(f"片段时长不能小于 {_MIN_RALLY_MS}ms")
        if take_duration_ms is not None and take_duration_ms >= 0 and end > take_duration_ms:
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
