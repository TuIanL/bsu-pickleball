"""joint 模式视觉层产物测试（2026-08-13 修复：此前 compose_joint_result artifacts 全空）。

- tracking_overlay 从 debug trace 聚合（status available / no_detections / unavailable）
- compose_joint_result 产出 tracking_overlay_url / heatmaps_url / pose_overlay_status 等
- 聚合 stage A/B 不再依赖 viewRuns（joint 完成即 succeeded）
"""

from __future__ import annotations

from types import SimpleNamespace

from app.schemas.analysis import AnalysisJobSummary
from app.services.multiview_result_composer import MultiViewResultComposer
from app.services.joint_visual_artifacts import (
    JOINT_POSE_UNAVAILABLE,
    build_joint_tracking_overlay,
)


def _sample_trace() -> dict[str, object]:
    return {
        "schema_version": "joint_debug_trace.v1",
        "run_id": "mvr_t",
        "tick_count": 3,
        "ticks": [
            {
                "canonical_tick": 0,
                "canonical_timestamp_ms": 0.0,
                "reference_frame_index": 100,
                "views": {
                    "cam_1": {
                        "status": "available",
                        "detections": [
                            {
                                "bbox": [10.0, 20.0, 100.0, 200.0],
                                "track_id": 1,
                                "player_id": "Player_1",
                                "confidence": 0.9,
                                "image_footpoint": [55.0, 200.0],
                            }
                        ],
                    },
                    "cam_2": {"status": "available", "detections": []},
                },
            },
            {
                "canonical_tick": 1,
                "canonical_timestamp_ms": 33.3,
                "reference_frame_index": 102,
                "views": {
                    "cam_1": {
                        "status": "available",
                        "detections": [
                            {
                                "bbox": [11.0, 21.0, 101.0, 201.0],
                                "track_id": 1,
                                "player_id": "Player_1",
                                "confidence": 0.91,
                                "image_footpoint": [56.0, 201.0],
                            }
                        ],
                    },
                    "cam_2": {"status": "available", "detections": []},
                },
            },
            {
                "canonical_tick": 2,
                "canonical_timestamp_ms": 66.6,
                "reference_frame_index": 104,
                "views": {
                    "cam_1": {"status": "available", "detections": []},
                    "cam_2": {"status": "available", "detections": []},
                },
            },
        ],
    }


def test_tracking_overlay_aggregates_from_trace():
    """从 trace 聚合 reference view 检测：只取 reference view、逐 tick 一帧、bbox 原样。"""
    overlay = build_joint_tracking_overlay(
        job_id="job-p",
        video_id="vid",
        debug_trace=_sample_trace(),
        frame_size={"width": 1920, "height": 1080},
        fps=60.0,
        frame_stride=2,
        reference_view_id="cam_1",
    )
    assert overlay.status == "available"
    assert len(overlay.frames) == 2  # 只统计有检测的帧
    assert overlay.frames[0].frame_index == 100
    assert overlay.frames[0].timestamp_seconds == 0.0
    det = overlay.frames[0].detections[0]
    assert det.bbox == [10.0, 20.0, 100.0, 200.0]
    assert det.player_id == "Player_1"
    assert det.track_id == "1"
    assert det.source_width == 1920 and det.source_height == 1080


def test_tracking_overlay_no_detections():
    """trace 无检测 → status=no_detections。"""
    trace = {"ticks": [{
        "canonical_tick": 0, "canonical_timestamp_ms": 0.0, "reference_frame_index": 0,
        "views": {"cam_1": {"status": "available", "detections": []}},
    }]}
    overlay = build_joint_tracking_overlay(
        job_id="job-p", video_id="vid", debug_trace=trace,
        frame_size={"width": 640, "height": 480}, fps=30.0, frame_stride=1,
        reference_view_id="cam_1",
    )
    assert overlay.status == "no_detections"
    assert overlay.frames == []


