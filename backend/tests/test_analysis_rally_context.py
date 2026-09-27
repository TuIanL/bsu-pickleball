"""分析名册、Job-bound 回合上下文、formal window 绑定与身份连续性审计。"""

from __future__ import annotations

import json

import pytest

from app.core.config import get_settings
from app.database import Base, get_engine, get_session_factory, init_db, reset_database_state
from app.models.capture_segment import CaptureSegment, EditStatus, SegmentSource, SegmentStatus, SegmentType
from app.schemas.analysis import AnalysisJobCreate, AnalysisUploadMetadata
from app.schemas.field_session import FieldSessionCreate
from app.schemas.rally_context import (
    AnalysisRosterConfirmationEntry,
    AnalysisRosterSnapshotPayload,
    RosterConfirmationRequest,
    context_hash,
)
from app.services import analysis_rally_context_service as ctx_svc
from app.services import court_end_projection_service as court_end_svc
from app.services.capture_take_service import create_capture_take
from app.services.coding_actions_service import execute_coding_action
from app.services.field_session_service import create_field_session
from app.services.storage_service import StorageService


@pytest.fixture()
def db(monkeypatch, tmp_path):
    monkeypatch.setenv("PICKLEBALL_DATABASE_PATH", str(tmp_path / "rally_context.sqlite3"))
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
            title="rally-context",
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
        source_session_id=f"rally-context-{match_format}",
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


def four_entries(team_split=("A", "A", "B", "B")) -> list[AnalysisRosterConfirmationEntry]:
    return [
        AnalysisRosterConfirmationEntry(
            canonical_player_id=f"Player_{index + 1}",
            display_name=f"球员{index + 1}",
            team_id=team_split[index],
            source_view_id="cam_1",
            anchor_timestamp_ms=1000 * (index + 1),
            anchor_court_xy=[10.0 + index, 20.0 + index],
            bootstrap_run_id="job-src-1",
            bootstrap_model_version="player-render-trajectory.v2",
            bootstrap_confidence=0.9,
        )
        for index in range(4)
    ]


def make_manual_rally_segment(db, take_id: str, *, segment_id: str, start_ms: int, end_ms: int, event_id: str):
    row = CaptureSegment(
        id=segment_id,
        capture_take_id=take_id,
        segment_type=SegmentType.rally,
        ordinal=1,
        start_ms=start_ms,
        end_ms=end_ms,
        start_event_id=event_id,
        status=SegmentStatus.closed,
        edit_status=EditStatus.active,
        source=SegmentSource.manual,
    )
    db.add(row)
    db.flush()
    return row


# ── bootstrap（3.1）──


def test_bootstrap_without_source_job_is_unavailable_and_skippable(db):
    result = ctx_svc.build_player_bootstrap(db, capture_take_id=make_take(db))
    assert result.status == "unavailable"
    assert result.unavailable_reason == ctx_svc.DIAG_BOOTSTRAP_NO_SOURCE_JOB
    assert result.skippable is True
    assert result.candidates == []


def test_bootstrap_reads_real_trajectory_artifact_and_quality(db, monkeypatch, tmp_path):
    """有真实产物时返回候选 + 锚点 + 质量诊断；不启动 Pipeline。"""
    monkeypatch.setenv("PICKLEBALL_OUTPUTS_DIR", str(tmp_path / "outputs"))
    get_settings.cache_clear()
    reset_database_state()
    init_db()
    storage = StorageService()
    job_id = "job-src-1"
    storage.write_json(
        storage.player_trajectory_json_path(job_id),
        {
            "schema_version": "player-render-trajectory.v2",
            "players": [
                {"player_id": "Player_1", "render_slot": "p1", "initial_side": "near"},
                {"player_id": "Player_2", "render_slot": "p2", "initial_side": "far"},
            ],
            "samples": [
                {"player_id": "Player_1", "timestamp_seconds": 1.5, "x_ft": 5.0, "y_ft": 6.0, "confidence": 0.8},
                {"player_id": "Player_2", "timestamp_seconds": 2.5, "x_ft": 7.0, "y_ft": 8.0, "confidence": 0.7},
            ],
        },
    )
    storage.write_json(
        storage.four_player_identification_quality_json_path(job_id),
        {"status": "available", "verdict": "fail", "failure_reasons": ["identity_switch_count 偏高"]},
    )

    result = ctx_svc.build_player_bootstrap(
        db, capture_take_id="take-1", source_job_ids=[job_id], match_format="doubles"
    )
    assert result.status == "insufficient_candidates"  # 双打期望 4 人，只有 2 人
    assert [item.canonical_player_id for item in result.candidates] == ["Player_1", "Player_2"]
    assert result.candidates[0].anchor_timestamp_ms == 1500
    assert result.candidates[0].anchor_court_xy == [5.0, 6.0]
    assert result.bootstrap_model_version == "player-render-trajectory.v2"
    codes = {item.code for item in result.diagnostics}
    assert "four_player_quality_verdict_fail" in codes
    assert ctx_svc.DIAG_BOOTSTRAP_INSUFFICIENT in codes


