"""player display diagnostics（player-display-diagnostics.v1）单元测试。

覆盖（tasks 5.1）：
- contract schema / validator（canonical Player_N、expected_region_status != available
  时 eligible_detections_in_expected_gate 必须为 null、重复 (tick, player, view) 拒绝）；
- 分层断裂状态：eligible_detection_present=true, position_present=false（break_stage=
  position_join）；position_present=true, court_position_present=false（break_stage=
  projection）；
- expected region 只来自 pre-tick prediction；prediction 缺失 → count=null 非 0；
- 共享 build_expected_player_region 与 guidance 同一几何（radius 规则）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import pytest

from app.vision.multiview.court_frame import CourtOrientation
from app.vision.multiview.guidance import CrossViewGuidancePolicy, GuidanceGenerator
from app.vision.multiview.player_display_diagnostics import (
    build_display_diagnostics_rows,
    build_expected_player_region,
    build_player_display_diagnostics_payload,
    validate_player_display_diagnostics,
)

IDENTITY_ORIENTATION = CourtOrientation.identity

# 球场→图像方向：10x 缩放（球场英尺坐标 ×10 → 像素）
TEST_INVERSE_HOMOGRAPHY = [
    [10.0, 0.0, 0.0],
    [0.0, 10.0, 0.0],
    [0.0, 0.0, 1.0],
]

POLICY = CrossViewGuidancePolicy(base_roi_margin_px=40.0, uncertainty_to_px_scale=12.0, max_roi_margin_px=160.0)


# ---- 轻量 ViewFrameResult 替身 ----------------------------------------------


@dataclass
class _FakeDet:
    player_id: str
    track_id: int
    image_footpoint: tuple[float, float]
    bbox: tuple[float, float, float, float] = (0.0, 0.0, 10.0, 50.0)


@dataclass
class _FakePos:
    track_id: int
    court_position: list[float] | None
    projection_status: str | None = "inside_court"
    projection_confidence: float | None = 0.9


@dataclass
class _FakeViewResult:
    frame_detections: list = field(default_factory=list)
    frame_positions: list = field(default_factory=list)


# ---- 测试几何：expected region 计算 ------------------------------------------


def _geometry(view_id: str = "cam_1", width: int = 640, height: int = 480) -> dict:
    return {
        view_id: {
            "orientation": IDENTITY_ORIENTATION,
            "inverse_homography": TEST_INVERSE_HOMOGRAPHY,
            "frame_width": width,
            "frame_height": height,
            "available": True,
        }
    }


def _roster(*, player_id: str = "Player_1", lifecycle: str = "confirmed", visibility: str = "lost") -> list[dict]:
    return [
        {
            "global_player_id": "global_player_1",
            "player_id": player_id,
            "lifecycle": lifecycle,
            "bindings": {
                "cam_1": {"view_player_id": "Player_1", "visibility": visibility},
                "cam_2": {"view_player_id": "Player_3", "visibility": visibility},
            },
        }
    ]


def _predictions(x: float = 10.0, y: float = 20.0, unc: float = 2.0) -> dict:
    return {"global_player_1": (x, y, unc)}


# ---- 1. 共享 expected region 几何与 guidance 一致 -----------------------------


def test_build_expected_player_region_matches_guidance_roi_rule() -> None:
    region = build_expected_player_region(
        predicted_canonical_position=(10.0, 20.0),
        uncertainty_ft=2.0,
        orientation=IDENTITY_ORIENTATION,
        inverse_homography=TEST_INVERSE_HOMOGRAPHY,
        frame_width=640,
        frame_height=480,
        policy=POLICY,
    )
    assert region.status == "available"
    # 40 + 2*12 = 64px（cap 160）
    assert region.radius_px == 64.0
    # 图像位置 (10*10, 20*10) = (100, 200)；roi = (100±64, 200±64)
    assert region.expected_image_position == (100.0, 200.0)
    x1, y1, x2, y2 = region.roi  # type: ignore[misc]
    assert x1 == pytest.approx(36.0)
    assert x2 == pytest.approx(164.0)
    assert y1 == pytest.approx(136.0)
    assert y2 == pytest.approx(264.0)


def test_build_expected_player_region_cap_at_max_margin() -> None:
    region = build_expected_player_region(
        predicted_canonical_position=(10.0, 20.0),
        uncertainty_ft=10.0,  # 40 + 10*12 = 160 → 恰为 cap（未超 max_uncertainty_ft=8 时需用 max_uncertainty 传参放开）
        orientation=IDENTITY_ORIENTATION,
        inverse_homography=TEST_INVERSE_HOMOGRAPHY,
        frame_width=640,
        frame_height=480,
        policy=POLICY,
        max_uncertainty_ft=20.0,  # 放宽 uncertainty 门限以验证 ROI cap
    )
    assert region.status == "available"
    assert region.radius_px == 160.0


# ---- 2. expected region 状态语义（null 而非 0） ------------------------------


def test_prediction_unavailable_yields_null_count() -> None:
    rows = build_display_diagnostics_rows(
        canonical_tick=210,
        timestamp_ms=7000.0,
        reference_view_id="cam_1",
        view_results={"cam_1": _FakeViewResult(), "cam_2": _FakeViewResult()},
        frame_status={"cam_1": "available", "cam_2": "available"},
        predictions={},  # 无 pre-tick prediction
        view_geometry=_geometry(),
        policy=POLICY,
        roster=_roster(),
        association_decisions=[],
        guidance_decisions=[],
    )
    assert len(rows) == 2
    for row in rows:
        assert row.expected_region_status == "prediction_unavailable"
        # 非 available => 计数必须为 null（MUST NOT 写 0）
        assert row.eligible_detections_in_expected_gate is None


def test_uncertainty_too_high_yields_null_count() -> None:
    rows = build_display_diagnostics_rows(
        canonical_tick=210,
        timestamp_ms=7000.0,
        reference_view_id="cam_1",
        view_results={"cam_1": _FakeViewResult(), "cam_2": _FakeViewResult()},
        frame_status={"cam_1": "available", "cam_2": "available"},
        predictions=_predictions(unc=99.0),  # 超 max_uncertainty_ft=8
        view_geometry=_geometry(),
        policy=POLICY,
        roster=_roster(),
        association_decisions=[],
        guidance_decisions=[],
    )
    for row in rows:
        assert row.expected_region_status == "uncertainty_too_high"
        assert row.eligible_detections_in_expected_gate is None


# ---- 3. 分层断裂状态 ---------------------------------------------------------


def test_eligible_detection_without_position_breaks_at_position_join() -> None:
    """frame_detections 有该 track，但 frame_positions 无 → position_join 断裂。"""
    view = _FakeViewResult(
        frame_detections=[
            _FakeDet(player_id="Player_1", track_id=7, image_footpoint=(100.0, 200.0)),
        ],
        frame_positions=[],  # 无 position
    )
    rows = build_display_diagnostics_rows(
        canonical_tick=210,
        timestamp_ms=7000.0,
        reference_view_id="cam_1",
        view_results={"cam_1": view},
        frame_status={"cam_1": "available"},
        predictions=_predictions(),  # expected region available
        view_geometry=_geometry(),
        policy=POLICY,
        roster=_roster(),
        association_decisions=[],
        guidance_decisions=[],
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.eligible_detection_present is True
    assert row.position_present is False
    assert row.court_position_present is False
    assert row.formal_observation_emitted is False
    # eligible detection 计数应命中（footpoint 在 region 内）
    assert row.eligible_detections_in_expected_gate == 1
    assert row.expected_region_status == "available"


def test_position_without_court_projection_breaks_at_projection() -> None:
    """frame_positions 有该 track，但 court_position=None → projection 断裂。"""
    view = _FakeViewResult(
        frame_detections=[
            _FakeDet(player_id="Player_1", track_id=7, image_footpoint=(100.0, 200.0)),
        ],
        frame_positions=[
            _FakePos(track_id=7, court_position=None, projection_status="outside_court"),
        ],
    )
    rows = build_display_diagnostics_rows(
        canonical_tick=210,
        timestamp_ms=7000.0,
        reference_view_id="cam_1",
        view_results={"cam_1": view},
        frame_status={"cam_1": "available"},
        predictions=_predictions(),
        view_geometry=_geometry(),
        policy=POLICY,
        roster=_roster(),
        association_decisions=[],
        guidance_decisions=[],
    )
    row = rows[0]
    assert row.eligible_detection_present is True
    assert row.position_present is True
    assert row.court_position_present is False
    assert row.formal_observation_emitted is False
    assert row.projection_status == "outside_court"


def test_full_chain_present() -> None:
    """完整链路：detection + position + court_position → formal observation 可能为 True。"""
    view = _FakeViewResult(
        frame_detections=[
            _FakeDet(player_id="Player_1", track_id=7, image_footpoint=(100.0, 200.0)),
        ],
        frame_positions=[
            _FakePos(track_id=7, court_position=[10.0, 20.0], projection_status="inside_court"),
        ],
    )
    rows = build_display_diagnostics_rows(
        canonical_tick=210,
        timestamp_ms=7000.0,
        reference_view_id="cam_1",
        view_results={"cam_1": view},
        frame_status={"cam_1": "available"},
        predictions=_predictions(),
        view_geometry=_geometry(),
        policy=POLICY,
        roster=_roster(),
        association_decisions=[],
        guidance_decisions=[],
    )
    row = rows[0]
    assert row.eligible_detection_present is True
    assert row.position_present is True
    assert row.court_position_present is True
    assert row.formal_observation_emitted is True


# ---- 4. association / guidance 只读决策 --------------------------------------


def test_association_decision_reason_surfaced() -> None:
    view = _FakeViewResult(frame_detections=[], frame_positions=[])
    decision = type(
        "D",
        (),
        {"view_id": "cam_1", "observation_key": "Player_1", "global_id": None, "reason": "unresolved_no_slot"},
    )()
    rows = build_display_diagnostics_rows(
        canonical_tick=210,
        timestamp_ms=7000.0,
        reference_view_id="cam_1",
        view_results={"cam_1": view},
        frame_status={"cam_1": "available"},
        predictions=_predictions(),
        view_geometry=_geometry(),
        policy=POLICY,
        roster=_roster(),
        association_decisions=[decision],
        guidance_decisions=[],
    )
    row = rows[0]
    assert row.global_associated is False
    assert row.association_reason == "unresolved_no_slot"


def test_guidance_decision_reason_surfaced() -> None:
    view = _FakeViewResult(frame_detections=[], frame_positions=[])
    decision = type(
        "G",
        (),
        {"global_player_id": "global_player_1", "target_view": "cam_1", "status": "not_eligible", "reason": "cooldown"},
    )()
    rows = build_display_diagnostics_rows(
        canonical_tick=210,
        timestamp_ms=7000.0,
        reference_view_id="cam_1",
        view_results={"cam_1": view},
        frame_status={"cam_1": "available"},
        predictions=_predictions(),
        view_geometry=_geometry(),
        policy=POLICY,
        roster=_roster(),
        association_decisions=[],
        guidance_decisions=[decision],
    )
    row = rows[0]
    assert row.guidance_status == "not_eligible"
    assert row.guidance_skip_reason == "cooldown"


# ---- 5. 只处理 confirmed player × available view -----------------------------


def test_tentative_player_skipped() -> None:
    rows = build_display_diagnostics_rows(
        canonical_tick=210,
        timestamp_ms=7000.0,
        reference_view_id="cam_1",
        view_results={"cam_1": _FakeViewResult(), "cam_2": _FakeViewResult()},
        frame_status={"cam_1": "available", "cam_2": "available"},
        predictions=_predictions(),
        view_geometry=_geometry(),
        policy=POLICY,
        roster=_roster(lifecycle="tentative"),
        association_decisions=[],
        guidance_decisions=[],
    )
    assert rows == []


def test_unavailable_view_skipped() -> None:
    rows = build_display_diagnostics_rows(
        canonical_tick=210,
        timestamp_ms=7000.0,
        reference_view_id="cam_1",
        view_results={"cam_1": _FakeViewResult()},
        frame_status={"cam_1": "unavailable"},
        predictions=_predictions(),
        view_geometry=_geometry(),
        policy=POLICY,
        roster=_roster(),
        association_decisions=[],
        guidance_decisions=[],
    )
    assert rows == []


# ---- 6. validator / payload ---------------------------------------------------


def test_validator_rejects_non_canonical_player_id() -> None:
    payload = {
        "schema_version": "player-display-diagnostics.v1",
        "job_id": "job-1",
        "video_id": None,
        "reference_view_id": "cam_1",
        "status": "available",
        "detail": "",
        "rows": [{"canonical_tick": 0, "timestamp_ms": 0.0, "player_id": "global_player_1", "view_id": "cam_1"}],
    }
    with pytest.raises(ValueError):
        validate_player_display_diagnostics(payload)


def test_validator_rejects_null_region_with_count() -> None:
    payload = {
        "schema_version": "player-display-diagnostics.v1",
        "job_id": "job-1",
        "video_id": None,
        "reference_view_id": "cam_1",
        "status": "available",
        "detail": "",
        "rows": [
            {
                "canonical_tick": 0,
                "timestamp_ms": 0.0,
                "player_id": "Player_1",
                "view_id": "cam_1",
                "expected_region_status": "prediction_unavailable",
                "eligible_detections_in_expected_gate": 0,  # MUST be null
            }
        ],
    }
    with pytest.raises(ValueError):
        validate_player_display_diagnostics(payload)


def test_payload_roundtrip() -> None:
    rows = build_display_diagnostics_rows(
        canonical_tick=210,
        timestamp_ms=7000.0,
        reference_view_id="cam_1",
        view_results={"cam_1": _FakeViewResult(), "cam_2": _FakeViewResult()},
        frame_status={"cam_1": "available", "cam_2": "available"},
        predictions={},
        view_geometry=_geometry(),
        policy=POLICY,
        roster=_roster(),
        association_decisions=[],
        guidance_decisions=[],
    )
    payload = build_player_display_diagnostics_payload(
        job_id="job-1",
        video_id=None,
        reference_view_id="cam_1",
        rows=rows,
    )
    assert payload["schema_version"] == "player-display-diagnostics.v1"
    assert len(payload["rows"]) == 2
    validate_player_display_diagnostics(payload)
    # JSON 可序列化
    json.dumps(payload)


# ---- 7. guidance 只读决策不改变 generate() 行为（回归保护） ---------------------


def test_guidance_decision_records_but_does_not_change_generate() -> None:
    generator = GuidanceGenerator(policy=POLICY)
    # 未生成场景：binding observed → target_not_missing
    state = type(
        "S",
        (),
        {
            "global_player_id": "global_player_1",
            "lifecycle": "confirmed",
            "cross_view_anchored": True,
            "view_bindings": {
                "cam_1": type("B", (), {"visibility": "observed"})(),
            },
        },
    )()
    result = generator.generate(
        global_state=state,
        target_view="cam_1",
        orientation=IDENTITY_ORIENTATION,
        inverse_homography=TEST_INVERSE_HOMOGRAPHY,
        now_take_ms=7000.0,
        tick=210,
        frame_width=640,
        frame_height=480,
        prediction=(10.0, 20.0, 2.0),
        strict_donor=False,
    )
    assert result is None
    assert generator.last_decisions
    decision = generator.last_decisions[-1]
    assert decision.status == "not_eligible"
    assert decision.reason == "target_not_missing"


# ---- 8. API 集成测试（tasks 5.2）--------------------------------------------


def _make_api_job(job_id: str = "job-diag") -> "object":
    from app.schemas.analysis import AnalysisJobSummary

    return AnalysisJobSummary(
        id=job_id,
        status="completed",
        stage="report",
        progress=100,
        createdAt="2026-08-13T00:00:00+00:00",
        updatedAt="2026-08-13T00:00:00+00:00",
        metadata={
            "fileName": "joint.mp4",
            "fileSize": 10,
            "matchTitle": "Diag test",
            "venue": "Test court",
            "matchDate": "2026-08-13",
            "matchFormat": "doubles",
            "cameraAngle": "elevated",
            "athleteLabel": "Test players",
            "level": "MVP",
        },
        stages=[],
        analysisMode="real",
        analysisKind="multiview",
        executionMode="joint_tracking_v2",
        jointRunId="run-diag",
        referenceViewId="cam_1",
        debugTraceEnabled=False,
    )


def _write_diag_artifact(storage, job_id: str) -> None:
    rows = build_display_diagnostics_rows(
        canonical_tick=210,
        timestamp_ms=7000.0,
        reference_view_id="cam_1",
        view_results={"cam_1": _FakeViewResult(), "cam_2": _FakeViewResult()},
        frame_status={"cam_1": "available", "cam_2": "available"},
        predictions={},
        view_geometry=_geometry(),
        policy=POLICY,
        roster=_roster(),
        association_decisions=[],
        guidance_decisions=[],
    )
    payload = build_player_display_diagnostics_payload(
        job_id=job_id, video_id=None, reference_view_id="cam_1", rows=rows
    )
    path = storage.player_display_diagnostics_json_path(job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    storage.write_json(path, payload)


def test_api_window_query_filters_player_and_time(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from app.api import routes_analysis
    from app.main import app
    from app.services.mock_analysis import JOBS, RESULTS
    from app.services.storage_service import StorageService

    storage = StorageService()
    storage.settings.outputs_dir = tmp_path / "outputs"
    storage.settings.ensure_data_dirs()
    job = _make_api_job()
    single = job.model_copy(update={"id": "job-single", "analysisKind": "single_view"})
    _write_diag_artifact(storage, job.id)
    # 无产物任务（用于 unavailable 断言）
    no_artifact_job = _make_api_job("job-no-diag")

    monkeypatch.setattr(routes_analysis, "_STORAGE", storage)
    snapshot = JOBS.copy(), RESULTS.copy()
    JOBS.clear()
    RESULTS.clear()
    JOBS.update({job.id: job, single.id: single, no_artifact_job.id: no_artifact_job})
    try:
        with TestClient(app) as client:
            # 1) 正常窗口查询：按 Player_1 过滤，返回两路行
            resp = client.get(
                f"/api/analysis/jobs/{job.id}/multiview/players/Player_1/display-diagnostics",
                params={"timestamp_ms": 7000, "window_ms": 500},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["player_id"] == "Player_1"
            views = {row["view_id"] for row in body["rows"]}
            assert views == {"cam_1", "cam_2"}
            assert all(row["player_id"] == "Player_1" for row in body["rows"])
            # 2) 非 multiview 任务 → not_applicable
            na = client.get(
                f"/api/analysis/jobs/{single.id}/multiview/players/Player_1/display-diagnostics",
                params={"timestamp_ms": 7000},
            )
            assert na.status_code == 404
            assert na.json()["error"]["code"] == "not_applicable"
            # 3) 非法 player_id → 422
            bad = client.get(
                f"/api/analysis/jobs/{job.id}/multiview/players/global_player_1/display-diagnostics",
                params={"timestamp_ms": 7000},
            )
            assert bad.status_code == 422
            # 4) 产物缺失 → 结构化 unavailable（HTTP 200，非 404；fix-multiview-player-identity T1.3）
            missing = client.get(
                f"/api/analysis/jobs/{no_artifact_job.id}/multiview/players/Player_1/display-diagnostics",
                params={"timestamp_ms": 7000},
            )
            assert missing.status_code == 200
            assert missing.json()["error"]["code"] == "unavailable"
            # 5) 查询窗口外 → 空 rows
            far = client.get(
                f"/api/analysis/jobs/{job.id}/multiview/players/Player_1/display-diagnostics",
                params={"timestamp_ms": 999999},
            )
            assert far.status_code == 200
            assert far.json()["rows"] == []
    finally:
        JOBS.clear()
        JOBS.update(snapshot[0])
        RESULTS.clear()
        RESULTS.update(snapshot[1])


def test_duplicate_player_view_rows_deduped() -> None:
    """fix-multiview-player-identity T1 收尾：roster 快照同一 (player_id, view_id)
    出现多次（两个 global 绑定同一 Player_N 的身份冲突）时保留首行，避免 validator
    duplicate 抛错导致整个产物 failed。"""
    # 构造两个 global player 绑定同一 reference Player_1（身份冲突场景）
    roster_dup = [
        {
            "global_player_id": "global_player_1",
            "player_id": "Player_1",
            "lifecycle": "confirmed",
            "bindings": {
                "cam_1": {"view_player_id": "Player_1", "visibility": "observed"},
                "cam_2": {"view_player_id": "Player_3", "visibility": "observed"},
            },
        },
        {
            "global_player_id": "global_player_2",
            "player_id": "Player_1",  # 冲突：第二个 global 也绑定 reference Player_1
            "lifecycle": "confirmed",
            "bindings": {
                "cam_1": {"view_player_id": "Player_1", "visibility": "observed"},
            },
        },
    ]
    view = _FakeViewResult(
        frame_detections=[
            _FakeDet(player_id="Player_1", track_id=7, image_footpoint=(100.0, 200.0)),
        ],
        frame_positions=[
            _FakePos(track_id=7, court_position=[10.0, 20.0], projection_status="inside_court"),
        ],
    )
    rows = build_display_diagnostics_rows(
        canonical_tick=210,
        timestamp_ms=7000.0,
        reference_view_id="cam_1",
        view_results={"cam_1": view},
        frame_status={"cam_1": "available"},
        predictions=_predictions(),
        view_geometry=_geometry(),
        policy=POLICY,
        roster=roster_dup,
        association_decisions=[],
        guidance_decisions=[],
    )
    # 去重后 (Player_1, cam_1) 只保留一行
    player_view_pairs = [(r.player_id, r.view_id) for r in rows]
    assert len(player_view_pairs) == len(set(player_view_pairs))
    cam1_rows = [r for r in rows if r.view_id == "cam_1"]
    assert len(cam1_rows) == 1
    # 构建 payload 不再抛 duplicate
    payload = build_player_display_diagnostics_payload(
        job_id="job-dup", video_id=None, reference_view_id="cam_1", rows=rows
    )
    assert payload["status"] == "available"


def test_roster_conflict_flag_from_registry_counts() -> None:
    """fix-multiview-cam1-bootstrap-4player D4：reference 槽位冲突计数 → roster_conflict。"""
    view = _FakeViewResult(
        frame_detections=[
            _FakeDet(player_id="Player_1", track_id=7, image_footpoint=(100.0, 200.0)),
        ],
        frame_positions=[
            _FakePos(track_id=7, court_position=[10.0, 20.0], projection_status="inside_court"),
        ],
    )
    conflicts = {("cam_1", "Player_1"): 3}
    rows = build_display_diagnostics_rows(
        canonical_tick=210,
        timestamp_ms=7000.0,
        reference_view_id="cam_1",
        view_results={"cam_1": view},
        frame_status={"cam_1": "available"},
        predictions=_predictions(),
        view_geometry=_geometry(),
        policy=POLICY,
        roster=_roster(),
        association_decisions=[],
        guidance_decisions=[],
        roster_conflicts=conflicts,
    )
    assert rows
    cam1_rows = [r for r in rows if r.view_id == "cam_1"]
    assert cam1_rows[0].roster_conflict is True
    # 无冲突的 view（cam_2 或未冲突槽位）→ False
    cam2_rows = [r for r in rows if r.view_id == "cam_2"]
    assert all(r.roster_conflict is False for r in cam2_rows)


def test_roster_conflict_defaults_false_without_arg() -> None:
    """旧调用（不传 roster_conflicts）→ roster_conflict 缺省 False，不报错。"""
    view = _FakeViewResult(frame_detections=[], frame_positions=[])
    rows = build_display_diagnostics_rows(
        canonical_tick=210,
        timestamp_ms=7000.0,
        reference_view_id="cam_1",
        view_results={"cam_1": view},
        frame_status={"cam_1": "available"},
        predictions=_predictions(),
        view_geometry=_geometry(),
        policy=POLICY,
        roster=_roster(),
        association_decisions=[],
        guidance_decisions=[],
    )
    assert all(r.roster_conflict is False for r in rows)