def test_compose_joint_result_publishes_visual_artifacts(tmp_path):
    """compose_joint_result 产出 tracking_overlay/heatmaps/pose 契约。"""
    from app.schemas.analysis import AnalysisJobSummary
    from app.schemas.metrics import PerformanceMetrics
    from app.services.storage_service import StorageService

    storage = StorageService()
    take_dir = tmp_path / "take"
    storage.register_capture_job("job-p", take_dir)

    job = AnalysisJobSummary(
        id="job-p",
        status="completed",
        stage="report",
        progress=100,
        createdAt="2026-08-13T00:00:00+00:00",
        updatedAt="2026-08-13T00:00:00+00:00",
        videoId="vid",
        calibrationId="calib",
        analysisKind="multiview",
        executionMode="joint_tracking_v2",
        frameStride=2,
        sourceFps=60.0,
        clipStartMs=0,
        clipEndMs=60000,
        viewRuns={},
        referenceViewId="cam_1",
        jointViewInputs=[],
        metadata={
            "fileName": "joint.mp4",
            "fileSize": 10,
            "matchTitle": "Joint test",
            "venue": "Test court",
            "matchDate": "2026-08-13",
            "matchFormat": "doubles",
            "cameraAngle": "elevated",
            "athleteLabel": "Test players",
            "level": "MVP",
        },
        stages=[],
    )
    fused = {
        "schema_version": "fused_player_trajectory.v2",
        "run_id": "mvr_t", "capture_take_id": "ct", "reference_view_id": "cam_1",
        "samples": [{
            "global_player_id": "global_player_1",
            "take_timestamp_ms": 1000.0,
            "timestamp_seconds": 1.0,
            "reference_frame_index": 30,
            "x_ft": 5.0, "y_ft": 10.0,
            "fusion_status": "dual_observed",
            "metric_eligible": True,
            "observation_origin": "base",
        }],
    }
    joint_output = SimpleNamespace(
        trajectory=fused,
        normalized=__import__("app.vision.multiview.joint_artifact", fromlist=["load_fused_trajectory"]).load_fused_trajectory(fused),
        diagnostics={
            "analysis_window": {"enabled": True, "source_frame_count": 3600, "source_duration_ms": 60000},
            "frame_size": {"width": 1920, "height": 1080},
            "execution_mode": "joint_authoritative",
            "effective_mode": "multiview_fused",
            "authoritative_joint_eligible": True,
            "global_player_count": 1,
            "expected_player_count": 4,
            "roster_state": "BOOTSTRAPPING",
            "roster_occupied_count": 1,
            "confirmed_player_count": 0,
            # global-player-roster.v1 快照（reference view binding 决定 canonical Player_N）
            "roster": [
                {
                    "global_player_id": "global_player_1",
                    "player_id": "Player_1",
                    "label": "P1",
                    "status": "provisional",
                    "lifecycle": "tentative",
                    "cross_view_anchored": False,
                    "bindings": {
                        "cam_1": {"view_player_id": "Player_1", "track_id": 1, "visibility": "observed"},
                        "cam_2": {"view_player_id": "Player_3", "track_id": 11, "visibility": "observed"},
                    },
                }
            ],
        },
        debug_trace=_sample_trace(),
    )
    composer = MultiViewResultComposer(storage)
    result = composer.compose_joint_result(
        job=job, joint_output=joint_output, reference_view_id="cam_1",
        message="ok", refinement=None,
    )
    # tracking overlay（框架）可用
    assert result.artifacts.tracking_overlay_url == "/api/analysis/jobs/job-p/artifacts/tracking-overlay"
    assert result.artifacts.tracking_overlay_status == "available"
    # pose 显式 unavailable + reason
    assert result.artifacts.pose_overlay_status == "unavailable"
    assert result.artifacts.pose_overlay_detail == JOINT_POSE_UNAVAILABLE
    # roster 化公开契约（stabilize-joint-global-player-roster）
    assert result.artifacts.roster_url == "/api/analysis/jobs/job-p/artifacts/roster"
    assert result.artifacts.roster_status == "available"
    assert result.artifacts.structured_visualization_data_path is not None
    assert result.artifacts.four_player_identification_quality_url == "/api/analysis/jobs/job-p/artifacts/four-player-identification-quality"
    # 公开轨迹身份为 canonical Player_N（非 global_player_）
    assert {t.track_id for t in result.tracks} == {"Player_1"}
    assert result.observed_player_count == 1
    roster_json = storage.read_json(storage.roster_manifest_json_path("job-p"))
    assert roster_json["schema_version"] == "global-player-roster.v1"
    assert roster_json["expected_player_count"] == 4
    assert roster_json["status"] == "bootstrap"
    assert roster_json["players"][0]["global_player_id"] == "global_player_1"
    assert roster_json["players"][0]["player_id"] == "Player_1"
    assert roster_json["players"][0]["label"] == "P1"
    assert roster_json["players"][0]["bindings"]["cam_2"]["view_player_id"] == "Player_3"
    # heatmaps URL 已生成（可用与否取决于点数）
    assert result.artifacts.heatmaps_url == "/api/analysis/jobs/job-p/artifacts/position-heatmaps"
    structured = storage.read_json(storage.structured_visualization_data_path("job-p"))
    assert structured["identity_quality"]["players"]["Player_1"]["accepted_count"] == 1
    assert structured["identity_quality"]["players"]["Player_1"]["sufficiency"] == "sufficient"
    # 聚合 stage：A/B 均 done（joint 完成，不再误报 failed）
    stage_ids = {s.id: s.status for s in result.stages}
    assert stage_ids["multiview-view-a"] == "done"
    assert stage_ids["multiview-view-b"] == "done"