def test_bootstrap_is_available_for_singles_with_two_candidates(db, monkeypatch, tmp_path):
    monkeypatch.setenv("PICKLEBALL_OUTPUTS_DIR", str(tmp_path / "outputs"))
    get_settings.cache_clear()
    reset_database_state()
    init_db()
    storage = StorageService()
    storage.write_json(
        storage.roster_manifest_json_path("job-src-2"),
        {
            "schema_version": "global-player-roster.v1",
            "players": [{"player_id": "Player_1", "label": "A"}, {"player_id": "Player_2", "label": "B"}],
        },
    )
    result = ctx_svc.build_player_bootstrap(
        db, capture_take_id="take-1", source_job_ids=["job-src-2"], match_format="singles"
    )
    assert result.status == "available"
    codes = {item.code for item in result.diagnostics}
    assert ctx_svc.DIAG_ANCHOR_EVIDENCE_UNAVAILABLE in codes


# ── 名册冻结（3.3）──


def test_freeze_roster_marks_skip_and_insufficient(db):
    take_id = make_take(db)
    skipped = ctx_svc.freeze_roster_snapshot(
        db,
        capture_take_id=take_id,
        video_id=None,
        job_id="job-skip",
        request=RosterConfirmationRequest(skipped=True),
    )
    assert skipped.status == "skipped"
    assert skipped.unavailable_reason == "analysis_roster_skipped_by_user"

    short = ctx_svc.freeze_roster_snapshot(
        db,
        capture_take_id=take_id,
        video_id=None,
        job_id="job-short",
        request=RosterConfirmationRequest(entries=four_entries()[:2]),
    )
    assert short.status == "insufficient_candidates"
    assert short.unavailable_reason == "analysis_roster_insufficient_candidates"

    full = ctx_svc.freeze_roster_snapshot(
        db,
        capture_take_id=take_id,
        video_id=None,
        job_id="job-full",
        request=RosterConfirmationRequest(entries=four_entries(), initial_team_a_end="end_a"),
    )
    assert full.status == "available"
    assert full.players_for_team("A") == ["Player_1", "Player_2"]
    assert full.players_for_team("B") == ["Player_3", "Player_4"]
    # 确认初始端位随 Job 提交落盘
    assert court_end_svc.get_effective_court_end_confirmation(db, take_id).team_a_end == "end_a"


def test_later_roster_edits_do_not_change_older_job_snapshot(db):
    take_id = make_take(db)
    first = ctx_svc.freeze_roster_snapshot(
        db,
        capture_take_id=take_id,
        video_id=None,
        job_id="job-old",
        request=RosterConfirmationRequest(entries=four_entries()),
    )
    second = ctx_svc.freeze_roster_snapshot(
        db,
        capture_take_id=take_id,
        video_id=None,
        job_id="job-new",
        request=RosterConfirmationRequest(entries=four_entries(("B", "B", "A", "A"))),
    )
    assert first.roster_hash != second.roster_hash
    assert ctx_svc.roster_snapshot_hash_for_job(db, "job-old") == first.roster_hash
    assert ctx_svc.roster_snapshot_hash_for_job(db, "job-new") == second.roster_hash


# ── 上下文合成（4.1/4.2）──


def test_compose_context_binds_scoring_roster_and_court_end(db):
    take_id = make_take(db)
    result = run(db, take_id, "start_game", 0, 500, {"initial_server_team": "A"})
    result = run(db, take_id, "start_next_rally", result["revision"], 1000)
    result = run(db, take_id, "rally_result_a", result["revision"], 2000)
    run(db, take_id, "start_next_rally", result["revision"], 3000)

    ctx_svc.freeze_roster_snapshot(
        db,
        capture_take_id=take_id,
        video_id=None,
        job_id="job-ctx",
        request=RosterConfirmationRequest(entries=four_entries(), initial_team_a_end="end_a"),
    )
    payload = ctx_svc.compose_rally_context(db, job_id="job-ctx", capture_take_id=take_id)
    assert payload.status == "available"
    assert len(payload.rallies) == 2

    first, second = payload.rallies
    assert first.status == "available"
    assert first.server_team == "A"
    assert (first.score_a_before, first.score_b_before) == (0, 0)
    assert first.team_a_end == "end_a" and first.team_b_end == "end_b"
    assert first.team_a_players == ["Player_1", "Player_2"]
    assert first.team_b_players == ["Player_3", "Player_4"]
    assert first.scoring_hash and first.context_hash
    assert (second.score_a_before, second.score_b_before) == (1, 0)
    assert first.context_hash != second.context_hash


