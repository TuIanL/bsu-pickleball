"""测试计分状态机纯 reducer —— 无副作用，纯函数验证。"""

from app.services.scoring_fsm import ScoringState, ScoringAction, reduce_scoring_state


def test_reducer_A_serves_wins():
    state = ScoringState(server_team="A", score_a=0, score_b=0)
    action = ScoringAction(type="rally_result", winner="A", validity="valid")
    result = reduce_scoring_state(state, action)
    assert result.server_team == "A"
    assert result.score_a == 1
    assert result.score_b == 0


def test_reducer_A_serves_loses_side_out():
    state = ScoringState(server_team="A", score_a=0, score_b=0)
    action = ScoringAction(type="rally_result", winner="B", validity="valid")
    result = reduce_scoring_state(state, action)
    assert result.server_team == "B"
    assert result.score_a == 0
    assert result.score_b == 0


def test_reducer_B_serves_wins():
    state = ScoringState(server_team="B", score_a=0, score_b=0)
    action = ScoringAction(type="rally_result", winner="B", validity="valid")
    result = reduce_scoring_state(state, action)
    assert result.server_team == "B"
    assert result.score_a == 0
    assert result.score_b == 1


def test_reducer_B_serves_loses_side_out():
    state = ScoringState(server_team="B", score_a=0, score_b=0)
    action = ScoringAction(type="rally_result", winner="A", validity="valid")
    result = reduce_scoring_state(state, action)
    assert result.server_team == "A"
    assert result.score_a == 0
    assert result.score_b == 0


def test_reducer_replay_does_not_change():
    state = ScoringState(server_team="A", score_a=3, score_b=2)
    action = ScoringAction(type="rally_result", winner=None, validity="replay")
    result = reduce_scoring_state(state, action)
    assert result.server_team == "A"
    assert result.score_a == 3
    assert result.score_b == 2


def test_reducer_correct_score_anchor():
    state = ScoringState(server_team="A", score_a=3, score_b=2)
    action = ScoringAction(
        type="correct_score",
        target_server_team="B",
        target_score_a=4,
        target_score_b=2,
    )
    result = reduce_scoring_state(state, action)
    assert result.server_team == "B"
    assert result.score_a == 4
    assert result.score_b == 2


def test_reducer_multiple_rallies():
    state = ScoringState(server_team="A", score_a=0, score_b=0)
    # A 发球 A 赢 → 1:0 A
    state = reduce_scoring_state(state, ScoringAction(type="rally_result", winner="A", validity="valid"))
    assert state.score_a == 1 and state.server_team == "A"
    # A 发球 A 赢 → 2:0 A
    state = reduce_scoring_state(state, ScoringAction(type="rally_result", winner="A", validity="valid"))
    assert state.score_a == 2 and state.server_team == "A"
    # A 发球 B 赢 → side out, 2:0 B
    state = reduce_scoring_state(state, ScoringAction(type="rally_result", winner="B", validity="valid"))
    assert state.score_a == 2 and state.score_b == 0 and state.server_team == "B"
    # B 发球 B 赢 → 2:1 B
    state = reduce_scoring_state(state, ScoringAction(type="rally_result", winner="B", validity="valid"))
    assert state.score_a == 2 and state.score_b == 1 and state.server_team == "B"


def test_reducer_server_team_none_A_wins():
    state = ScoringState(server_team=None, score_a=0, score_b=0)
    result = reduce_scoring_state(state, ScoringAction(type="rally_result", winner="A", validity="valid"))
    assert result.server_team == "A"
    assert result.score_a == 1
    assert result.score_b == 0


def test_reducer_server_team_none_B_wins():
    state = ScoringState(server_team=None, score_a=0, score_b=0)
    result = reduce_scoring_state(state, ScoringAction(type="rally_result", winner="B", validity="valid"))
    assert result.server_team == "B"
    assert result.score_a == 0
    assert result.score_b == 1


def test_reducer_server_team_none_replay():
    state = ScoringState(server_team=None, score_a=0, score_b=0)
    result = reduce_scoring_state(state, ScoringAction(type="rally_result", validity="replay"))
    assert result.server_team is None
    assert result.score_a == 0
    assert result.score_b == 0