# ---- fused player overlay（add-multiview-fused-player-overlay）---------------


def _f0_snapshot_with_observation():
    """构造含 1 tick 的 F0 snapshot：global_player_1 在 cam_1 有 strong base 观测。"""
    from app.vision.multiview.offline_refinement import (
        F0RefinementSnapshot,
        F0TickSnapshot,
        F0TickViewState,
    )

    state = F0TickViewState(
        observed=True,
        quality=0.9,
        canonical_position=(10.0, 20.0),
        origin="base",
        source_frame_index=30,
        source_timestamp_ms=1000.0,
        mapped_take_timestamp_ms=1000.0,
        timing_authority="reference",
        sync_quality="good",
        view_status="available",
        observation_status="observed",
        view_player_id="Player_1",
        detector_confidence=0.9,
        projection_confidence=0.9,
        tracking_status="detected",
        bbox=(100.0, 200.0, 150.0, 300.0),
    )
    tick = F0TickSnapshot(
        canonical_tick=0,
        canonical_timestamp_ms=1000.0,
        reference_frame_index=30,
        observations=(("global_player_1", "cam_1", state),),
        global_positions=(("global_player_1", (10.0, 20.0)),),
    )
    return F0RefinementSnapshot(
        run_id="mvr_t",
        capture_take_id="ct",
        reference_view_id="cam_1",
        view_ids=("cam_1", "cam_2"),
        global_player_ids=("global_player_1",),
        ticks=(tick,),
    )


def _joint_output_with_overlay_context(debug_trace=None):
    """构造带 overlay_context（view geometry + final_source）的 joint output。"""
    from app.vision.multiview.court_frame import CourtOrientation
    from app.vision.multiview.fused_overlay_bundle import ViewGeometry

    fused = {
        "schema_version": "fused_player_trajectory.v2",
        "run_id": "mvr_t", "capture_take_id": "ct", "reference_view_id": "cam_1",
        "samples": [{
            "global_player_id": "global_player_1",
            "take_timestamp_ms": 1000.0,
            "timestamp_seconds": 1.0,
            "reference_frame_index": 30,
            "x_ft": 10.0, "y_ft": 20.0,
            "fusion_status": "dual_observed",
            "metric_eligible": True,
            "observation_origin": "base",
        }],
    }
    identity_h = [[10.0, 0.0, 0.0], [0.0, 10.0, 0.0], [0.0, 0.0, 1.0]]
    overlay_context = {
        "view_geometry": {
            "cam_1": ViewGeometry(
                view_id="cam_1", orientation=CourtOrientation.identity,
                inverse_homography=identity_h, frame_width=640, frame_height=480,
            ),
            "cam_2": ViewGeometry(
                view_id="cam_2", orientation=CourtOrientation.identity,
                inverse_homography=identity_h, frame_width=640, frame_height=480,
            ),
        },
        "recovered_observations": [],
        "final_source": "first_pass_f0",
    }
    return SimpleNamespace(
        trajectory=fused,
        normalized=__import__("app.vision.multiview.joint_artifact", fromlist=["load_fused_trajectory"]).load_fused_trajectory(fused),
        diagnostics={
            "analysis_window": {"enabled": True, "source_frame_count": 3600, "source_duration_ms": 60000},
            "frame_size": {"width": 640, "height": 480},
            "execution_mode": "joint_authoritative",
            "effective_mode": "multiview_fused",
            "authoritative_joint_eligible": True,
            "global_player_count": 1,
            "expected_player_count": 4,
            "roster_state": "ROSTER_ACTIVE",
            "roster_occupied_count": 1,
            "confirmed_player_count": 1,
            "roster": [
                {
                    "global_player_id": "global_player_1",
                    "player_id": "Player_1",
                    "label": "P1",
                    "status": "confirmed",
                    "lifecycle": "confirmed",
                    "cross_view_anchored": False,
                    "bindings": {
                        "cam_1": {"view_player_id": "Player_1", "track_id": 1, "visibility": "observed"},
                        "cam_2": {"view_player_id": "Player_3", "track_id": 11, "visibility": "observed"},
                    },
                }
            ],
        },
        debug_trace=debug_trace,
        f0_snapshot=_f0_snapshot_with_observation(),
        recovery_evidence=[],
        overlay_context=overlay_context,
    )


