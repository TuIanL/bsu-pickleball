"""RallyScoringSnapshot：录制期计分事实的封存、重放与 supersede 链。"""

from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.database import Base, get_engine, get_session_factory, init_db, reset_database_state
from app.schemas.field_session import FieldSessionCreate
from app.services import rally_scoring_service as scoring_svc
from app.services.capture_take_service import create_capture_take
from app.services.coding_actions_service import execute_coding_action
from app.services.field_session_service import create_field_session


@pytest.fixture()
def db(monkeypatch, tmp_path):
    monkeypatch.setenv("PICKLEBALL_DATABASE_PATH", str(tmp_path / "rally_scoring.sqlite3"))
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


def make_take(db, match_format: str = "doubles") -> str:
    field_session = create_field_session(
        db,
        FieldSessionCreate(
            title="rally-scoring",
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
        source_session_id=f"rally-scoring-{match_format}",
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


def test_rally_start_seals_scoring_facts_only(db):
    """rally_start 在同一事务内封存计分事实，且不携带任何分析期身份/端位。"""
    take_id = make_take(db)
    result = run(db, take_id, "start_game", 0, 1000, {"initial_server_team": "A"})
    run(db, take_id, "start_next_rally", result["revision"], 2000)

    snapshots = scoring_svc.effective_scoring_snapshots(db, take_id)
    assert len(snapshots) == 1
    payload = scoring_svc.to_dict(snapshots[0])

    assert payload["server_team"] == "A"
    assert (payload["score_a_before"], payload["score_b_before"]) == (0, 0)
    assert payload["scoring_ruleset_version"] == "hybrid_21_best_of_5_v1"
    assert payload["ordinal"] == 1
    assert payload["rally_id"]
    assert payload["event_id"]
    assert payload["action_id"]
    assert payload["action_revision"] == 1  # start_next_rally 生效时的 take revision

    # 录制期快照不得引用分析期名册或端位（"引用未来对象"的时序矛盾）
    forbidden = {
        "roster_hash",
        "roster_snapshot_id",
        "players",
        "team_a_players",
        "team_b_players",
        "team_a_end",
        "team_b_end",
        "initial_side",
        "canonical_player_id",
    }
    assert forbidden.isdisjoint(payload.keys())


def test_next_rally_inherits_updated_server_and_score(db):
    """有效结果更新 reducer 后，下一个回合的快照固化更新后的发球权与比分。"""
    take_id = make_take(db)
    result = run(db, take_id, "start_game", 0, 1000, {"initial_server_team": "A"})
    result = run(db, take_id, "start_next_rally", result["revision"], 2000)
    result = run(db, take_id, "rally_result_a", result["revision"], 3000)
    run(db, take_id, "start_next_rally", result["revision"], 4000)

    snapshots = scoring_svc.effective_scoring_snapshots(db, take_id)
    assert [item.ordinal for item in snapshots] == [1, 2]
    second = scoring_svc.to_dict(snapshots[1])
    assert second["server_team"] == "A"
    assert (second["score_a_before"], second["score_b_before"]) == (1, 0)
    assert second["start_ms"] == 4000


def test_score_correction_during_open_rally_supersedes_snapshot(db):
    """回合进行中改分 → 该回合 before-facts 被重放并形成 supersede 链。"""
    take_id = make_take(db)
    result = run(db, take_id, "start_game", 0, 1000, {"initial_server_team": "A"})
    result = run(db, take_id, "start_next_rally", result["revision"], 2000)
    result = run(db, take_id, "rally_result_a", result["revision"], 3000)
    result = run(db, take_id, "start_next_rally", result["revision"], 4000)

    open_rally = scoring_svc.effective_scoring_snapshots(db, take_id)[1]
    assert (open_rally.score_a_before, open_rally.score_b_before) == (1, 0)

    run(db, take_id, "correct_score", result["revision"], 5000, {"score_a": 0, "score_b": 1, "server_team": "B"})

    versions = [row for row in scoring_svc.list_scoring_snapshots(db, take_id) if row.action_id == open_rally.action_id]
    assert len(versions) == 2, "改分必须追加新 revision 而不是就地改写"
    assert scoring_svc.status_of(versions[0]) == "superseded"
    assert scoring_svc.status_of(versions[1]) == "effective"
    assert versions[1].revision == versions[0].revision + 1
    assert versions[1].supersedes_snapshot_id == versions[0].id
    # supersede 后比分被重算，来源 action/event/rally 归属保持不变
    assert (versions[1].score_a_before, versions[1].score_b_before) == (0, 1)
    assert versions[1].rally_id == versions[0].rally_id
    assert versions[1].event_id == versions[0].event_id

    effective = scoring_svc.effective_scoring_snapshots(db, take_id)
    assert len(effective) == 2
    assert (effective[1].score_a_before, effective[1].score_b_before) == (0, 1)


def test_undoing_rally_start_marks_snapshot_undone(db):
    """撤销 start_next_rally → 其快照转 undone，且不会被后续重放复活。"""
    take_id = make_take(db)
    result = run(db, take_id, "start_game", 0, 1000, {"initial_server_team": "A"})
    result = run(db, take_id, "start_next_rally", result["revision"], 2000)
    assert len(scoring_svc.effective_scoring_snapshots(db, take_id)) == 1

    result = run(db, take_id, "undo", result["revision"], 3000)
    assert result["scoring_snapshot_changes"], "undo 必须触发一次对账重放"

    snapshot = scoring_svc.list_scoring_snapshots(db, take_id)[0]
    assert scoring_svc.status_of(snapshot) == "undone"
    assert scoring_svc.effective_scoring_snapshots(db, take_id) == []

    # 再跑一次重放：undone 不得被复活
    scoring_svc.replay_scoring_snapshots(db, take_id)
    assert scoring_svc.status_of(scoring_svc.list_scoring_snapshots(db, take_id)[0]) == "undone"


def test_replay_never_fabricates_snapshots_for_legacy_actions(db):
    """历史 take 从未写过快照时，重放只对账、不凭空造事实。"""
    take_id = make_take(db)
    result = run(db, take_id, "start_game", 0, 1000, {"initial_server_team": "A"})
    result = run(db, take_id, "start_next_rally", result["revision"], 2000)

    # 模拟历史遗留：直接把已写入的快照删掉，等价于"老录像没有快照表"
    for row in scoring_svc.list_scoring_snapshots(db, take_id):
        db.delete(row)
    db.flush()

    assert scoring_svc.replay_scoring_snapshots(db, take_id) == []
    assert scoring_svc.list_scoring_snapshots(db, take_id) == []


def test_snapshot_hash_is_stable_and_content_sensitive(db):
    take_id = make_take(db)
    result = run(db, take_id, "start_game", 0, 1000, {"initial_server_team": "A"})
    run(db, take_id, "start_next_rally", result["revision"], 2000)

    snapshot = scoring_svc.effective_scoring_snapshots(db, take_id)[0]
    first = scoring_svc.snapshot_hash_of(snapshot)
    assert first == scoring_svc.snapshot_hash_of(snapshot)
    assert len(first) == 64

    snapshot.score_a_before = 7
    assert scoring_svc.snapshot_hash_of(snapshot) != first
