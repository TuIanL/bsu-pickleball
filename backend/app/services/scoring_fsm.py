"""Scoring FSM —— 纯计分状态机 reducer，无副作用。"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Literal


@dataclass
class ScoringState:
    server_team: str | None
    score_a: int
    score_b: int


@dataclass
class ScoringAction:
    type: Literal[
        "rally_result", "correct_score",
    ]
    winner: str | None = None          # "A" | "B" | None
    validity: str = "valid"            # "valid" | "replay"

    # 用于 correct_score
    target_server_team: str | None = None
    target_score_a: int | None = None
    target_score_b: int | None = None


def reduce_scoring_state(
    state: ScoringState,
    action: ScoringAction,
) -> ScoringState:
    """
    纯函数：输入当前计分状态 + 一个 action，返回新的计分状态。
    不产生任何副作用（不写 DB、不创建事件）。
    """
    if action.type == "correct_score":
        return ScoringState(
            server_team=action.target_server_team,
            score_a=action.target_score_a or 0,
            score_b=action.target_score_b or 0,
        )

    if action.type != "rally_result":
        return state  # 未知 action 不处理

    # 重打不改变状态
    if action.validity == "replay":
        return ScoringState(
            server_team=state.server_team,
            score_a=state.score_a,
            score_b=state.score_b,
        )

    winner = action.winner
    if winner is None:
        return state

    # server_team 未设置时（未走 start_game），首次结果自动推断发球方
    if state.server_team is None:
        if winner == "A":
            return ScoringState(server_team="A", score_a=1, score_b=0)
        elif winner == "B":
            return ScoringState(server_team="B", score_a=0, score_b=1)
        return state

    server = state.server_team

    # 发球方赢 → 得分，发球权不变
    if winner == server:
        if server == "A":
            return ScoringState(server_team="A", score_a=state.score_a + 1, score_b=state.score_b)
        else:
            return ScoringState(server_team="B", score_a=state.score_a, score_b=state.score_b + 1)

    # 接发方赢 → side out，不得分
    if server == "A":
        return ScoringState(server_team="B", score_a=state.score_a, score_b=state.score_b)
    else:
        return ScoringState(server_team="A", score_a=state.score_a, score_b=state.score_b)


def scoring_state_to_dict(state: ScoringState) -> dict:
    return asdict(state)
