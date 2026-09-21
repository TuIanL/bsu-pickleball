"""CourtEndProjection 服务层 —— 与计分 reducer 分离的端位回放。

设计要点（对应 design.md Decision 3）：

- 投影以**用户确认的初始 A/B 端位**为种子，按 action ledger 重放有效 `change_side`
  切换 Team A/B 的 near/far。它不进入 `ScoringState`：计分 reducer 继续只负责
  比分、发球权、计分阶段与发球站位。
- 端位确认是 **Job 级一次**：确认一次即写入本 take 的有效种子，之后由换边回放。
- 局边界若没有显式 `change_side`，投影**继续继承**上一端位，同时写结构化诊断
  `game_boundary_without_explicit_side_change`；不静默假装用户确认过。
- 历史 take 缺少初始端位确认时，投影状态为 `unavailable`
  （reason `initial_court_end_not_confirmed`），绝不猜测端位。

术语澄清：`change_side` action 的 `payload_json` 为空，事件也不记录方向，因此投影
只能把它当作"翻转开关"使用 —— 这与 spec「读取有效 `side_change` action 切换
A/B near/far」一致。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.capture_coding_action import CodingActionStatus
from app.models.rally_context import CourtEndConfirmation
from app.models.timeline_event import SessionTimelineEvent, TimelineEventType
from app.schemas.rally_context import (
    REASON_INITIAL_COURT_END_NOT_CONFIRMED,
    REASON_NO_CAPTURE_TAKE,
    CourtEndDiagnostic,
    CourtEndProjectionPayload,
    CourtEndWindow,
)
from app.services import capture_coding_action_service as coding_svc

_ID_PREFIX = "cec"

DIAG_GAME_BOUNDARY_WITHOUT_SIDE_CHANGE = "game_boundary_without_explicit_side_change"
DIAG_SIDE_CHANGE_EVENT_UNRESOLVED = "side_change_event_unresolved"

END_A = "end_a"
END_B = "end_b"


def _generate_id() -> str:
    return f"{_ID_PREFIX}_{uuid4().hex[:12]}"


def owner_key_for(capture_take_id: str | None = None, video_id: str | None = None) -> str:
    """端位确认与名册的归属键：优先录制单元，其次视频。"""
    if capture_take_id:
        return capture_take_id
    if video_id:
        return f"video:{video_id}"
    raise ValueError("owner_key 需要 capture_take_id 或 video_id 之一")


def flip_end(end: str) -> str:
    return END_B if end == END_A else END_A


# ── 确认写入 ──


def confirm_initial_court_end(
    db: Session,
    *,
    capture_take_id: str | None,
    video_id: str | None,
    team_a_end: str,
    confirmed_at_ms: int = 0,
    job_id: str | None = None,
    confirmed_by: str = "manual",
) -> CourtEndConfirmation:
    """确认（或重新确认）Team A 的初始端位；旧确认转非 effective 并保留历史。"""
    if team_a_end not in (END_A, END_B):
        raise ValueError(f"未知端位 {team_a_end!r}，只能是 {END_A} 或 {END_B}")
    owner_key = owner_key_for(capture_take_id, video_id)
    now = datetime.now(UTC)
    previous = (
        db.query(CourtEndConfirmation)
        .filter(CourtEndConfirmation.owner_key == owner_key, CourtEndConfirmation.is_effective.is_(True))
        .all()
    )
    next_revision = 1
    for row in previous:
        next_revision = max(next_revision, row.revision + 1)
        row.is_effective = False
    if previous:
        db.flush()
    row = CourtEndConfirmation(
        id=_generate_id(),
        owner_key=owner_key,
        capture_take_id=capture_take_id,
        video_id=video_id,
        team_a_end=team_a_end,
        confirmed_at_ms=confirmed_at_ms,
        revision=next_revision,
        is_effective=True,
        confirmed_by=confirmed_by,
        job_id=job_id,
        created_at=now,
    )
    db.add(row)
    db.flush()
    return row


def get_effective_court_end_confirmation(db: Session, owner_key: str) -> CourtEndConfirmation | None:
    rows = (
        db.query(CourtEndConfirmation)
        .filter(CourtEndConfirmation.owner_key == owner_key, CourtEndConfirmation.is_effective.is_(True))
        .all()
    )
    if not rows:
        return None
    return max(rows, key=lambda item: item.revision)


# ── 投影构建 ──


def _effective_actions(db: Session, capture_take_id: str) -> list:
    actions = [
        action
        for action in coding_svc.list_actions_for_take(db, capture_take_id)
        if action.status == CodingActionStatus.executed
    ]
    actions.sort(key=lambda action: (action.revision_before, action.created_at))
    return actions


def _created_event_ids(action) -> list[str]:
    raw = getattr(action, "result_json", None)
    try:
        payload = json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        return []
    created = payload.get("created_events")
    return [str(item) for item in created] if isinstance(created, list) else []


def _resolve_side_change_event_id(db: Session, action) -> str | None:
    """把 `change_side` action 解析为它创建的 `side_change` 事件 id。

    `_handle_change_side()` 把该事件放在 `created_events[0]`，这里仍按事件类型校验，
    避免依赖列表顺序。
    """
    event_ids = _created_event_ids(action)
    if not event_ids:
        return None
    events = db.query(SessionTimelineEvent).filter(SessionTimelineEvent.id.in_(event_ids)).all()
    for event in events:
        if event.event_type == TimelineEventType.side_change and not event.is_undone:
            return event.id
    return None


def _unavailable(capture_take_id: str, reason: str, *, diagnostics: list[CourtEndDiagnostic] | None = None):
    return CourtEndProjectionPayload(
        capture_take_id=capture_take_id,
        status="unavailable",
        unavailable_reason=reason,
        diagnostics=diagnostics or [],
    )


def build_court_end_projection(
    db: Session,
    *,
    capture_take_id: str | None,
    owner_key: str | None = None,
    initial_team_a_end: str | None = None,
) -> CourtEndProjectionPayload:
    """从确认的初始端位 + 有效 `side_change` 回放 A/B 端位。

    ``initial_team_a_end`` 仅用于 Job 创建前的纯规划：此时用户提交的端位
    还没有写入数据库，不能为了构造签名而先产生副作用。若未传入，仍读取
    owner 当前有效确认，保持历史调用兼容。
    """
    if not capture_take_id:
        return _unavailable("", REASON_NO_CAPTURE_TAKE)

    key = owner_key or owner_key_for(capture_take_id=capture_take_id)
    confirmation = get_effective_court_end_confirmation(db, key)
    seed_team_a_end = initial_team_a_end or (confirmation.team_a_end if confirmation else None)
    if seed_team_a_end not in (END_A, END_B):
        return _unavailable(capture_take_id, REASON_INITIAL_COURT_END_NOT_CONFIRMED)

    diagnostics: list[CourtEndDiagnostic] = []
    actions = _effective_actions(db, capture_take_id)

    windows: list[CourtEndWindow] = [
        CourtEndWindow(
            effective_from_ms=0,
            team_a_end=seed_team_a_end,  # type: ignore[arg-type]
            team_b_end=flip_end(seed_team_a_end),  # type: ignore[arg-type]
        )
    ]
    current_team_a_end = seed_team_a_end

    game_end_count = 0
    saw_side_change_in_current_game = False
    # 局边界标记：优先用 `start_game`（权威的"新一局开始"），没有足够 `start_game`
    # 时退化为 `end_game`/`end_set`。两条路径都不改动端位，只用于诊断。
    boundaries = [action for action in actions if action.action_type == "start_game"]
    if len(boundaries) < 2:
        boundaries = [action for action in actions if action.action_type in ("end_game", "end_set")]
    boundary_ids = {action.id: index for index, action in enumerate(boundaries)}

    for action in actions:
        if action.action_type == "change_side":
            current_team_a_end = flip_end(current_team_a_end)
            event_id = _resolve_side_change_event_id(db, action)
            if event_id is None:
                diagnostics.append(
                    CourtEndDiagnostic(
                        code=DIAG_SIDE_CHANGE_EVENT_UNRESOLVED,
                        detail="change_side action 未能解析到有效的 side_change 事件",
                        timestamp_ms=action.timestamp_ms,
                    )
                )
            windows.append(
                CourtEndWindow(
                    effective_from_ms=action.timestamp_ms,
                    team_a_end=current_team_a_end,  # type: ignore[arg-type]
                    team_b_end=flip_end(current_team_a_end),  # type: ignore[arg-type]
                    source_action_id=action.id,
                    source_event_id=event_id,
                )
            )
            saw_side_change_in_current_game = True
        elif action.id in boundary_ids:
            index = boundary_ids[action.id]
            # 第 0 个边界是"比赛开局"，不需要换边；其后每个边界必须显式换边，
            # 否则沿用上一局的投影结果并记录诊断（不静默假装用户确认过）。
            if index > 0 and not saw_side_change_in_current_game:
                diagnostics.append(
                    CourtEndDiagnostic(
                        code=DIAG_GAME_BOUNDARY_WITHOUT_SIDE_CHANGE,
                        detail="局边界没有显式换边，端位沿用上一局的投影结果",
                        game_ordinal=index + 1,
                        timestamp_ms=action.timestamp_ms,
                    )
                )
            saw_side_change_in_current_game = False

    return CourtEndProjectionPayload(
        capture_take_id=capture_take_id,
        status="available",
        initial_team_a_end=seed_team_a_end,  # type: ignore[arg-type]
        initial_confirmed_at_ms=confirmation.confirmed_at_ms if confirmation else 0,
        windows=windows,
        diagnostics=diagnostics,
    )
