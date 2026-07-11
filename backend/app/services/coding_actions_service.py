"""Coding Actions 服务层 —— 层级编码操作的语义命令处理。"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.capture_take import CaptureTake, CaptureTakeStatus
from app.models.capture_coding_action import CaptureCodingAction
from app.models.live_coding_state import LiveCodingState
from app.models.timeline_event import SessionTimelineEvent
from app.models.capture_segment import CaptureSegment, EditStatus, SegmentStatus

from app.services import capture_take_service
from app.services import capture_coding_action_service as coding_svc
from app.services import live_coding_state_service as state_svc
from app.services import capture_segment_service as seg_svc
from app.services import timeline_event_service as event_svc

# ── 公开 action 列表 ──

VALID_ACTIONS = frozenset({
    "start_set", "start_game", "start_next_rally",
    "end_rally", "end_game", "end_set",
    "toggle_non_play", "start_timeout", "change_side", "add_note", "undo",
})

# ── 主入口 ──


def execute_coding_action(
    db: Session,
    capture_take_id: str,
    *,
    action: str,
    client_action_id: str,
    expected_revision: int,
    timestamp_ms: int,
    payload: dict | None = None,
) -> dict:
    take = capture_take_service.get_capture_take(db, capture_take_id)
    if take is None:
        raise ValueError(f"CaptureTake {capture_take_id} 不存在")
    if take.status != CaptureTakeStatus.recording:
        raise ValueError(f"CaptureTake {capture_take_id} 不在录制中")

    # 幂等检查
    existing = coding_svc.find_existing_action(db, capture_take_id, client_action_id)
    if existing:
        req_hash = coding_svc.compute_request_hash(action, payload or {})
        if existing.request_hash != req_hash:
            raise ValueError("duplicate_action_mismatched_payload")
        state = state_svc.get_state(db, capture_take_id)
        return _with_snapshot(db, take, {
            "revision": existing.revision_after or existing.revision_before,
            "created_events": [],
            "updated_segments": [],
            "live_state": state_svc.state_to_dict(state) if state else _empty_state(),
            "duplicate": True,
        })

    # revision 冲突检查
    if take.revision != expected_revision:
        state = state_svc.get_state(db, capture_take_id)
        return {
            "error": "revision_conflict",
            "current_revision": take.revision,
            "live_state": state_svc.state_to_dict(state) if state else _empty_state(),
        }

    # 时间戳合理性校验（宽松模式：允许任意正值，仅否定负值）
    if timestamp_ms < 0:
        raise ValueError(f"时间戳 {timestamp_ms} 不能为负")

    with db.begin_nested():
        result = _apply_action(db, take, action, client_action_id, timestamp_ms, payload or {})
        db.flush()
    return result


# ── 内部 action 处理 ──


def _empty_state() -> dict:
    return {"revision": 0, "set_ordinal": 0, "game_ordinal": 0, "rally_ordinal": 0, "non_play": False}


def _ensure_state(db: Session, take: CaptureTake) -> LiveCodingState:
    state = state_svc.get_state(db, take.id)
    if state is None:
        state = state_svc.init_state(db, take.id)
    return state


def _apply_action(
    db: Session,
    take: CaptureTake,
    action: str,
    client_action_id: str,
    timestamp_ms: int,
    payload: dict,
) -> dict:
    state = _ensure_state(db, take)
    request_hash = coding_svc.compute_request_hash(action, payload)
    action_record = coding_svc.create_action_record(
        db,
        capture_take_id=take.id,
        client_action_id=client_action_id,
        action_type=action,
        timestamp_ms=timestamp_ms,
        payload_json=payload,
        request_hash=request_hash,
        revision_before=take.revision,
    )

    created_events: list[dict] = []
    updated_segments: list[dict] = []

    if action == "start_set":
        created_events, updated_segments = _handle_start_set(db, take, state, timestamp_ms)
    elif action == "start_game":
        created_events, updated_segments = _handle_start_game(db, take, state, timestamp_ms)
    elif action == "start_next_rally":
        created_events, updated_segments = _handle_start_next_rally(db, take, state, timestamp_ms)
    elif action == "end_rally":
        created_events, updated_segments = _handle_end_rally(db, take, state, timestamp_ms, "between_rallies")
    elif action == "end_game":
        created_events, updated_segments = _handle_end_level(db, take, state, timestamp_ms, "game")
    elif action == "end_set":
        created_events, updated_segments = _handle_end_level(db, take, state, timestamp_ms, "set")
    elif action == "toggle_non_play":
        created_events, updated_segments = _handle_toggle_non_play(db, take, state, timestamp_ms)
    elif action == "start_timeout":
        created_events, updated_segments = _handle_end_rally(db, take, state, timestamp_ms, "timeout")
    elif action == "change_side":
        created_events, updated_segments = _handle_change_side(db, take, state, timestamp_ms)
    elif action == "add_note":
        created_events, updated_segments = _handle_add_note(db, take, timestamp_ms, payload)
    elif action == "undo":
        created_events, updated_segments = _handle_undo(db, take, state, timestamp_ms, action_record)

    new_revision = take.revision + 1
    take.revision = new_revision
    state.revision = new_revision
    take.updated_at = datetime.now(timezone.utc)

    result_json = json.dumps({
        "created_events": [e["id"] for e in created_events],
        "updated_segments": [s["id"] for s in updated_segments],
    }, ensure_ascii=False)

    coding_svc.complete_action_record(
        db, action_record,
        revision_after=new_revision,
        result_json=result_json,
    )

    return _with_snapshot(db, take, {
        "revision": new_revision,
        "created_events": created_events,
        "updated_segments": updated_segments,
        "live_state": state_svc.state_to_dict(state),
    })


# ── Action handlers ──


def _close_all_open(
    db: Session, take: CaptureTake, timestamp_ms: int
) -> tuple[list[dict], list[dict]]:
    """关闭所有 open 的 rally、game、set，返回 (events, segments)。"""
    events: list[dict] = []
    segments: list[dict] = []
    open_segs = seg_svc.get_open_segments_for_take(db, take.id)
    # 按类型倒序关闭：先 rally → game → set
    type_order = {"rally": 2, "game": 1, "set": 0}
    open_segs.sort(key=lambda s: -type_order.get(s.segment_type.value, 0))
    for seg in open_segs:
        end_type = f"{seg.segment_type.value}_end"
        event = event_svc._add_timeline_event(
            db, take.field_session_id, end_type,
            capture_take_id=take.id, timestamp_ms=timestamp_ms,
        )
        seg_svc.close_segment(db, seg, end_ms=timestamp_ms, end_event_id=event.id,
                              status="closed", close_reason="user_action")
        events.append(_event_to_dict(event))
        segments.append(_segment_to_dict(seg))
    return events, segments


def _handle_start_set(
    db: Session, take: CaptureTake, state: LiveCodingState, timestamp_ms: int
) -> tuple[list[dict], list[dict]]:
    events, segments = _close_all_open(db, take, timestamp_ms)
    events.extend(_close_intermission(db, take, state, timestamp_ms))

    event = event_svc._add_timeline_event(
        db, take.field_session_id, "set_start",
        capture_take_id=take.id, timestamp_ms=timestamp_ms,
    )
    seg = seg_svc.create_segment(
        db, capture_take_id=take.id, segment_type="set",
        ordinal=state.set_ordinal + 1, start_ms=timestamp_ms,
        start_event_id=event.id, label=f"第{state.set_ordinal + 1}盘",
    )
    events.append(_event_to_dict(event))
    segments.append(_segment_to_dict(seg))

    state_svc.upsert_state(db, take.id, revision=take.revision,
                           set_ordinal=state.set_ordinal + 1, game_ordinal=0, rally_ordinal=0, match_phase="idle",
                           current_set_segment_id=seg.id)
    return events, segments


def _handle_start_game(
    db: Session, take: CaptureTake, state: LiveCodingState, timestamp_ms: int
) -> tuple[list[dict], list[dict]]:
    events: list[dict] = []
    segments: list[dict] = []
    events.extend(_close_intermission(db, take, state, timestamp_ms))

    # 关闭所有 open rally
    open_ev, open_sg = _close_open_by_type(db, take, timestamp_ms, "rally")
    events.extend(open_ev)
    segments.extend(open_sg)

    # 关闭 open game（如果有）
    open_game_ev, open_game_sg = _close_open_by_type(db, take, timestamp_ms, "game")
    events.extend(open_game_ev)
    segments.extend(open_game_sg)

    # 缺 set 创建 inferred
    if state.set_ordinal == 0:
        ev = event_svc._add_timeline_event(
            db, take.field_session_id, "set_start",
            capture_take_id=take.id, timestamp_ms=timestamp_ms, source="algorithm",
        )
        set_seg = seg_svc.create_segment(
            db, capture_take_id=take.id, segment_type="set",
            ordinal=1, start_ms=timestamp_ms, start_event_id=ev.id,
            label="第1盘", source="algorithm",
        )
        seg_svc.close_segment(db, set_seg, end_ms=timestamp_ms, status="inferred", close_reason="inferred_parent")
        state.set_ordinal = 1
        state.current_set_segment_id = set_seg.id
        events.append(_event_to_dict(ev))
        segments.append(_segment_to_dict(set_seg))

    event = event_svc._add_timeline_event(
        db, take.field_session_id, "game_start",
        capture_take_id=take.id, timestamp_ms=timestamp_ms,
    )
    seg = seg_svc.create_segment(
        db, capture_take_id=take.id, segment_type="game",
        ordinal=state.game_ordinal + 1, start_ms=timestamp_ms,
        start_event_id=event.id, label=f"第{state.game_ordinal + 1}局",
        parent_segment_id=state.current_set_segment_id,
    )
    events.append(_event_to_dict(event))
    segments.append(_segment_to_dict(seg))

    state_svc.upsert_state(db, take.id, revision=take.revision,
                           set_ordinal=state.set_ordinal, game_ordinal=state.game_ordinal + 1,
                           rally_ordinal=0, non_play=False, match_phase="idle",
                           current_game_segment_id=seg.id,
                           current_set_segment_id=state.current_set_segment_id)
    return events, segments


def _handle_start_next_rally(
    db: Session, take: CaptureTake, state: LiveCodingState, timestamp_ms: int
) -> tuple[list[dict], list[dict]]:
    events: list[dict] = []
    segments: list[dict] = []

    if seg_svc.get_open_segment_by_type(db, take.id, "rally") is not None:
        raise ValueError("当前分尚未结束，请先结束当前分")

    # 缺 game 创建 inferred
    if state.game_ordinal == 0:
        # 缺 set 创建 inferred
        if state.set_ordinal == 0:
            ev = event_svc._add_timeline_event(
                db, take.field_session_id, "set_start",
                capture_take_id=take.id, timestamp_ms=timestamp_ms, source="algorithm",
            )
            set_seg = seg_svc.create_segment(
                db, capture_take_id=take.id, segment_type="set",
                ordinal=1, start_ms=timestamp_ms, start_event_id=ev.id,
                label="第1盘", source="algorithm",
            )
            seg_svc.close_segment(db, set_seg, end_ms=timestamp_ms, status="inferred", close_reason="inferred_parent")
            state.set_ordinal = 1
            state.current_set_segment_id = set_seg.id
            events.append(_event_to_dict(ev))
            segments.append(_segment_to_dict(set_seg))

        ev = event_svc._add_timeline_event(
            db, take.field_session_id, "game_start",
            capture_take_id=take.id, timestamp_ms=timestamp_ms, source="algorithm",
        )
        game_seg = seg_svc.create_segment(
            db, capture_take_id=take.id, segment_type="game",
            ordinal=1, start_ms=timestamp_ms, start_event_id=ev.id,
            label="第1局", source="algorithm",
            parent_segment_id=state.current_set_segment_id,
        )
        seg_svc.close_segment(db, game_seg, end_ms=timestamp_ms, status="inferred", close_reason="inferred_parent")
        state.game_ordinal = 1
        state.current_game_segment_id = game_seg.id
        events.append(_event_to_dict(ev))
        segments.append(_segment_to_dict(game_seg))

    if state.non_play:
        ev = event_svc._add_timeline_event(
            db, take.field_session_id, "non_play_end",
            capture_take_id=take.id, timestamp_ms=timestamp_ms,
            payload_json={"intermission_kind": getattr(state, "intermission_kind", None) or "between_rallies"},
        )
        events.append(_event_to_dict(ev))
        state.non_play = False

    event = event_svc._add_timeline_event(
        db, take.field_session_id, "rally_start",
        capture_take_id=take.id, timestamp_ms=timestamp_ms,
    )
    seg = seg_svc.create_segment(
        db, capture_take_id=take.id, segment_type="rally",
        ordinal=state.rally_ordinal + 1, start_ms=timestamp_ms,
        start_event_id=event.id, label=f"第{state.rally_ordinal + 1}分",
        parent_segment_id=state.current_game_segment_id,
    )
    events.append(_event_to_dict(event))
    segments.append(_segment_to_dict(seg))

    state_svc.upsert_state(db, take.id, revision=take.revision,
                           set_ordinal=state.set_ordinal, game_ordinal=state.game_ordinal,
                           rally_ordinal=state.rally_ordinal + 1, non_play=False, match_phase="rally_active",
                           current_rally_segment_id=seg.id,
                           current_game_segment_id=state.current_game_segment_id,
                           current_set_segment_id=state.current_set_segment_id)
    return events, segments


def _handle_end_level(
    db: Session, take: CaptureTake, state: LiveCodingState, timestamp_ms: int, level: str
) -> tuple[list[dict], list[dict]]:
    events: list[dict] = []
    segments: list[dict] = []
    events.extend(_close_intermission(db, take, state, timestamp_ms))

    if level == "set":
        ev, sg = _close_open_by_type(db, take, timestamp_ms, "rally")
        events.extend(ev); segments.extend(sg)
        ev, sg = _close_open_by_type(db, take, timestamp_ms, "game")
        events.extend(ev); segments.extend(sg)
        ev, sg = _close_open_by_type(db, take, timestamp_ms, "set")
        events.extend(ev); segments.extend(sg)
    elif level == "game":
        ev, sg = _close_open_by_type(db, take, timestamp_ms, "rally")
        events.extend(ev); segments.extend(sg)
        ev, sg = _close_open_by_type(db, take, timestamp_ms, "game")
        events.extend(ev); segments.extend(sg)
    else:  # rally
        ev, sg = _close_open_by_type(db, take, timestamp_ms, "rally")
        events.extend(ev); segments.extend(sg)

    state_svc.upsert_state(db, take.id, revision=take.revision, set_ordinal=state.set_ordinal,
        game_ordinal=state.game_ordinal, rally_ordinal=state.rally_ordinal, non_play=False,
        match_phase="idle", current_set_segment_id=state.current_set_segment_id,
        current_game_segment_id=state.current_game_segment_id, current_rally_segment_id=None)
    return events, segments


def _handle_toggle_non_play(
    db: Session, take: CaptureTake, state: LiveCodingState, timestamp_ms: int
) -> tuple[list[dict], list[dict]]:
    events: list[dict] = []
    segments: list[dict] = []

    if state.non_play:
        # 结束 non_play
        event = event_svc._add_timeline_event(
            db, take.field_session_id, "non_play_end",
            capture_take_id=take.id, timestamp_ms=timestamp_ms,
            payload_json={"intermission_kind": getattr(state, "intermission_kind", None) or "between_rallies"},
        )
        events.append(_event_to_dict(event))
        state.non_play = False
    else:
        # 开启 non_play：关闭 rally 但保留 set/game
        ev, sg = _close_open_by_type(db, take, timestamp_ms, "rally")
        events.extend(ev); segments.extend(sg)
        event = event_svc._add_timeline_event(
            db, take.field_session_id, "non_play_start",
            capture_take_id=take.id, timestamp_ms=timestamp_ms,
            payload_json={"intermission_kind": "between_rallies"},
        )
        events.append(_event_to_dict(event))
        state.non_play = True

    state_svc.upsert_state(db, take.id, revision=take.revision,
                           set_ordinal=state.set_ordinal, game_ordinal=state.game_ordinal,
                           rally_ordinal=state.rally_ordinal, non_play=state.non_play,
                           match_phase="intermission" if state.non_play else "idle",
                           intermission_kind="between_rallies" if state.non_play else None,
                           current_set_segment_id=state.current_set_segment_id,
                           current_game_segment_id=state.current_game_segment_id,
                           current_rally_segment_id=state.current_rally_segment_id if not state.non_play else None)
    return events, segments


def _handle_change_side(
    db: Session, take: CaptureTake, state: LiveCodingState, timestamp_ms: int
) -> tuple[list[dict], list[dict]]:
    events, segments = _handle_end_rally(db, take, state, timestamp_ms, "side_change")
    event = event_svc._add_timeline_event(
        db, take.field_session_id, "side_change",
        capture_take_id=take.id, timestamp_ms=timestamp_ms,
    )
    return [_event_to_dict(event), *events], segments


def _handle_end_rally(
    db: Session, take: CaptureTake, state: LiveCodingState, timestamp_ms: int, kind: str
) -> tuple[list[dict], list[dict]]:
    events, segments = _close_open_by_type(db, take, timestamp_ms, "rally")
    if state.non_play:
        end = event_svc._add_timeline_event(db, take.field_session_id, "non_play_end", capture_take_id=take.id,
            timestamp_ms=timestamp_ms, payload_json={"intermission_kind": getattr(state, "intermission_kind", None) or "between_rallies"})
        events.append(_event_to_dict(end))
    start = event_svc._add_timeline_event(db, take.field_session_id, "non_play_start", capture_take_id=take.id,
        timestamp_ms=timestamp_ms, payload_json={"intermission_kind": kind})
    events.append(_event_to_dict(start))
    state_svc.upsert_state(db, take.id, revision=take.revision, set_ordinal=state.set_ordinal,
        game_ordinal=state.game_ordinal, rally_ordinal=state.rally_ordinal, non_play=True,
        match_phase="intermission", intermission_kind=kind, current_set_segment_id=state.current_set_segment_id,
        current_game_segment_id=state.current_game_segment_id, current_rally_segment_id=None)
    return events, segments


def _close_intermission(db: Session, take: CaptureTake, state: LiveCodingState, timestamp_ms: int) -> list[dict]:
    if not state.non_play:
        return []
    event = event_svc._add_timeline_event(
        db, take.field_session_id, "non_play_end", capture_take_id=take.id, timestamp_ms=timestamp_ms,
        payload_json={"intermission_kind": getattr(state, "intermission_kind", None) or "between_rallies"},
    )
    state.non_play = False
    state.intermission_kind = None
    return [_event_to_dict(event)]


def _with_snapshot(db: Session, take: CaptureTake, result: dict) -> dict:
    events = event_svc.list_timeline_events(db, take.field_session_id, capture_take_id=take.id)
    segments = seg_svc.list_segments(db, take.id)
    result["timeline_events"] = [_event_to_dict(event) for event in events]
    result["segments"] = [_segment_to_dict(segment) for segment in segments]
    return result


def _handle_add_note(
    db: Session, take: CaptureTake, timestamp_ms: int, payload: dict
) -> tuple[list[dict], list[dict]]:
    event = event_svc._add_timeline_event(
        db, take.field_session_id,
        event_type=payload.get("event_type", "session_note"),
        capture_take_id=take.id, timestamp_ms=timestamp_ms,
        note=payload.get("note", ""), label=payload.get("label", ""),
        payload_json=payload.get("payload", {}),
    )
    return [_event_to_dict(event)], []


def _handle_undo(
    db: Session, take: CaptureTake, state: LiveCodingState, timestamp_ms: int, undo_action: CaptureCodingAction
) -> tuple[list[dict], list[dict]]:
    last = coding_svc.get_last_undoable_action(db, take.id)
    if last is None:
        raise ValueError("没有可撤销的操作")
    coding_svc.mark_action_undone(db, last)
    undo_action.reverses_action_id = last.id

    try:
        result = json.loads(last.result_json or "{}")
    except json.JSONDecodeError:
        result = {}
    event_ids = result.get("created_events", [])
    if event_ids:
        affected_events = db.query(SessionTimelineEvent).filter(SessionTimelineEvent.id.in_(event_ids)).all()
        for event in affected_events:
            event.is_undone = True

        affected_segments = db.query(CaptureSegment).filter(
            CaptureSegment.capture_take_id == take.id
        ).all()
        for segment in affected_segments:
            if segment.start_event_id in event_ids:
                segment.edit_status = EditStatus.archived
            elif segment.end_event_id in event_ids:
                segment.end_event_id = None
                segment.end_ms = None
                segment.status = SegmentStatus.open

    events: list[dict] = []

    # 标记 undo action 创建的 undo coding action
    undo_event = event_svc._add_timeline_event(
        db, take.field_session_id, "session_note",
        capture_take_id=take.id, timestamp_ms=timestamp_ms,
        note=f"撤销操作: {last.action_type}", source="corrected",
    )
    events.append(_event_to_dict(undo_event))

    _rebuild_projection_state(db, take, state)
    rebuilt = state_svc.get_state(db, take.id)
    return events, [_segment_to_dict(segment) for segment in seg_svc.list_segments(db, take.id)]


def _rebuild_projection_state(db: Session, take: CaptureTake, state: LiveCodingState) -> None:
    """Recompute the live snapshot from the surviving action projection after undo."""
    active_actions = [action for action in coding_svc.list_actions_for_take(db, take.id) if action.status.value == "executed"]
    open_rally = seg_svc.get_open_segment_by_type(db, take.id, "rally")
    active_rallies = seg_svc.list_segments(db, take.id, segment_type="rally")
    active_events = event_svc.list_timeline_events(db, take.field_session_id, capture_take_id=take.id)
    starts = [event for event in active_events if event.event_type.value == "non_play_start"]
    ends = [event for event in active_events if event.event_type.value == "non_play_end"]
    last_start = starts[-1] if starts else None
    last_end = ends[-1] if ends else None
    active_intermission = bool(last_start and (not last_end or last_start.timestamp_ms >= last_end.timestamp_ms))
    kind = "between_rallies"
    if last_start is not None:
        try:
            kind = json.loads(last_start.payload_json or "{}").get("intermission_kind", kind)
        except json.JSONDecodeError:
            pass
    phase = "rally_active" if open_rally else "intermission" if active_intermission else "idle"
    active_sets = seg_svc.list_segments(db, take.id, segment_type="set")
    active_games = seg_svc.list_segments(db, take.id, segment_type="game")
    state_svc.upsert_state(db, take.id, revision=take.revision,
                           set_ordinal=max((segment.ordinal for segment in active_sets), default=0),
                           game_ordinal=max((segment.ordinal for segment in active_games), default=0),
                           rally_ordinal=max((segment.ordinal for segment in active_rallies), default=0),
                           non_play=not bool(open_rally) and active_intermission,
                           match_phase=phase,
                           intermission_kind=kind if active_intermission and not open_rally else None,
                           current_set_segment_id=state.current_set_segment_id,
                           current_game_segment_id=state.current_game_segment_id,
                           current_rally_segment_id=open_rally.id if open_rally else None)


# ── 辅助 ──


def _close_open_by_type(
    db: Session, take: CaptureTake, timestamp_ms: int, segment_type: str
) -> tuple[list[dict], list[dict]]:
    seg = seg_svc.get_open_segment_by_type(db, take.id, segment_type)
    if seg is None:
        return [], []
    end_type = f"{segment_type}_end"
    event = event_svc._add_timeline_event(
        db, take.field_session_id, end_type,
        capture_take_id=take.id, timestamp_ms=timestamp_ms,
    )
    seg_svc.close_segment(db, seg, end_ms=timestamp_ms, end_event_id=event.id,
                          status="closed", close_reason="user_action")
    return [_event_to_dict(event)], [_segment_to_dict(seg)]


def _event_to_dict(ev) -> dict:
    try:
        payload = json.loads(ev.payload_json or "{}")
    except (TypeError, json.JSONDecodeError):
        payload = {}
    return {
        "id": ev.id, "event_type": ev.event_type.value, "label": ev.label,
        "timestamp_ms": ev.timestamp_ms, "source": ev.source.value, "note": ev.note,
        "payload_json": payload, "is_undone": ev.is_undone,
    }


def _segment_to_dict(seg) -> dict:
    return {
        "id": seg.id, "segment_type": seg.segment_type.value,
        "ordinal": seg.ordinal, "start_ms": seg.start_ms, "end_ms": seg.end_ms,
        "status": seg.status.value, "label": seg.label,
    }
