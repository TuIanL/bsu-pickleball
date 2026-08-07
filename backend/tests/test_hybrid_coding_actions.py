from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.database import Base, get_engine, get_session_factory, init_db, reset_database_state
from app.schemas.field_session import FieldSessionCreate
from app.services.capture_take_service import create_capture_take
from app.services.coding_actions_service import execute_coding_action
from app.services.field_session_service import create_field_session
from app.services.live_coding_state_service import get_state


@pytest.fixture()
def db(monkeypatch, tmp_path):
    monkeypatch.setenv("PICKLEBALL_DATABASE_PATH", str(tmp_path / "hybrid.sqlite3"))
    get_settings.cache_clear()
    reset_database_state()
    init_db()
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=get_engine())
        reset_database_state()
        get_settings.cache_clear()


def make_take(db, match_format: str = "singles") -> str:
    field_session = create_field_session(
        db,
        FieldSessionCreate(
            title="hybrid",
            venue="court",
            court_name="1",
            capture_mode="match",
            match_format=match_format,
            camera_setup="single",
        ),
    )
    take = create_capture_take(
        db,
        field_session_id=field_session.id,
        capture_mode="single",
        source_session_type="recording",
        source_session_id=f"hybrid-{match_format}",
    )
    db.commit()
    return take.id


def run(db, take_id: str, action: str, revision: int, timestamp: int, payload=None):
    return execute_coding_action(
        db,
        take_id,
        action=action,
        client_action_id=f"{action}-{revision}-{timestamp}",
        expected_revision=revision,
        timestamp_ms=timestamp,
        payload=payload or {},
    )


@pytest.mark.parametrize("match_format", ["singles", "doubles"])
def test_new_match_formats_use_hybrid_rules(db, match_format):
    state = get_state(db, make_take(db, match_format))
    assert state.scoring_ruleset_version == "hybrid_21_best_of_5_v1"
    assert state.scoring_mode == "hybrid_21_best_of_5_v1"


def test_start_game_requires_initial_server_without_revision_change(db):
    take_id = make_take(db)
    with pytest.raises(ValueError, match="initial_server_team"):
        run(db, take_id, "start_game", 0, 1000)
    db.rollback()
    assert get_state(db, take_id).revision == 0


def test_twenty_all_receiver_only_changes_serve_then_server_wins_game(db):
    take_id = make_take(db)
    result = run(db, take_id, "start_game", 0, 1000, {"initial_server_team": "A"})
    result = run(
        db,
        take_id,
        "correct_score",
        result["revision"],
        2000,
        {
            "score_a": 20,
            "score_b": 20,
            "server_team": "A",
        },
    )
    result = run(db, take_id, "start_next_rally", result["revision"], 3000)
    result = run(db, take_id, "rally_result_b", result["revision"], 4000)
    assert (result["live_state"]["score_a"], result["live_state"]["score_b"]) == (20, 20)
    assert result["live_state"]["server_team"] == "B"
    result = run(db, take_id, "start_next_rally", result["revision"], 5000)
    result = run(db, take_id, "rally_result_b", result["revision"], 6000)
    assert result["live_state"]["score_b"] == 21
    assert result["live_state"]["games_won_b"] == 1
    assert result["live_state"]["current_game_segment_id"] is None
    assert any(event["event_type"] == "game_end" for event in result["created_events"])


def test_three_game_wins_complete_match_and_block_next_game(db):
    take_id = make_take(db, "doubles")
    revision = 0
    timestamp = 1000
    for game in range(3):
        result = run(db, take_id, "start_game", revision, timestamp, {"initial_server_team": "A"})
        timestamp += 1000
        result = run(
            db,
            take_id,
            "correct_score",
            result["revision"],
            timestamp,
            {
                "score_a": 20,
                "score_b": 0,
                "server_team": "A",
            },
        )
        timestamp += 1000
        result = run(db, take_id, "start_next_rally", result["revision"], timestamp)
        timestamp += 1000
        result = run(db, take_id, "rally_result_a", result["revision"], timestamp)
        timestamp += 1000
        revision = result["revision"]
        assert result["live_state"]["games_won_a"] == game + 1

    assert result["live_state"]["match_status"] == "completed"
    assert result["live_state"]["match_winner"] == "A"
    assert result["live_state"]["current_set_segment_id"] is None
    with pytest.raises(ValueError, match="比赛已结束"):
        run(db, take_id, "start_game", revision, timestamp, {"initial_server_team": "B"})


def test_undo_winning_point_restores_open_game(db):
    take_id = make_take(db)
    result = run(db, take_id, "start_game", 0, 1000, {"initial_server_team": "A"})
    result = run(
        db,
        take_id,
        "correct_score",
        result["revision"],
        2000,
        {
            "score_a": 20,
            "score_b": 0,
            "server_team": "A",
        },
    )
    result = run(db, take_id, "start_next_rally", result["revision"], 3000)
    result = run(db, take_id, "rally_result_a", result["revision"], 4000)
    assert result["live_state"]["games_won_a"] == 1
    result = run(db, take_id, "undo", result["revision"], 5000)
    assert result["live_state"]["score_a"] == 20
    assert result["live_state"]["games_won_a"] == 0
    assert result["live_state"]["current_game_segment_id"] is not None
    assert result["live_state"]["match_status"] == "in_progress"


def test_score_correction_to_twenty_one_closes_game(db):
    take_id = make_take(db)
    result = run(db, take_id, "start_game", 0, 1000, {"initial_server_team": "B"})
    result = run(
        db,
        take_id,
        "correct_score",
        result["revision"],
        2000,
        {
            "score_a": 8,
            "score_b": 21,
            "server_team": "B",
        },
    )
    assert result["live_state"]["games_won_b"] == 1
    assert result["live_state"]["current_game_segment_id"] is None
    assert any(event["event_type"] == "game_end" for event in result["created_events"])


def test_legacy_side_out_state_keeps_old_semantics(db):
    take_id = make_take(db)
    state = get_state(db, take_id)
    state.scoring_mode = "side_out_singles_v1"
    state.scoring_ruleset_version = "side_out_singles_v1"
    db.commit()
    result = run(db, take_id, "start_game", 0, 1000, {"initial_server_team": "A"})
    result = run(db, take_id, "start_next_rally", result["revision"], 2000)
    result = run(db, take_id, "rally_result_b", result["revision"], 3000)
    assert result["live_state"]["score_b"] == 0
    assert result["live_state"]["server_team"] == "B"