def test_compose_publishes_fused_player_overlay(tmp_path):
    """joint compose 产出 fused_player_overlay_url + 契约（debug trace 无关）。"""
    from app.schemas.analysis import AnalysisJobSummary
    from app.services.storage_service import StorageService

    storage = StorageService()
    take_dir = tmp_path / "take"
    storage.register_capture_job("job-p2", take_dir)

    job = AnalysisJobSummary(
        id="job-p2",
        status="completed",
        stage="report",
        progress=100,
        createdAt="2026-08-15T00:00:00+00:00",
        updatedAt="2026-08-15T00:00:00+00:00",
        videoId="vid",
        calibrationId="calib",
        analysisKind="multiview",
        executionMode="joint_tracking_v2",
        frameStride=2,
        sourceFps=60.0,
        clipStartMs=0,
        clipEndMs=60000,
        viewRuns={},
        referenceViewId="cam_1",
        jointViewInputs=[],
        metadata={
            "fileName": "joint.mp4", "fileSize": 10, "matchTitle": "Joint",
            "venue": "Court", "matchDate": "2026-08-15",
            "matchFormat": "doubles", "cameraAngle": "elevated",
            "athleteLabel": "P", "level": "MVP",
        },
        stages=[],
    )
    composer = MultiViewResultComposer(storage)
    # debugTraceEnabled=false：debug_trace 为 None
    result = composer.compose_joint_result(
        job=job,
        joint_output=_joint_output_with_overlay_context(debug_trace=None),
        reference_view_id="cam_1",
        message="ok",
        refinement=None,
    )
    # fused overlay 正式产物（不依赖 debug trace）
    assert result.artifacts.fused_player_overlay_url == (
        "/api/analysis/jobs/job-p2/artifacts/fused-player-overlay"
    )
    assert result.artifacts.fused_player_overlay_status == "available"
    assert result.artifacts.fused_player_overlay_json_path is not None
    overlay = storage.read_json(storage.fused_player_overlay_json_path("job-p2"))
    assert overlay["schema_version"] == "multiview-fused-player-overlay.v1"
    assert overlay["reference_view_id"] == "cam_1"
    assert len(overlay["frames"]) == 1
    players = overlay["frames"][0]["players"]
    assert len(players) == 1
    assert players[0]["player_id"] == "Player_1"
    assert players[0]["evidence_type"] == "base_observed"
    assert players[0]["bbox"] == [100.0, 200.0, 150.0, 300.0]
    # manifest 含 fusedPlayerOverlay 入口
    manifest = storage.read_json(storage.fusion_manifest_json_path("job-p2"))
    assert manifest["artifacts"]["fusedPlayerOverlay"]["url"] == result.artifacts.fused_player_overlay_url