def test_context_without_roster_is_unavailable_and_does_not_invent_teams(db):
    take_id = make_take(db)
    result = run(db, take_id, "start_game", 0, 500, {"initial_server_team": "A"})
    run(db, take_id, "start_next_rally", result["revision"], 1000)

    payload = ctx_svc.compose_rally_context(db, job_id="job-noroster", capture_take_id=take_id)
    assert payload.status == "unavailable"
    assert payload.roster_hash is None
    rally = payload.rallies[0]
    assert rally.status == "unavailable"
    assert rally.team_a_players == [] and rally.team_b_players == []
    assert rally.unavailable_reason in {
        "analysis_roster_not_confirmed",
        "initial_court_end_not_confirmed",
        "analysis_roster_skipped_by_user",
    }


def test_plan_context_uses_pre_persisted_roster_and_initial_end(db):
    """Job 创建前的纯计划必须已经带上本次提交的名册/端位。

    这是回归测试：不能先用空 Job id 组装上下文、再在落库后才冻结名册，
    否则首个 Job 的 Team A/B 会永久变成 unavailable。
    """
    take_id = make_take(db)
    result = run(db, take_id, "start_game", 0, 500, {"initial_server_team": "A"})
    run(db, take_id, "start_next_rally", result["revision"], 1000)
    payload = AnalysisJobCreate(
        metadata=AnalysisUploadMetadata(
            fileName="rally.mp4",
            matchTitle="plan",
            venue="court",
            matchDate="2026-09-20",
            matchFormat="doubles",
            cameraAngle="baseline",
            athleteLabel="players",
            level="recreational",
            capture_take_id=take_id,
        ),
        videoId="video-plan",
        rosterConfirmation=RosterConfirmationRequest(
            entries=four_entries(),
            initial_team_a_end="end_a",
        ),
    )
    plan = ctx_svc.plan_context_for_job(db, payload=payload)
    context = plan["context_payload"]
    assert context.status == "available"
    assert plan["roster_hash"]
    assert context.rallies[0].server_team == "A"
    assert context.rallies[0].team_a_end == "end_a"
    assert context.rallies[0].team_a_players == ["Player_1", "Player_2"]
    persisted = ctx_svc.persist_context_binding(db, job_id="job-plan", plan=plan)
    stored = ctx_svc.context_payload(ctx_svc.get_context_set(db, "job-plan"))
    assert persisted["context_set_hash"]
    assert stored is not None
    assert stored.rallies[0].context_hash == context_hash(stored.rallies[0].model_dump(mode="json"))


def test_context_input_hash_is_job_id_independent_but_roster_sensitive(db):
    take_id = make_take(db)
    result = run(db, take_id, "start_game", 0, 500, {"initial_server_team": "A"})
    run(db, take_id, "start_next_rally", result["revision"], 1000)

    first = ctx_svc._build_roster_payload(  # noqa: SLF001 - 直接用纯构造验证 hash 语义
        capture_take_id=take_id, video_id=None, request=RosterConfirmationRequest(entries=four_entries())
    )
    second = ctx_svc._build_roster_payload(  # noqa: SLF001
        capture_take_id=take_id, video_id=None, request=RosterConfirmationRequest(entries=four_entries(("B", "B", "A", "A")))
    )
    assert first.roster_hash != second.roster_hash

    a = ctx_svc.compose_rally_context(db, job_id="job-1", capture_take_id=take_id)
    b = ctx_svc.compose_rally_context(db, job_id="job-2", capture_take_id=take_id)
    assert ctx_svc.context_input_hash(a) == ctx_svc.context_input_hash(b)


def test_persist_context_is_idempotent_per_job(db):
    take_id = make_take(db)
    result = run(db, take_id, "start_game", 0, 500, {"initial_server_team": "A"})
    run(db, take_id, "start_next_rally", result["revision"], 1000)

    payload = ctx_svc.compose_rally_context(db, job_id="job-idem", capture_take_id=take_id)
    first = ctx_svc.persist_rally_context(db, payload)
    second = ctx_svc.persist_rally_context(db, payload.model_copy(update={"context_set_id": "arc_other"}))
    assert second.id == first.id
    assert ctx_svc.context_set_hash_for_job(db, "job-idem") == first.context_set_hash


# ── 绑定优先级（4.3/4.4）──


