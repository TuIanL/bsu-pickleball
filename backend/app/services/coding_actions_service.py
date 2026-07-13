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


# 执行编码动作命令：校验状态、幂等检查、revision 冲突检测，分发到具体处理器
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

    # 允许 recording 或 completed (宽限期内) 接收事件
    from datetime import datetime, timedelta, timezone
    try:
        from app.core.config import get_settings
        _GRACE_MINUTES = get_settings().capture_take_late_event_grace_minutes
    except Exception:
        _GRACE_MINUTES = 5
    if take.status == CaptureTakeStatus.completed:
        if take.ended_at is None:
            raise ValueError(f"CaptureTake {capture_take_id} 已完成但缺少 ended_at")
        grace_deadline = take.ended_at.replace(tzinfo=timezone.utc) if take.ended_at.tzinfo is None else take.ended_at
        grace_deadline = grace_deadline + timedelta(minutes=_GRACE_MINUTES)
        if datetime.now(timezone.utc) > grace_deadline:
            raise ValueError(f"CaptureTake {capture_take_id} 已完成且超出补传宽限期")
        if not (0 <= timestamp_ms <= (take.duration_ms or 0)):
            raise ValueError(f"timestamp_ms {timestamp_ms} 超出录制时长范围")
    elif take.status != CaptureTakeStatus.recording:
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


# 返回空状态字典（默认值）
def _empty_state() -> dict:
    return {"revision": 0, "set_ordinal": 0, "game_ordinal": 0, "rally_ordinal": 0, "non_play": False}


# 确保 take 存在状态快照，不存在则初始化
def _ensure_state(db: Session, take: CaptureTake) -> LiveCodingState:
    state = state_svc.get_state(db, take.id)
    if state is None:
        state = state_svc.init_state(db, take.id)
    return state


# 核心分发：根据 action 类型调用对应处理器，更新 revision 并持久化结果
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

    result = _with_snapshot(db, take, {
        "revision": new_revision,
        "created_events": created_events,
        "updated_segments": updated_segments,
        "live_state": state_svc.state_to_dict(state),
    })

    # 迟到事件：completed take 收到事件后重投影时间线
    if take.status == CaptureTakeStatus.completed:
        try:
            reproject_coding_timeline(db, capture_take_id)
        except Exception:
            pass

    return result


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


# 处理开始新盘：关闭所有未关闭层级，创建 set 区间，更新状态
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
                           current_set_segment_id=seg.id,
                           current_game_segment_id=None,
                           current_rally_segment_id=None)
    return events, segments


# 处理开始新局：关闭 intermission 与 rally，确保 set 存在，创建 game 区间
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

    current_set = seg_svc.get_segment(db, state.current_set_segment_id) if state.current_set_segment_id else None
    if current_set is None or current_set.edit_status != EditStatus.active or current_set.status != SegmentStatus.open:
        current_set = seg_svc.get_open_segment_by_type(db, take.id, "set")
    if current_set is None:
        ev = event_svc._add_timeline_event(
            db, take.field_session_id, "set_start",
            capture_take_id=take.id, timestamp_ms=timestamp_ms, source="algorithm",
        )
        set_seg = seg_svc.create_segment(
            db, capture_take_id=take.id, segment_type="set",
            ordinal=state.set_ordinal + 1 if state.set_ordinal > 0 else 1,
            start_ms=timestamp_ms, start_event_id=ev.id,
            label=f"第{state.set_ordinal + 1 if state.set_ordinal > 0 else 1}盘", source="algorithm",
        )
        state.set_ordinal = set_seg.ordinal
        state.current_set_segment_id = set_seg.id
        state.game_ordinal = 0
        state.rally_ordinal = 0
        events.append(_event_to_dict(ev))
        segments.append(_segment_to_dict(set_seg))
    else:
        state.current_set_segment_id = current_set.id
        state.set_ordinal = current_set.ordinal

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
                           current_set_segment_id=state.current_set_segment_id,
                           current_rally_segment_id=None)
    return events, segments


