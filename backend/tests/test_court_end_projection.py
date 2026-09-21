"""CourtEndProjection：独立端位投影的构建、回放与 unavailable 语义。"""

from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.database import Base, get_engine, get_session_factory, init_db, reset_database_state
from app.schemas.field_session import FieldSessionCreate
from app.services import court_end_projection_service as court_end_svc
from app.services.capture_take_service import create_capture_take
from app.services.coding_actions_service import execute_coding_action
from app.services.field_session_service import create_field_session


@pytest.fixture()
def db(monkeypatch, tmp_path):
    monkeypatch.setenv("PICKLEBALL_DATABASE_PATH", str(tmp_path / "court_end.sqlite3"))
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
            title="court-end",
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
        source_session_id=f"court-end-{match_format}",
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


def confirm(db, take_id: str, team_a_end: str = "end_a"):
    return court_end_svc.confirm_initial_court_end(
        db, capture_take_id=take_id, video_id=None, team_a_end=team_a_end
    )


def test_projection_requires_confirmed_initial_court_end(db):
    """缺少初始端位确认 → unavailable，绝不猜测端位。"""
    take_id = make_take(db)
    result = run(db, take_id, "start_game", 0, 1000, {"initial_server_team": "A"})
    run(db, take_id, "start_next_rally", result["revision"], 2000)

    projection = court_end_svc.build_court_end_projection(db, capture_take_id=take_id)
    assert projection.status == "unavailable"
    assert projection.unavailable_reason == "initial_court_end_not_confirmed"
    assert projection.initial_team_a_end is None
    assert projection.windows == []
    assert projection.team_end_at(0) == (None, None)
    # hash 仍然稳定可计算，便于消费者记录 unavailable 版本
    assert len(projection.court_end_hash) == 64


def test_projection_without_capture_take_is_unavailable(db):
    projection = court_end_svc.build_court_end_projection(db, capture_take_id=None)
    assert projection.status == "unavailable"
    assert projection.unavailable_reason == "no_capture_take_context"


def test_side_change_swaps_ends_for_subsequent_rallies(db):
    """有效换边 → 其后的回合交换 Team A/B 的 near/far。"""
    take_id = make_take(db)
    confirm(db, take_id, "end_a")
    result = run(db, take_id, "start_game", 0, 1000, {"initial_server_team": "A"})
    result = run(db, take_id, "start_next_rally", result["revision"], 2000)
    result = run(db, take_id, "rally_result_a", result["revision"], 3000)
    result = run(db, take_id, "change_side", result["revision"], 3500)
    run(db, take_id, "start_next_rally", result["revision"], 4000)

    projection = court_end_svc.build_court_end_projection(db, capture_take_id=take_id)
    assert projection.status == "available"
    assert projection.initial_team_a_end == "end_a"
    assert len(projection.windows) == 2

    initial, flipped = projection.windows
    assert initial.source_action_id is None and initial.source_event_id is None
    assert (initial.effective_from_ms, initial.team_a_end, initial.team_b_end) == (0, "end_a", "end_b")
    assert flipped.source_action_id is not None
    assert flipped.source_event_id is not None
    assert (flipped.effective_from_ms, flipped.team_a_end, flipped.team_b_end) == (3500, "end_b", "end_a")

    assert projection.team_end_at(2000) == ("end_a", "end_b")
    assert projection.team_end_at(4000) == ("end_b", "end_a")


def test_undoing_side_change_removes_the_flip(db):
    """撤销换边 → 投影回到单一窗口；端位投影完全由有效 ledger 决定。"""
    take_id = make_take(db)
    confirm(db, take_id, "end_b")
    result = run(db, take_id, "start_game", 0, 1000, {"initial_server_team": "A"})
    result = run(db, take_id, "start_next_rally", result["revision"], 2000)
    result = run(db, take_id, "rally_result_a", result["revision"], 3000)
    result = run(db, take_id, "change_side", result["revision"], 3500)

    before = court_end_svc.build_court_end_projection(db, capture_take_id=take_id)
    assert len(before.windows) == 2

    run(db, take_id, "undo", result["revision"], 4000)

    after = court_end_svc.build_court_end_projection(db, capture_take_id=take_id)
    assert len(after.windows) == 1
    assert after.team_end_at(0) == ("end_b", "end_a")
    assert after.team_end_at(99999) == ("end_b", "end_a")


def test_game_boundary_without_side_change_inherits_and_records_diagnostic(db):
    """局边界没有显式换边 → 继续继承上一端位，同时写结构化诊断。"""
    take_id = make_take(db)
    confirm(db, take_id, "end_a")
    result = run(db, take_id, "start_game", 0, 1000, {"initial_server_team": "A"})
    result = run(
        db, take_id, "correct_score", result["revision"], 1500, {"score_a": 21, "score_b": 0, "server_team": "A"}
    )
    run(db, take_id, "start_game", result["revision"], 2000, {"initial_server_team": "B"})

    projection = court_end_svc.build_court_end_projection(db, capture_take_id=take_id)
    codes = [item.code for item in projection.diagnostics]
    assert court_end_svc.DIAG_GAME_BOUNDARY_WITHOUT_SIDE_CHANGE in codes
    diagnostic = next(
        item for item in projection.diagnostics if item.code == court_end_svc.DIAG_GAME_BOUNDARY_WITHOUT_SIDE_CHANGE
    )
    assert diagnostic.game_ordinal == 2
    # 端位继承，不翻转
    assert len(projection.windows) == 1
    assert projection.team_end_at(999999) == ("end_a", "end_b")


def test_reconfirmation_versions_keep_only_latest_effective(db):
    """重新确认端位 → 产生新 revision，旧确认转 non-effective；投影用最新值。"""
    take_id = make_take(db)
    first = confirm(db, take_id, "end_a")
    second = confirm(db, take_id, "end_b")

    assert second.revision == first.revision + 1
    assert court_end_svc.get_effective_court_end_confirmation(db, take_id).id == second.id

    projection = court_end_svc.build_court_end_projection(db, capture_take_id=take_id)
    assert projection.initial_team_a_end == "end_b"
    assert projection.team_end_at(0) == ("end_b", "end_a")


def test_invalid_court_end_is_rejected(db):
    take_id = make_take(db)
    with pytest.raises(ValueError, match="未知端位"):
        confirm(db, take_id, "near")