def _snapshot_stub(db, take_id: str):
    result = run(db, take_id, "start_game", 0, 500, {"initial_server_team": "A"})
    result = run(db, take_id, "start_next_rally", result["revision"], 1000)
    from app.services.rally_scoring_service import effective_scoring_snapshots

    return effective_scoring_snapshots(db, take_id)[0]


def test_bind_prefers_direct_segment_link(db):
    take_id = make_take(db)
    snapshot = _snapshot_stub(db, take_id)
    make_manual_rally_segment(
        db, take_id, segment_id="seg-manual-1", start_ms=1000, end_ms=2000, event_id=snapshot.event_id
    )
    binding, bound = ctx_svc.bind_formal_window(
        db,
        capture_take_id=take_id,
        window={"segment_id": "seg-formal-1", "start_ms": 1000, "end_ms": 2000, "source_rally_segment_id": "seg-manual-1"},
        snapshots=[snapshot],
    )
    assert binding.method == "direct_segment_link"
    assert binding.source_segment_id == "seg-manual-1"
    assert bound is snapshot


def test_bind_falls_back_to_direct_start_event_link(db):
    take_id = make_take(db)
    snapshot = _snapshot_stub(db, take_id)
    binding, bound = ctx_svc.bind_formal_window(
        db,
        capture_take_id=take_id,
        window={"segment_id": "seg-formal-1", "start_ms": 1000, "end_ms": 2000, "source_start_event_id": snapshot.event_id},
        snapshots=[snapshot],
    )
    assert binding.method == "direct_start_event_link"
    assert bound is snapshot


def test_bind_falls_back_to_unique_temporal_match(db):
    take_id = make_take(db)
    snapshot = _snapshot_stub(db, take_id)
    binding, bound = ctx_svc.bind_formal_window(
        db,
        capture_take_id=take_id,
        window={"segment_id": "seg-formal-1", "start_ms": 1800, "end_ms": 3000},
        snapshots=[snapshot],
        tolerance_ms=3000,
    )
    assert binding.method == "unique_temporal_match"
    assert bound is snapshot


def test_bind_degrades_to_unavailable_on_ambiguity(db):
    take_id = make_take(db)
    result = run(db, take_id, "start_game", 0, 500, {"initial_server_team": "A"})
    result = run(db, take_id, "start_next_rally", result["revision"], 1000)
    result = run(db, take_id, "rally_result_a", result["revision"], 1500)
    result = run(db, take_id, "start_next_rally", result["revision"], 2000)
    from app.services.rally_scoring_service import effective_scoring_snapshots

    snapshots = effective_scoring_snapshots(db, take_id)
    assert len(snapshots) == 2

    binding, bound = ctx_svc.bind_formal_window(
        db,
        capture_take_id=take_id,
        window={"segment_id": "seg-formal-x", "start_ms": 2500, "end_ms": 3000},
        snapshots=snapshots,
        tolerance_ms=3000,
    )
    assert binding.method == "unavailable"
    assert bound is None
    assert binding.candidate_count == 2
    assert any("歧义" in item for item in binding.diagnostics)


def test_attach_window_context_binding_records_method_and_hash(db):
    take_id = make_take(db)
    result = run(db, take_id, "start_game", 0, 500, {"initial_server_team": "A"})
    result = run(db, take_id, "start_next_rally", result["revision"], 1000)
    from app.services.rally_scoring_service import effective_scoring_snapshots

    snapshot = effective_scoring_snapshots(db, take_id)[0]
    # 录制期真实创建的 rally 区间就是 direct link 的源：它已带 start_event_id。
    ctx_svc.freeze_roster_snapshot(
        db,
        capture_take_id=take_id,
        video_id=None,
        job_id="job-attach",
        request=RosterConfirmationRequest(entries=four_entries(), initial_team_a_end="end_a"),
    )
    context = ctx_svc.compose_rally_context(db, job_id="job-attach", capture_take_id=take_id)
    assert context.rallies[0].rally_id == snapshot.rally_id

    enriched = ctx_svc.attach_window_context_binding(
        db,
        capture_take_id=take_id,
        segments=[{"segment_id": "seg-formal-1", "start_ms": 1050, "end_ms": 2000}],
        context=context,
    )
    window = enriched[0]
    assert window["source_rally_segment_id"] == snapshot.rally_id
    assert window["source_start_event_id"] == snapshot.event_id
    assert window["binding_method"] == "direct_segment_link"
    assert window["context_rally_id"] == snapshot.rally_id
    assert window["context_hash"] == context.rallies[0].context_hash


# ── 身份连续性审计（3.4）──


