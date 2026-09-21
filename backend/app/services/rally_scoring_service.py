"""RallyScoringSnapshot 服务层 —— 录制期计分事实的封存与重放。

职责边界：

- 在有效 `rally_start` 的**同一事务**内封存仅含计分事实的快照。
- 按有效 action ledger 重放并对账已存在的快照：来源 action 失效 → `undone`；
  派生事实变化 → 追加新 revision 并 `supersede` 旧版本。
- **不为历史 action 凭空补造快照**：老录像从未写过快照，就保持"没有快照"，
  下游读到的是 `no_rally_scoring_snapshots` unavailable，而不是被推测出比分。

快照显式不得引用名册、P1–P4 或分析期端位；端位由 `court_end_projection_service`
独立负责。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.capture_coding_action import CodingActionStatus
from app.models.rally_context import RallyScoringSnapshot, ScoringSnapshotStatus
from app.schemas.rally_context import RallyScoringSnapshotPayload, scoring_snapshot_hash
from app.services import capture_coding_action_service as coding_svc
from app.services.scoring_fsm import (
    HYBRID_21_RULESET,
    ScoringAction,
    ScoringState,
    initial_game_state,
    reduce_scoring_state_for_ruleset,
)

_ID_PREFIX = "rss"

# 这些 action 会改变"计分事实"，因此需要触发一次对账重放。
# `start_next_rally` 不在其中：它的快照刚刚由写入路径产生，无需重放。
SCORING_FACT_AFFECTING_ACTIONS = frozenset(
    {
        "start_game",
        "end_game",
        "end_set",
        "rally_result_a",
        "rally_result_b",
        "rally_replay",
        "correct_score",
        "undo",
    }
)


def _generate_id() -> str:
    return f"{_ID_PREFIX}_{uuid4().hex[:12]}"


def status_of(row: RallyScoringSnapshot) -> str:
    """`status` 列是 VARCHAR，读回来是 `str`；统一成字符串便于比较与序列化。"""
    return row.status.value if hasattr(row.status, "value") else str(row.status)


def _payload_for(row: RallyScoringSnapshot) -> RallyScoringSnapshotPayload:
    return RallyScoringSnapshotPayload(
        snapshot_id=row.id,
        capture_take_id=row.capture_take_id,
        rally_id=row.rally_id or "",
        ordinal=row.ordinal,
        server_team=row.server_team,  # type: ignore[arg-type]
        score_a_before=row.score_a_before,
        score_b_before=row.score_b_before,
        games_won_a_before=row.games_won_a_before,
        games_won_b_before=row.games_won_b_before,
        scoring_phase=row.scoring_phase,
        scoring_ruleset_version=row.scoring_ruleset_version,
        action_id=row.action_id,
        event_id=row.event_id or "",
        action_revision=row.action_revision,
        start_ms=row.start_ms,
        revision=row.revision,
        supersedes_snapshot_id=row.supersedes_snapshot_id,
        status=status_of(row),  # type: ignore[arg-type]
    )


def snapshot_hash_of(row: RallyScoringSnapshot) -> str:
    return scoring_snapshot_hash(_payload_for(row).model_dump(mode="json"))


def to_dict(row: RallyScoringSnapshot) -> dict:
    payload = _payload_for(row).model_dump(mode="json")
    payload["scoring_hash"] = scoring_snapshot_hash(payload)
    return payload


def create_rally_scoring_snapshot(
    db: Session,
    *,
    capture_take_id: str,
    action_id: str,
    event_id: str,
    rally_id: str,
    ordinal: int,
    scoring_state: ScoringState,
    action_revision: int,
    start_ms: int,
    scoring_ruleset_version: str | None,
) -> RallyScoringSnapshot:
    """在 `rally_start` 事务内封存计分事实（仅计分；不含名册与端位）。"""
    row = RallyScoringSnapshot(
        id=_generate_id(),
        capture_take_id=capture_take_id,
        action_id=action_id,
        event_id=event_id,
        rally_id=rally_id,
        ordinal=ordinal,
        server_team=scoring_state.server_team,
        score_a_before=scoring_state.score_a,
        score_b_before=scoring_state.score_b,
        games_won_a_before=scoring_state.games_won_a,
        games_won_b_before=scoring_state.games_won_b,
        scoring_phase=scoring_state.scoring_phase,
        scoring_ruleset_version=scoring_ruleset_version,
        action_revision=action_revision,
        start_ms=start_ms,
        revision=1,
        status=ScoringSnapshotStatus.effective,
        created_at=datetime.now(UTC),
    )
    db.add(row)
    db.flush()
    return row


def list_scoring_snapshots(db: Session, capture_take_id: str) -> list[RallyScoringSnapshot]:
    return (
        db.query(RallyScoringSnapshot)
        .filter(RallyScoringSnapshot.capture_take_id == capture_take_id)
        .order_by(RallyScoringSnapshot.ordinal.asc(), RallyScoringSnapshot.revision.asc())
        .all()
    )


def effective_scoring_snapshots(db: Session, capture_take_id: str) -> list[RallyScoringSnapshot]:
    """每个来源 action 只返回当前 effective 的那一版。"""
    latest: dict[str, RallyScoringSnapshot] = {}
    for row in list_scoring_snapshots(db, capture_take_id):
        if row.status != ScoringSnapshotStatus.effective:
            continue
        current = latest.get(row.action_id)
        if current is None or row.revision > current.revision:
            latest[row.action_id] = row
    return sorted(latest.values(), key=lambda item: (item.ordinal, item.start_ms))


def get_by_rally_id(db: Session, capture_take_id: str, rally_id: str) -> RallyScoringSnapshot | None:
    rows = [
        row
        for row in list_scoring_snapshots(db, capture_take_id)
        if row.rally_id == rally_id and row.status == ScoringSnapshotStatus.effective
    ]
    if not rows:
        return None
    return max(rows, key=lambda item: item.revision)


def find_by_start_event_id(db: Session, capture_take_id: str, event_id: str) -> RallyScoringSnapshot | None:
    rows = [
        row
        for row in list_scoring_snapshots(db, capture_take_id)
        if row.event_id == event_id and row.status == ScoringSnapshotStatus.effective
    ]
    if not rows:
        return None
    return max(rows, key=lambda item: item.revision)


def _mark_snapshot(db: Session, row: RallyScoringSnapshot, status: ScoringSnapshotStatus, *, now: datetime) -> None:
    row.status = status
    row.superseded_at = now
    db.flush()


def _derive_facts(scoring_state: ScoringState) -> dict:
    return {
        "server_team": scoring_state.server_team,
        "score_a_before": scoring_state.score_a,
        "score_b_before": scoring_state.score_b,
        "games_won_a_before": scoring_state.games_won_a,
        "games_won_b_before": scoring_state.games_won_b,
        "scoring_phase": scoring_state.scoring_phase,
    }


def _stored_facts(row: RallyScoringSnapshot) -> dict:
    return {
        "server_team": row.server_team,
        "score_a_before": row.score_a_before,
        "score_b_before": row.score_b_before,
        "games_won_a_before": row.games_won_a_before,
        "games_won_b_before": row.games_won_b_before,
        "scoring_phase": row.scoring_phase,
    }


def _replay_scoring_state(actions: list, ruleset: str | None) -> dict[str, ScoringState]:
    """按有效 action 顺序重放，返回 `start_next_rally action_id -> 该时点计分状态`。

    计分修正的语义（本模块的显式解释，design.md Decision 1 的落地）：

    一个 `correct_score` 是对"当前比分"的重新陈述。它发生在某个回合**尚未产生结果**
    期间时，说明该回合开始时的比分记录本身需要被修正，因此会覆盖该回合的
    before-facts；一旦该回合已经记了结果（`rally_result_*` / `rally_replay`）或已
    经结束（`end_rally` / `end_game` / `change_side` 等），后续改分不再回溯影响它。
    这样既满足"改分重放并 supersede 受影响版本"，又不会把修正滥用到已经沉淀的
    历史回合上。
    """
    state = ScoringState(server_team=None, score_a=0, score_b=0)
    derived: dict[str, ScoringState] = {}
    open_rally_action_id: str | None = None

    for action in actions:
        action_type = action.action_type
        if action_type == "start_game":
            payload = _payload_dict(action)
            initial_server = payload.get("initial_server_team", state.server_team)
            if ruleset == HYBRID_21_RULESET and initial_server in ("A", "B"):
                state = initial_game_state(state, initial_server)
            else:
                state = ScoringState(server_team=initial_server, score_a=0, score_b=0)
            open_rally_action_id = None
        elif action_type in ("end_game", "end_set"):
            if ruleset != HYBRID_21_RULESET:
                state = ScoringState(server_team=None, score_a=0, score_b=0)
            open_rally_action_id = None
        elif action_type in ("rally_result_a", "rally_result_b"):
            winner = "A" if action_type == "rally_result_a" else "B"
            state = reduce_scoring_state_for_ruleset(
                state, ScoringAction(type="rally_result", winner=winner, validity="valid"), ruleset
            )
            open_rally_action_id = None
        elif action_type == "rally_replay":
            state = reduce_scoring_state_for_ruleset(
                state, ScoringAction(type="rally_result", validity="replay"), ruleset
            )
            open_rally_action_id = None
        elif action_type in ("end_rally", "start_timeout", "change_side"):
            open_rally_action_id = None
        elif action_type == "correct_score":
            payload = _payload_dict(action)
            state = reduce_scoring_state_for_ruleset(
                state,
                ScoringAction(
                    type="correct_score",
                    target_server_team=payload.get("server_team", state.server_team),
                    target_score_a=payload.get("score_a", state.score_a),
                    target_score_b=payload.get("score_b", state.score_b),
                ),
                ruleset,
            )
            if open_rally_action_id is not None:
                # 该回合仍在进行中：修正覆盖它的 before-facts。
                derived[open_rally_action_id] = state
        elif action_type == "start_next_rally":
            derived[action.id] = state
            open_rally_action_id = action.id

    return derived


def _payload_dict(action) -> dict:
    raw = getattr(action, "payload_json", None)
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}


def replay_scoring_snapshots(db: Session, capture_take_id: str, *, ruleset_version: str | None = None) -> list[dict]:
    """按有效 action ledger 对账计分快照，返回本次发生变化的快照字典列表。

    - 来源 action 已被撤销 → 快照标记 `undone`（不复活）。
    - 派生计分事实与冻结值不一致（如 score correction）→ 追加新 revision，
      旧版本转 `superseded`，形成 supersede 链。
    """
    snapshots = list_scoring_snapshots(db, capture_take_id)
    if not snapshots:
        return []

    actions = [
        action
        for action in coding_svc.list_actions_for_take(db, capture_take_id)
        if action.status == CodingActionStatus.executed
    ]
    actions.sort(key=lambda action: (action.revision_before, action.created_at))
    effective_action_ids = {action.id for action in actions}

    ruleset = ruleset_version
    if ruleset is None:
        ruleset = next(
            (row.scoring_ruleset_version for row in reversed(snapshots) if row.scoring_ruleset_version),
            None,
        )

    now = datetime.now(UTC)
    changed: list[dict] = []

    # 1) 来源 action 失效 → undone
    for row in snapshots:
        if row.status == ScoringSnapshotStatus.effective and row.action_id not in effective_action_ids:
            _mark_snapshot(db, row, ScoringSnapshotStatus.undone, now=now)
            changed.append(to_dict(row))

    derived_by_action = _replay_scoring_state(actions, ruleset)
    by_action: dict[str, list[RallyScoringSnapshot]] = {}
    for row in snapshots:
        by_action.setdefault(row.action_id, []).append(row)

    # 2) 派生事实与冻结值不一致 → 追加 revision
    for action_id, derived_state in derived_by_action.items():
        rows = by_action.get(action_id)
        if not rows:
            # 历史 take 从未写过快照：保持"无事实"，不凭空补造。
            continue
        current = max(rows, key=lambda item: item.revision)
        if current.status == ScoringSnapshotStatus.undone:
            continue
        if _stored_facts(current) == _derive_facts(derived_state):
            continue
        new_row = RallyScoringSnapshot(
            id=_generate_id(),
            capture_take_id=capture_take_id,
            action_id=action_id,
            event_id=current.event_id,
            rally_id=current.rally_id,
            ordinal=current.ordinal,
            scoring_ruleset_version=current.scoring_ruleset_version,
            action_revision=current.action_revision,
            start_ms=current.start_ms,
            revision=current.revision + 1,
            supersedes_snapshot_id=current.id,
            status=ScoringSnapshotStatus.effective,
            created_at=now,
            **_derive_facts(derived_state),
        )
        db.add(new_row)
        db.flush()
        _mark_snapshot(db, current, ScoringSnapshotStatus.superseded, now=now)
        changed.append(to_dict(new_row))

    return changed
