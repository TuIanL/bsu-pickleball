"""LiveCodingState 服务层 —— 状态快照管理，可从命令日志重建。"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.live_coding_state import LiveCodingState


# 获取某个 take 的实时编码状态快照
def get_state(db: Session, capture_take_id: str) -> LiveCodingState | None:
    return db.query(LiveCodingState).filter(
        LiveCodingState.capture_take_id == capture_take_id
    ).first()


# 初始化实时编码状态；已存在时直接返回，避免重复创建。
def init_state(db: Session, capture_take_id: str, *,
               scoring_mode: str = "none",
               scoring_ruleset_version: str | None = None) -> LiveCodingState:
    existing = get_state(db, capture_take_id)
    if existing is not None:
        return existing

    now = datetime.now(timezone.utc)
    state = LiveCodingState(
        capture_take_id=capture_take_id,
        revision=0,
        set_ordinal=0,
        game_ordinal=0,
        rally_ordinal=0,
        non_play=False,
        match_phase="idle",
        score_a=0,
        score_b=0,
        server_team=None,
        scoring_mode=scoring_mode,
        scoring_ruleset_version=scoring_ruleset_version,
        recent_results="[]",
        updated_at=now,
    )
    db.add(state)
    db.flush()
    return state


# 写入或更新实时编码状态（不存在则新建，存在则覆盖字段）
def upsert_state(
    db: Session,
    capture_take_id: str,
    *,
    revision: int,
    set_ordinal: int,
    game_ordinal: int,
    rally_ordinal: int,
    non_play: bool = False,
    match_phase: str | None = None,
    intermission_kind: str | None = None,
    current_set_segment_id: str | None = None,
    current_game_segment_id: str | None = None,
    current_rally_segment_id: str | None = None,
    # ── 计分相关 ──
    server_team: str | None = None,
    score_a: int | None = None,
    score_b: int | None = None,
    scoring_mode: str | None = None,
    scoring_ruleset_version: str | None = None,
    recent_results: list[dict] | None = None,
) -> LiveCodingState:
    state = get_state(db, capture_take_id)
    now = datetime.now(timezone.utc)
    if state is None:
        state = LiveCodingState(
            capture_take_id=capture_take_id,
            revision=revision,
            set_ordinal=set_ordinal,
            game_ordinal=game_ordinal,
            rally_ordinal=rally_ordinal,
            non_play=non_play,
            match_phase=match_phase or ("intermission" if non_play else "idle"),
            intermission_kind=intermission_kind,
            current_set_segment_id=current_set_segment_id,
            current_game_segment_id=current_game_segment_id,
            current_rally_segment_id=current_rally_segment_id,
            server_team=server_team,
            score_a=score_a or 0,
            score_b=score_b or 0,
            scoring_mode=scoring_mode or "none",
            scoring_ruleset_version=scoring_ruleset_version,
            recent_results=json.dumps(recent_results or [], ensure_ascii=False),
            updated_at=now,
        )
        db.add(state)
    else:
        state.revision = revision
        state.set_ordinal = set_ordinal
        state.game_ordinal = game_ordinal
        state.rally_ordinal = rally_ordinal
        state.non_play = non_play
        state.match_phase = match_phase or ("intermission" if non_play else "idle")
        state.intermission_kind = intermission_kind
        state.current_set_segment_id = current_set_segment_id
        state.current_game_segment_id = current_game_segment_id
        state.current_rally_segment_id = current_rally_segment_id
        if server_team is not None:
            state.server_team = server_team
        if score_a is not None:
            state.score_a = score_a
        if score_b is not None:
            state.score_b = score_b
        if scoring_mode is not None:
            state.scoring_mode = scoring_mode
        if scoring_ruleset_version is not None:
            state.scoring_ruleset_version = scoring_ruleset_version
        if recent_results is not None:
            state.recent_results = json.dumps(recent_results, ensure_ascii=False)
        state.updated_at = now
    db.flush()
    return state


# 将实时编码状态对象转换为字典（用于接口返回）
def state_to_dict(state: LiveCodingState) -> dict:
    try:
        recent = json.loads(state.recent_results) if isinstance(state.recent_results, str) else (state.recent_results or [])
    except (json.JSONDecodeError, TypeError):
        recent = []
    return {
        "revision": state.revision,
        "set_ordinal": state.set_ordinal,
        "game_ordinal": state.game_ordinal,
        "rally_ordinal": state.rally_ordinal,
        "non_play": state.non_play,
        "match_phase": getattr(state, "match_phase", "intermission" if state.non_play else "idle"),
        "intermission_kind": getattr(state, "intermission_kind", None),
        "current_set_segment_id": state.current_set_segment_id,
        "current_game_segment_id": state.current_game_segment_id,
        "current_rally_segment_id": state.current_rally_segment_id,
        # ── 计分相关 ──
        "server_team": getattr(state, "server_team", None),
        "score_a": getattr(state, "score_a", 0),
        "score_b": getattr(state, "score_b", 0),
        "scoring_mode": getattr(state, "scoring_mode", "none"),
        "scoring_ruleset_version": getattr(state, "scoring_ruleset_version", None),
        "recent_results": recent,
    }