def _formal_sample(
    player_id: str,
    *,
    timestamp_ms: int,
    x_ft: float,
    y_ft: float,
    bbox: list[float] | None = None,
) -> dict:
    sample: dict = {
        "player_id": player_id,
        "take_timestamp_ms": timestamp_ms,
        "x_ft": x_ft,
        "y_ft": y_ft,
    }
    if bbox is not None:
        sample["bbox"] = bbox
    return sample


def test_binding_audit_confirms_only_simultaneous_one_to_one_matches(db):
    """同一时刻、同一机位的唯一几何匹配才确认；越出时间窗口的不确认。"""
    take_id = make_take(db)
    roster = ctx_svc.freeze_roster_snapshot(
        db,
        capture_take_id=take_id,
        video_id=None,
        job_id="job-audit",
        request=RosterConfirmationRequest(entries=four_entries()),
    )
    formal_payload = {
        "player_roster": [{"player_id": f"Player_{index}"} for index in range(1, 5)],
        "samples": [
            # Player_1 / Player_2 在锚点时刻附近、位置相符 → 可确认
            _formal_sample("Player_1", timestamp_ms=1050, x_ft=10.2, y_ft=20.3),
            _formal_sample("Player_2", timestamp_ms=2040, x_ft=11.1, y_ft=21.2),
            # Player_3 的观测离锚点 9 秒（超出 2 秒窗口）→ 不确认
            _formal_sample("Player_3", timestamp_ms=12000, x_ft=12.0, y_ft=22.0),
            # Player_4 位置相差 40ft → 不确认
            _formal_sample("Player_4", timestamp_ms=4050, x_ft=53.0, y_ft=63.0),
        ],
    }
    audit = ctx_svc.build_bootstrap_binding_audit(
        job_id="job-audit", roster=roster, formal_roster_payload=formal_payload
    )
    assert audit is not None
    assert audit.roster_hash == roster.roster_hash
    by_player = {entry.canonical_player_id: entry for entry in audit.entries}
    assert by_player["Player_1"].confirmed is True
    assert by_player["Player_1"].method == "anchor_simultaneous_match"
    assert by_player["Player_1"].formal_canonical_player_id == "Player_1"
    assert by_player["Player_1"].evidence.time_delta_ms == 50
    assert by_player["Player_2"].confirmed is True
    assert by_player["Player_3"].confirmed is False
    assert by_player["Player_3"].reason in {
        "bootstrap_binding_no_formal_observation",
        "bootstrap_binding_outside_time_window",
    }
    assert by_player["Player_4"].confirmed is False
    assert audit.status == "partial"
    # 已确认映射是唯一可消费的 P 槽位 → 正式身份来源
    assert audit.p_slot_to_formal_player() == {"Player_1": "Player_1", "Player_2": "Player_2"}
    # 历史弱证据方法不再被用于确认
    assert all(entry.method != "temporal_fallback" for entry in audit.entries if entry.confirmed)


def test_multiview_binding_uses_the_anchor_views_source_timestamp():
    roster = AnalysisRosterSnapshotPayload(
        snapshot_id="source-time-test", owner_key="take-x", status="available",
        entries=[AnalysisRosterConfirmationEntry(
            canonical_player_id="Player_1", slot_index=0, candidate_id="candidate-b",
            source_view_id="cam_2", anchor_timestamp_ms=2200,
            anchor_court_xy=[10.0, 20.0], anchor_bbox=[20, 20, 40, 80],
        )],
    )
    sample = {
        "global_player_id": "global_player_7", "take_timestamp_ms": 1000,
        "x_ft": 10.0, "y_ft": 20.0,
        "view_observations": {
            "cam_1": {"view_status": "available", "source_timestamp_ms": 1000},
            "cam_2": {"view_status": "available", "source_timestamp_ms": 2200},
        },
    }
    manifest = {"schema_version": "global-player-roster.v1", "players": [
        {"global_player_id": "global_player_7", "player_id": "Player_3"}
    ]}
    audit = ctx_svc.build_bootstrap_binding_audit(
        job_id="job-source-time", roster=roster,
        formal_roster_payload={"samples": [sample]}, formal_roster_manifest=manifest,
    )
    assert audit is not None
    assert audit.entries[0].confirmed is True
    assert audit.entries[0].formal_canonical_player_id == "Player_3"
    assert audit.entries[0].evidence.view_id == "cam_2"
    assert audit.entries[0].evidence.time_delta_ms == 0

    sample["view_observations"]["cam_2"]["view_status"] = "unavailable"
    without_b = ctx_svc.build_bootstrap_binding_audit(
        job_id="job-source-time", roster=roster,
        formal_roster_payload={"samples": [sample]}, formal_roster_manifest=manifest,
    )
    assert without_b is not None
    assert without_b.entries[0].confirmed is False