# 处理开始新分：确保 game 与 set 存在（必要时自动创建），关闭 intermission，创建 rally 区间
def _handle_start_next_rally(
    db: Session, take: CaptureTake, state: LiveCodingState, timestamp_ms: int
) -> tuple[list[dict], list[dict]]:
    events: list[dict] = []
    segments: list[dict] = []

    if seg_svc.get_open_segment_by_type(db, take.id, "rally") is not None:
        raise ValueError("当前分尚未结束，请先结束当前分")

    # A rally can be the first action in a game. Treat a closed/missing current
    # game as absent even when game_ordinal still contains the previous game.
    current_game = seg_svc.get_segment(db, state.current_game_segment_id) if state.current_game_segment_id else None
    if current_game is None or current_game.edit_status != EditStatus.active or current_game.status != SegmentStatus.open:
        current_game = seg_svc.get_open_segment_by_type(db, take.id, "game")
    if current_game is None:
        current_set = seg_svc.get_segment(db, state.current_set_segment_id) if state.current_set_segment_id else None
        if current_set is None or current_set.edit_status != EditStatus.active or current_set.status != SegmentStatus.open:
            current_set = seg_svc.get_open_segment_by_type(db, take.id, "set")
        if current_set is None:
            ev = event_svc._add_timeline_event(
                db, take.field_session_id, "set_start",
                capture_take_id=take.id, timestamp_ms=timestamp_ms, source="algorithm",
            )
            set_seg = seg_svc.create_segment(
                db, capture_take_id=take.id, segment_type="set",
                ordinal=state.set_ordinal + 1 if state.set_ordinal > 0 else 1,
                start_ms=timestamp_ms, start_event_id=ev.id,
                label=f"第{state.set_ordinal + 1 if state.set_ordinal > 0 else 1}盘", source="algorithm",
            )
            state.set_ordinal = set_seg.ordinal
            state.current_set_segment_id = set_seg.id
            state.game_ordinal = 0
            state.rally_ordinal = 0
            events.append(_event_to_dict(ev))
            segments.append(_segment_to_dict(set_seg))
        else:
            state.current_set_segment_id = current_set.id
            state.set_ordinal = current_set.ordinal

        game_ordinal = state.game_ordinal + 1 if state.game_ordinal > 0 else 1
        ev = event_svc._add_timeline_event(
            db, take.field_session_id, "game_start",
            capture_take_id=take.id, timestamp_ms=timestamp_ms, source="algorithm",
        )
        game_seg = seg_svc.create_segment(
            db, capture_take_id=take.id, segment_type="game",
            ordinal=game_ordinal, start_ms=timestamp_ms, start_event_id=ev.id,
            label=f"第{game_ordinal}局", source="algorithm",
            parent_segment_id=state.current_set_segment_id,
        )
        state.game_ordinal = game_ordinal
        state.rally_ordinal = 0
        state.current_game_segment_id = game_seg.id
        events.append(_event_to_dict(ev))
        segments.append(_segment_to_dict(game_seg))
    else:
        state.current_game_segment_id = current_game.id

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


# 处理结束层级（game/set）：关闭下级所有 open 区间，更新状态进入 intermission
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

    # Ending a game or set enters the same between-play intermission as ending
    # a rally, so the timeline remains gray until the next start action.
    if level in ("game", "set"):
        intermission = event_svc._add_timeline_event(
            db, take.field_session_id, "non_play_start",
            capture_take_id=take.id, timestamp_ms=timestamp_ms,
            payload_json={"intermission_kind": "between_rallies"},
        )
        events.append(_event_to_dict(intermission))

    state_svc.upsert_state(db, take.id, revision=take.revision, set_ordinal=state.set_ordinal,
        game_ordinal=state.game_ordinal, rally_ordinal=state.rally_ordinal,
        non_play=level in ("game", "set"),
        match_phase="intermission" if level in ("game", "set") else "idle",
        intermission_kind="between_rallies" if level in ("game", "set") else None,
        current_set_segment_id=None if level == "set" else state.current_set_segment_id,
        current_game_segment_id=None if level in ("game", "set") else state.current_game_segment_id,
        current_rally_segment_id=None)
    return events, segments


# 处理切换非比赛状态：开启时关闭 rally，关闭时结束 intermission
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