def test_fused_overlay_unavailable_without_geometry(tmp_path):
    """缺少 view geometry → fused overlay 显式 unavailable（不中断 compose）。"""
    from app.schemas.analysis import AnalysisJobSummary
    from app.services.storage_service import StorageService

    storage = StorageService()
    take_dir = tmp_path / "take"
    storage.register_capture_job("job-p3", take_dir)

    job = AnalysisJobSummary(
        id="job-p3",
        status="completed",
        stage="report",
        progress=100,
        createdAt="2026-08-15T00:00:00+00:00",
        updatedAt="2026-08-15T00:00:00+00:00",
        videoId="vid",
        calibrationId="calib",
        analysisKind="multiview",
        executionMode="joint_tracking_v2",
        frameStride=2,
        sourceFps=60.0,
        clipStartMs=0,
        clipEndMs=60000,
        viewRuns={},
        referenceViewId="cam_1",
        jointViewInputs=[],
        metadata={
            "fileName": "joint.mp4", "fileSize": 10, "matchTitle": "Joint",
            "venue": "Court", "matchDate": "2026-08-15",
            "matchFormat": "doubles", "cameraAngle": "elevated",
            "athleteLabel": "P", "level": "MVP",
        },
        stages=[],
    )
    joint_output = _joint_output_with_overlay_context(debug_trace=None)
    joint_output.overlay_context = {"view_geometry": {}, "recovered_observations": [], "final_source": "first_pass_f0"}
    composer = MultiViewResultComposer(storage)
    result = composer.compose_joint_result(
        job=job, joint_output=joint_output, reference_view_id="cam_1",
        message="ok", refinement=None,
    )
    assert result.artifacts.fused_player_overlay_status == "unavailable"
    assert result.artifacts.fused_player_overlay_url is None


def test_compose_writes_placeholder_display_diagnostics_when_payload_missing(tmp_path):
    """fix-multiview-player-identity T1.2：joint_output 缺 display_diagnostics_payload
    时 composer 仍写盘占位 artifact（status=unavailable），查询 API 返回结构化 unavailable 而非 404。"""
    from fastapi.testclient import TestClient

    from app.api import routes_analysis
    from app.main import app
    from app.schemas.analysis import AnalysisJobSummary
    from app.services.mock_analysis import JOBS, RESULTS
    from app.services.storage_service import StorageService

    storage = StorageService()
    storage.settings.outputs_dir = tmp_path / "outputs"
    storage.settings.ensure_data_dirs()
    take_dir = tmp_path / "take"
    storage.register_capture_job("job-pdiag", take_dir)

    job = AnalysisJobSummary(
        id="job-pdiag",
        status="completed",
        stage="report",
        progress=100,
        createdAt="2026-08-15T00:00:00+00:00",
        updatedAt="2026-08-15T00:00:00+00:00",
        videoId="vid",
        calibrationId="calib",
        analysisKind="multiview",
        executionMode="joint_tracking_v2",
        frameStride=2,
        sourceFps=60.0,
        clipStartMs=0,
        clipEndMs=60000,
        viewRuns={},
        referenceViewId="cam_1",
        jointViewInputs=[],
        metadata={
            "fileName": "joint.mp4", "fileSize": 10, "matchTitle": "Joint",
            "venue": "Court", "matchDate": "2026-08-15",
            "matchFormat": "doubles", "cameraAngle": "elevated",
            "athleteLabel": "P", "level": "MVP",
        },
        stages=[],
    )
    # joint output 显式不携带 display_diagnostics_payload（模拟构建失败场景）
    joint_output = _joint_output_with_overlay_context(debug_trace=None)
    assert not hasattr(joint_output, "display_diagnostics_payload")
    composer = MultiViewResultComposer(storage)
    result = composer.compose_joint_result(
        job=job, joint_output=joint_output, reference_view_id="cam_1",
        message="ok", refinement=None,
    )
    # 占位 artifact 已写盘且状态为 unavailable
    assert result.artifacts.player_display_diagnostics_status == "unavailable"
    diag_path = storage.player_display_diagnostics_json_path(job.id)
    assert diag_path.exists()
    payload = storage.read_json(diag_path)
    assert payload["schema_version"] == "player-display-diagnostics.v1"
    assert payload["status"] == "unavailable"
    assert payload["rows"] == []

    # 查询 API：产物存在但 status=unavailable → 结构化 unavailable（HTTP 200，非 404）
    monkeypatch_storage = routes_analysis
    original_storage = monkeypatch_storage._STORAGE
    monkeypatch_storage._STORAGE = storage
    snapshot = JOBS.copy(), RESULTS.copy()
    JOBS.clear()
    RESULTS.clear()
    JOBS.update({job.id: job})
    try:
        with TestClient(app) as client:
            resp = client.get(
                f"/api/analysis/jobs/{job.id}/multiview/players/Player_1/display-diagnostics",
                params={"timestamp_ms": 7000},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "unavailable"
            assert body["rows"] == []
    finally:
        monkeypatch_storage._STORAGE = original_storage
        JOBS.clear()
        JOBS.update(snapshot[0])
        RESULTS.clear()
        RESULTS.update(snapshot[1])