def test_binding_audit_is_absent_without_roster(db):
    take_id = make_take(db)
    assert ctx_svc.build_bootstrap_binding_audit(job_id="job-x", roster=None, formal_roster_payload={}) is None


def test_binding_audit_refuses_same_number_without_anchor_evidence(db):
    """只有相同 Player_N 字符串、没有同时刻证据时不得确认。"""
    take_id = make_take(db)
    roster = ctx_svc.freeze_roster_snapshot(
        db,
        capture_take_id=take_id,
        video_id=None,
        job_id="job-audit-same-number",
        request=RosterConfirmationRequest(entries=four_entries()[:2]),
        match_format="singles",
    )
    assert roster.status == "available"
    audit = ctx_svc.build_bootstrap_binding_audit(
        job_id="job-audit-same-number",
        roster=roster,
        formal_roster_payload={"player_roster": [{"player_id": "Player_1"}], "samples": []},
    )
    assert audit is not None
    entry = audit.entries[0]
    assert entry.canonical_player_id == "Player_1"
    assert entry.confirmed is False
    assert entry.formal_canonical_player_id is None
    assert entry.reason == "bootstrap_binding_no_formal_observation"
    assert audit.status == "unavailable"


def test_binding_audit_reports_conflicting_slots_without_silent_renumber(db):
    """两个槽位竞争同一正式球员时两个槽位都不确认，也不改写编号。"""
    take_id = make_take(db)
    entries = four_entries()
    # 让 P1 与 P2 的锚点落在同一时刻、同一位置，去竞争同一个正式球员。
    entries[1] = entries[1].model_copy(
        update={"anchor_timestamp_ms": entries[0].anchor_timestamp_ms, "anchor_court_xy": [10.2, 20.3]}
    )
    roster = ctx_svc.freeze_roster_snapshot(
        db,
        capture_take_id=take_id,
        video_id=None,
        job_id="job-audit-conflict",
        request=RosterConfirmationRequest(entries=entries),
    )
    audit = ctx_svc.build_bootstrap_binding_audit(
        job_id="job-audit-conflict",
        roster=roster,
        formal_roster_payload={
            "player_roster": [{"player_id": "Player_1"}],
            "samples": [_formal_sample("Player_1", timestamp_ms=1000, x_ft=10.2, y_ft=20.3)],
        },
    )
    assert audit is not None
    contested = [
        entry
        for entry in audit.entries
        if entry.canonical_player_id in {"Player_1", "Player_2"}
    ]
    assert all(entry.confirmed is False for entry in contested)
    assert any(entry.reason == "bootstrap_binding_conflicting_slots" for entry in contested)
    assert audit.p_slot_to_formal_player() == {}


def test_binding_audit_marks_ambiguous_when_two_players_are_indistinguishable(db):
    """同一时刻有两个正式球员都满足几何门槛 → 歧义，不确认。"""
    take_id = make_take(db)
    roster = ctx_svc.freeze_roster_snapshot(
        db,
        capture_take_id=take_id,
        video_id=None,
        job_id="job-audit-ambiguous",
        request=RosterConfirmationRequest(entries=four_entries()[:2]),
        match_format="singles",
    )
    audit = ctx_svc.build_bootstrap_binding_audit(
        job_id="job-audit-ambiguous",
        roster=roster,
        formal_roster_payload={
            "player_roster": [{"player_id": "Player_1"}, {"player_id": "Player_2"}],
            "samples": [
                _formal_sample("Player_1", timestamp_ms=1000, x_ft=10.0, y_ft=20.0),
                _formal_sample("Player_2", timestamp_ms=1000, x_ft=10.1, y_ft=20.1),
            ],
        },
    )
    assert audit is not None
    entry = audit.entries[0]
    assert entry.confirmed is False
    assert entry.reason == "bootstrap_binding_ambiguous_match"
    assert audit.p_slot_to_formal_player() == {}


def test_binding_audit_fails_closed_when_anchor_evidence_is_missing(db):
    """没有画面/球场锚点时，不能把槽位连续性当作身份确认。

    冻结层（任务 3.5）已经会拒绝缺锚点的名册，所以这里**直接构造**名册负载，
    单独验证审计自身的护栏——历史快照里可能存在结构不完整的条目。
    """
    entries = four_entries()
    entries[0] = entries[0].model_copy(update={"anchor_court_xy": None, "anchor_bbox": None})
    roster = AnalysisRosterSnapshotPayload(
        snapshot_id="snap-missing-anchor",
        owner_key="take-audit-missing-anchor",
        status="available",
        entries=entries,
    )
    audit = ctx_svc.build_bootstrap_binding_audit(
        job_id="job-audit-missing-anchor",
        roster=roster,
        formal_roster_payload={
            "player_roster": [{"player_id": "Player_1"}],
            # 没有 samples/位置证据，不能确认 Player_1 的正式身份。
            "samples": [],
        },
    )
    assert audit is not None
    player = next(entry for entry in audit.entries if entry.canonical_player_id == "Player_1")
    assert player.formal_canonical_player_id is None
    assert player.method == "unavailable"
    assert player.confirmed is False
    assert player.reason == "bootstrap_binding_anchor_evidence_missing"
    assert audit.status == "unavailable"