# 处理交换场地：先结束当前 rally，再记录 side_change 事件
def _handle_change_side(
    db: Session, take: CaptureTake, state: LiveCodingState, timestamp_ms: int
) -> tuple[list[dict], list[dict]]:
    events, segments = _handle_end_rally(db, take, state, timestamp_ms, "side_change")
    event = event_svc._add_timeline_event(
        db, take.field_session_id, "side_change",
        capture_take_id=take.id, timestamp_ms=timestamp_ms,
    )
    return [_event_to_dict(event), *events], segments


# 处理结束分：关闭 open rally，开启 intermission（含 kind 标记）
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


# 关闭 intermission：若处于非比赛状态则记录 non_play_end 事件
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


# 在结果中附加时间线事件与区间快照
def _with_snapshot(db: Session, take: CaptureTake, result: dict) -> dict:
    events = event_svc.list_timeline_events(db, take.field_session_id, capture_take_id=take.id)
    segments = seg_svc.list_segments(db, take.id)
    result["timeline_events"] = [_event_to_dict(event) for event in events]
    result["segments"] = [_segment_to_dict(segment) for segment in segments]
    return result


# 处理添加笔记：创建 timeline 笔记事件
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


# 处理撤销：找到最近可撤销动作，恢复事件与区间，重建状态投影
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
        archived_segment_ids: set[str] = set()
        for segment in affected_segments:
            if segment.start_event_id in event_ids:
                segment.edit_status = EditStatus.archived
                archived_segment_ids.add(segment.id)
            elif segment.end_event_id in event_ids:
                segment.end_event_id = None
                segment.end_ms = None
                segment.status = SegmentStatus.open

        # A parent action can leave child segments behind (for example, a game
        # action followed by rallies). Undoing the parent must remove that
        # subtree as well, otherwise later actions can recreate ordinal 1.
        changed = True
        while changed:
            changed = False
            for segment in affected_segments:
                if (
                    segment.edit_status == EditStatus.active
                    and segment.parent_segment_id in archived_segment_ids
                ):
                    segment.edit_status = EditStatus.archived
                    archived_segment_ids.add(segment.id)
                    changed = True

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


# 从剩余有效动作中重算实时状态快照（用于撤销后重建）
def _rebuild_projection_state(db: Session, take: CaptureTake, state: LiveCodingState) -> None:
    active_actions = [action for action in coding_svc.list_actions_for_take(db, take.id) if action.status.value == "executed"]
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
    active_sets = seg_svc.list_segments(db, take.id, segment_type="set")
    active_games = seg_svc.list_segments(db, take.id, segment_type="game")

    def latest(items):
        return max(items, key=lambda segment: (segment.start_ms, segment.created_at)) if items else None

    current_set = latest(active_sets)
    games_in_set = (
        [segment for segment in active_games if segment.parent_segment_id == current_set.id]
        if current_set else active_games
    )
    current_game = latest(games_in_set)
    rallies_in_game = (
        [segment for segment in active_rallies if segment.parent_segment_id == current_game.id]
        if current_game else active_rallies
    )
    open_rallies = [segment for segment in rallies_in_game if segment.status == SegmentStatus.open]
    open_rally = latest(open_rallies)
    phase = "rally_active" if open_rally else "intermission" if active_intermission else "idle"
    state_svc.upsert_state(db, take.id, revision=take.revision,
                           set_ordinal=current_set.ordinal if current_set else 0,
                           game_ordinal=current_game.ordinal if current_game else 0,
                           rally_ordinal=max((segment.ordinal for segment in rallies_in_game), default=0),
                           non_play=not bool(open_rally) and active_intermission,
                           match_phase=phase,
                           intermission_kind=kind if active_intermission and not open_rally else None,
                           current_set_segment_id=current_set.id if current_set else None,
                           current_game_segment_id=current_game.id if current_game else None,
                           current_rally_segment_id=open_rally.id if open_rally else None)


# ── 辅助 ──


# 按类型关闭某层级的 open 区间（如关闭 open rally）
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


# 将 TimelineEvent 对象转换为字典
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


# 将 CaptureSegment 对象转换为字典
def _segment_to_dict(seg) -> dict:
    return {
        "id": seg.id, "segment_type": seg.segment_type.value,
        "ordinal": seg.ordinal, "start_ms": seg.start_ms, "end_ms": seg.end_ms,
        "status": seg.status.value, "label": seg.label,
    }


