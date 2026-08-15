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
    # 聚合 stage：A/B 均 done（joint 完成，不再误报 failed）
    stage_ids = {s.id: s.status for s in result.stages}
    assert stage_ids["multiview-view-a"] == "done"
    assert stage_ids["multiview-view-b"] == "done"