def test_roster_freeze_rejects_structurally_invalid_entries(db):
    """槽位数量、候选唯一性与来源完整性都要校验；不合法不得冻结成 available。"""
    take_id = make_take(db)
    entries = [
        entry.model_copy(update={"candidate_id": f"bp_{index}", "slot_index": index})
        for index, entry in enumerate(four_entries())
    ]

    duplicated = list(entries)
    duplicated[3] = duplicated[3].model_copy(update={"candidate_id": "bp_0"})
    snapshot = ctx_svc.freeze_roster_snapshot(
        db,
        capture_take_id=take_id,
        video_id=None,
        job_id="job-roster-dup",
        request=RosterConfirmationRequest(entries=duplicated, initial_team_a_end="end_a"),
    )
    assert snapshot.status == "insufficient_candidates"
    assert snapshot.unavailable_reason == "analysis_roster_invalid_entries"

    missing_source = list(entries)
    missing_source[2] = missing_source[2].model_copy(update={"source_view_id": None})
    snapshot2 = ctx_svc.freeze_roster_snapshot(
        db,
        capture_take_id=take_id,
        video_id=None,
        job_id="job-roster-nosource",
        request=RosterConfirmationRequest(entries=missing_source, initial_team_a_end="end_a"),
    )
    assert snapshot2.status == "insufficient_candidates"
    assert snapshot2.unavailable_reason == "analysis_roster_invalid_entries"

    missing_anchor = list(entries)
    missing_anchor[1] = missing_anchor[1].model_copy(
        update={"anchor_bbox": None, "anchor_court_xy": None}
    )
    snapshot3 = ctx_svc.freeze_roster_snapshot(
        db,
        capture_take_id=take_id,
        video_id=None,
        job_id="job-roster-noanchor",
        request=RosterConfirmationRequest(entries=missing_anchor, initial_team_a_end="end_a"),
    )
    assert snapshot3.status == "insufficient_candidates"
    assert snapshot3.unavailable_reason == "analysis_roster_invalid_entries"

    ok = ctx_svc.freeze_roster_snapshot(
        db,
        capture_take_id=take_id,
        video_id=None,
        job_id="job-roster-ok",
        request=RosterConfirmationRequest(entries=entries, initial_team_a_end="end_a"),
    )
    assert ok.status == "available"
    assert [entry.slot_index for entry in ok.entries] == [0, 1, 2, 3]
    assert [entry.candidate_id for entry in ok.entries] == ["bp_0", "bp_1", "bp_2", "bp_3"]


# ── canonical artifact 的上下文引用（4.4）──


def test_trajectory_identity_map_is_gated_by_the_binding_audit(tmp_path):
    """未通过审计的槽位不得把融合轨迹解析成正式 Player_N（指标随之降级）。"""
    from app.services import canonical_shot_rally_events as events
    from app.schemas.rally_context import (
        BootstrapBindingAuditEntry,
        BootstrapBindingAuditPayload,
    )

    manifest = {
        "schema_version": "global-player-roster.v1",
        "players": [
            {
                "global_player_id": "global_player_1",
                "player_id": "Player_1",
                "mapping_confirmed": True,
                "mapping_method": "direct_reference_binding",
            },
            {
                "global_player_id": "global_player_2",
                "player_id": "Player_2",
                "mapping_confirmed": True,
                "mapping_method": "direct_reference_binding",
            },
        ],
    }
    manifest_path = tmp_path / "roster_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    class _Storage:
        def roster_manifest_json_path(self, job_id: str):
            return manifest_path

    roster = {
        "entries": [
            {"canonical_player_id": "Player_1"},
            {"canonical_player_id": "Player_2"},
        ]
    }

    # 无审计（legacy 路径）：保持既往行为
    legacy = events._frozen_trajectory_identity_map(_Storage(), "job-1", roster)
    assert legacy == {"global_player_1": "Player_1", "global_player_2": "Player_2"}

    audit = BootstrapBindingAuditPayload(
        job_id="job-1",
        roster_hash="hash",
        status="partial",
        unavailable_reason="bootstrap_binding_partial",
        entries=[
            BootstrapBindingAuditEntry(
                canonical_player_id="Player_1",
                formal_canonical_player_id="Player_1",
                method="anchor_simultaneous_match",
                confirmed=True,
            ),
            BootstrapBindingAuditEntry(
                canonical_player_id="Player_2",
                method="unavailable",
                confirmed=False,
                reason="bootstrap_binding_insufficient_evidence",
            ),
        ],
    )
    gated = events._frozen_trajectory_identity_map(_Storage(), "job-1", roster, audit)
    assert gated == {"global_player_1": "Player_1"}
    assert audit.p_slot_to_formal_player() == {"Player_1": "Player_1"}