def reproject_coding_timeline(db, capture_take_id: str) -> None:
    """
    重放全部 CodingAction，重建 TimelineEvent 和 CaptureSegment 派生投影。
    用于迟到事件补传后修正时间线。
    """
    take = capture_take_service.get_capture_take(db, capture_take_id)
    if take is None:
        return

    actions = coding_svc.list_actions_for_take(db, capture_take_id)
    actions.sort(key=lambda a: (a.timestamp_ms, a.sequence_number or 0))

    # 删除旧的 TimelineEvent 和 CaptureSegment 投影
    from app.models.timeline_event import SessionTimelineEvent
    from app.models.capture_segment import CaptureSegment
    db.query(SessionTimelineEvent).filter(
        SessionTimelineEvent.capture_take_id == capture_take_id
    ).delete()
    db.query(CaptureSegment).filter(
        CaptureSegment.capture_take_id == capture_take_id
    ).delete()
    db.flush()

    # 按序重放
    for action in actions:
        try:
            _apply_action_to_timeline(db, take, action)
        except Exception:
            pass

    # 裁剪仍 open 的 segment 到 duration_ms
    duration_ms = take.duration_ms or 0
    if duration_ms > 0:
        open_segs = db.query(CaptureSegment).filter(
            CaptureSegment.capture_take_id == capture_take_id,
            CaptureSegment.end_ms.is_(None),
        ).all()
        for seg in open_segs:
            seg.end_ms = duration_ms
        db.flush()


def _apply_action_to_timeline(db, take, action):
    """将单个 CodingAction 应用到 Timeline/Segment。"""
    from app.models.timeline_event import SessionTimelineEvent, TimelineEventSource
    from app.models.capture_segment import CaptureSegment, SegmentStatus

    payload = action.payload or {}
    event_type = _action_to_event_type(action.action)

    event = SessionTimelineEvent(
        field_session_id=take.field_session_id,
        capture_take_id=take.id,
        recording_session_id=take.source_session_id,
        event_type=event_type,
        source=TimelineEventSource.manual,
        timestamp_ms=action.timestamp_ms,
        note=payload.get("note", ""),
        payload_json=payload,
    )
    db.add(event)
    db.flush()

    if action.action in ("start_game", "start_set", "start_next_rally", "start_rally",
                         "end_rally", "end_game", "end_set"):
        _update_segments_from_action(db, take, action)


# 将 action 类型映射为 timeline 事件类型
def _action_to_event_type(action: str) -> str:
    mapping = {
        "start_set": "set_start", "end_set": "set_end",
        "start_game": "game_start", "end_game": "game_end",
        "start_next_rally": "rally_start", "start_rally": "rally_start",
        "end_rally": "rally_end",
        "toggle_non_play": "non_play_start",
        "change_side": "side_change",
        "add_note": "custom_marker",
        "undo": "custom_marker",
    }
    return mapping.get(action, "custom_marker")


# 根据动作类型创建或关闭 CaptureSegment（用于重放投影）
def _update_segments_from_action(db, take, action):
    from app.models.capture_segment import CaptureSegment, SegmentStatus
    from uuid import uuid4

    payload = action.payload or {}
    now_ms = action.timestamp_ms

    if action.action in ("start_set", "start_game", "start_next_rally", "start_rally"):
        seg_type = "rally" if "rally" in action.action else ("game" if "game" in action.action else "set")
        ordinal = payload.get("ordinal", 0)
        seg = CaptureSegment(
            id=f"seg_{uuid4().hex[:12]}",
            capture_take_id=take.id,
            segment_type=seg_type,
            ordinal=ordinal,
            start_ms=now_ms,
            status=SegmentStatus.inferred,
        )
        db.add(seg)
    elif action.action in ("end_rally", "end_game", "end_set"):
        seg_type = "rally" if "rally" in action.action else ("game" if "game" in action.action else "set")
        segs = db.query(CaptureSegment).filter(
            CaptureSegment.capture_take_id == take.id,
            CaptureSegment.end_ms.is_(None),
            CaptureSegment.segment_type == seg_type,
        ).order_by(CaptureSegment.start_ms.desc()).all()
        if segs:
            segs[0].end_ms = now_ms
