"""Pure, versioned scoring reducers used by live execution and replay."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Literal


HYBRID_21_RULESET = "hybrid_21_best_of_5_v1"
LEGACY_SIDE_OUT_RULESET = "side_out_singles_v1"


@dataclass
class ScoringState:
    server_team: str | None
    score_a: int
    score_b: int
    games_won_a: int = 0
    games_won_b: int = 0
    scoring_phase: str = "rally"
    serving_side: str | None = None
    match_status: str = "not_started"
    match_winner: str | None = None
    game_completed: bool = False
    game_winner: str | None = None


@dataclass
class ScoringAction:
    type: Literal["rally_result", "correct_score"]
    winner: str | None = None
    validity: str = "valid"
    target_server_team: str | None = None
    target_score_a: int | None = None
    target_score_b: int | None = None


def serving_side_for(server_team: str | None, score_a: int, score_b: int) -> str | None:
    if server_team not in ("A", "B"):
        return None
    server_score = score_a if server_team == "A" else score_b
    return "left" if server_score % 2 else "right"


def scoring_phase_for(score_a: int, score_b: int) -> str:
    return "serve_only" if score_a == 20 and score_b == 20 else "rally"


def initial_game_state(state: ScoringState, initial_server_team: str) -> ScoringState:
    return ScoringState(
        server_team=initial_server_team,
        score_a=0,
        score_b=0,
        games_won_a=state.games_won_a,
        games_won_b=state.games_won_b,
        scoring_phase="rally",
        serving_side="right",
        match_status="in_progress",
    )


def reduce_hybrid_21_state(state: ScoringState, action: ScoringAction) -> ScoringState:
    """Apply the best-of-five hybrid 21-point rules."""
    if action.type == "correct_score":
        score_a = action.target_score_a if action.target_score_a is not None else 0
        score_b = action.target_score_b if action.target_score_b is not None else 0
        server = action.target_server_team
        game_winner = "A" if score_a == 21 else "B" if score_b == 21 else None
        games_a = state.games_won_a + (1 if game_winner == "A" else 0)
        games_b = state.games_won_b + (1 if game_winner == "B" else 0)
        match_winner = "A" if games_a == 3 else "B" if games_b == 3 else None
        return replace(
            state,
            server_team=server,
            score_a=score_a,
            score_b=score_b,
            scoring_phase=scoring_phase_for(score_a, score_b),
            serving_side=serving_side_for(server, score_a, score_b),
            games_won_a=games_a,
            games_won_b=games_b,
            match_status="completed" if match_winner else "in_progress",
            match_winner=match_winner,
            game_completed=game_winner is not None,
            game_winner=game_winner,
        )

    if action.type != "rally_result" or action.validity == "replay" or action.winner not in ("A", "B"):
        return replace(state, game_completed=False, game_winner=None)
    if state.match_status == "completed":
        return state

    winner = action.winner
    score_a, score_b = state.score_a, state.score_b
    if state.scoring_phase == "serve_only":
        if winner == state.server_team:
            if winner == "A":
                score_a = min(21, score_a + 1)
            else:
                score_b = min(21, score_b + 1)
    else:
        if winner == "A":
            score_a = min(21, score_a + 1)
        else:
            score_b = min(21, score_b + 1)

    server = winner
    game_winner = "A" if score_a == 21 else "B" if score_b == 21 else None
    games_a = state.games_won_a + (1 if game_winner == "A" else 0)
    games_b = state.games_won_b + (1 if game_winner == "B" else 0)
    match_winner = "A" if games_a == 3 else "B" if games_b == 3 else None
    return ScoringState(
        server_team=server,
        score_a=score_a,
        score_b=score_b,
        games_won_a=games_a,
        games_won_b=games_b,
        scoring_phase=scoring_phase_for(score_a, score_b),
        serving_side=serving_side_for(server, score_a, score_b),
        match_status="completed" if match_winner else "in_progress",
        match_winner=match_winner,
        game_completed=game_winner is not None,
        game_winner=game_winner,
    )


def reduce_scoring_state_for_ruleset(
    state: ScoringState, action: ScoringAction, ruleset_version: str | None
) -> ScoringState:
    if ruleset_version == HYBRID_21_RULESET:
        return reduce_hybrid_21_state(state, action)
    return reduce_scoring_state(state, action)


def reduce_scoring_state(state: ScoringState, action: ScoringAction) -> ScoringState:
    """Preserve the legacy side-out reducer for historical takes."""
    if action.type == "correct_score":
        return ScoringState(
            server_team=action.target_server_team,
            score_a=action.target_score_a or 0,
            score_b=action.target_score_b or 0,
        )
    if action.type != "rally_result" or action.validity == "replay":
        return replace(state)
    winner = action.winner
    if winner not in ("A", "B"):
        return state
    if state.server_team is None:
        return ScoringState(
            server_team=winner,
            score_a=1 if winner == "A" else 0,
            score_b=1 if winner == "B" else 0,
        )
    if winner == state.server_team:
        return ScoringState(
            server_team=winner,
            score_a=state.score_a + (1 if winner == "A" else 0),
            score_b=state.score_b + (1 if winner == "B" else 0),
        )
    return ScoringState(server_team=winner, score_a=state.score_a, score_b=state.score_b)


def scoring_state_to_dict(state: ScoringState) -> dict:
    return asdict(state)