def test_formal_window_plan_hash_ignores_context_references():
    """挂上源引用不改变 plan_hash：既有任务的 windowPlanHash 不会失配。"""
    from app.vision.match_state.artifact import AnalysisWindowPlan

    plain = AnalysisWindowPlan.create("run-1", [{"segment_id": "s1", "start_ms": 0, "end_ms": 1000}])
    enriched = AnalysisWindowPlan.create(
        "run-1",
        [
            {
                "segment_id": "s1",
                "start_ms": 0,
                "end_ms": 1000,
                "source_rally_segment_id": "seg-manual-1",
                "source_start_event_id": "te_1",
                "context_rally_id": "seg-manual-1",
                "context_hash": "deadbeef",
                "binding_method": "direct_segment_link",
                "binding_diagnostics": ["ok"],
            }
        ],
    )
    assert plain.plan_hash == enriched.plan_hash
    assert enriched.windows[0]["context_rally_id"] == "seg-manual-1"
    assert json.loads(json.dumps(enriched.to_dict()))["windows"][0]["binding_method"] == "direct_segment_link"


# ── Job 签名与 feature gate（4.2 / 5.3）──


def _job_payload(**overrides):
    from app.schemas.analysis import AnalysisJobCreate, AnalysisUploadMetadata

    metadata = AnalysisUploadMetadata(
        fileName="a.mp4",
        matchTitle="t",
        venue="v",
        matchDate="2026-09-20",
        matchFormat="doubles",
        cameraAngle="elevated",
        athleteLabel="a",
        level="l",
    )
    return AnalysisJobCreate(metadata=metadata, videoId="video-1", **overrides)


def test_job_signature_is_roster_and_context_sensitive():
    """相同媒体 + 不同名册或上下文 → 不同输入签名，因此绝不会复用旧结果。"""
    from app.services.job_orchestration import analysis_signature

    payload = _job_payload()
    base_input, base_config = analysis_signature(payload)
    roster_a, config_a = analysis_signature(payload, roster_hash="roster-a", context_input_hash="ctx-1")
    roster_b, config_b = analysis_signature(payload, roster_hash="roster-b", context_input_hash="ctx-1")
    context_b, config_c = analysis_signature(payload, roster_hash="roster-a", context_input_hash="ctx-2")

    assert len({base_input, roster_a, roster_b, context_b}) == 4
    # 配置签名不受名册/上下文影响（它们属于"输入"维度）
    assert {base_config, config_a, config_b, config_c} == {base_config}
    # legacy 单摄任务逐字不变：不传 hash 时不写入签名材料
    assert analysis_signature(payload) == (base_input, base_config)


def test_job_signature_separates_new_and_legacy_flow():
    """同一媒体选择新/旧流程时不能被幂等去重混为一个任务。"""
    from app.services.job_orchestration import analysis_signature

    new_payload = _job_payload(useRallyContext=True)
    legacy_payload = _job_payload(useRallyContext=False)
    assert analysis_signature(new_payload) != analysis_signature(legacy_payload)


def test_new_flow_is_the_settings_default():
    from app.core.config import Settings

    assert Settings().rally_context_enabled is True


def test_consumers_enabled_mirrors_settings_feature_gate(monkeypatch):
    """context consumer 仍可通过部署开关关闭，关闭时上游不冻结任何上下文。"""
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "rally_context_enabled", False, raising=False)
    assert ctx_svc._consumers_enabled() is False  # noqa: SLF001
    monkeypatch.setattr(settings, "rally_context_enabled", True, raising=False)
    assert ctx_svc._consumers_enabled() is True  # noqa: SLF001


def test_bootstrap_reports_feature_gate_state(db, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "rally_context_enabled", False, raising=False)
    disabled = ctx_svc.build_player_bootstrap(db, capture_take_id="take-1")
    assert disabled.consumers_enabled is False
    monkeypatch.setattr(settings, "rally_context_enabled", True, raising=False)
    enabled = ctx_svc.build_player_bootstrap(db, capture_take_id="take-1")
    assert enabled.consumers_enabled is True
