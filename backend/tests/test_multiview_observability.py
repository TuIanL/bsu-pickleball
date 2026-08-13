from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.api import routes_analysis
from app.main import app
from app.schemas.analysis import AnalysisJobSummary
from app.services.mock_analysis import JOBS, RESULTS
from app.services.multiview_observability import MultiviewObservabilityProjector
from app.services.multiview_observability import build_recovery_episode_projection
from app.services.storage_service import StorageService


def make_multiview_job(job_id: str = "job-observe") -> AnalysisJobSummary:
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
            "matchTitle": "Observability test",
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
        jointRunId="run-observe",
        referenceViewId="cam_1",
        debugTraceEnabled=False,
    )


def write_source_artifacts(storage: StorageService, job: AnalysisJobSummary) -> None:
    storage.write_json(storage.fusion_manifest_json_path(job.id), {
        "schema_version": "fused_manifest.v1",
        "run_id": "run-observe",
        "effective_mode": "multiview_fused",
        "refinement": {
            "status": "rejected_by_safety_gate",
            "final_source": "first_pass_f0",
            "refined_artifact": "fused_player_trajectory.f1.v2.json",
            "reason": "conflicts_increased",
        },
    })
    storage.write_json(storage.fusion_diagnostics_json_path(job.id), {
        "schema_version": "fused_diagnostics.v1",
        "timing_authority_by_view": {"cam_1": "source_pts", "cam_2": "source_pts"},
        "sync_quality": "good",
        "execution_mode": "joint_authoritative",
        "authoritative_joint_eligible": True,
        "authority_reason_codes": [],
        "fusion_status_counts": {"dual_observed": 8, "single_view_fallback": 2},
        "sample_count": 10,
        "metric_eligible_count": 8,
        "view_disagreement": {"median_distance_ft": 0.4},
        "recovery_funnel": {
            "recovery_opportunity_count": 2,
            "guidance_generated_count": 2,
            "guided_candidate_count": 2,
            "guided_recovery_success_count": 1,
            "base_recovered_count": 1,
        },
    })
    storage.write_json(storage.recovery_episodes_json_path(job.id, "run-observe"), {
        "schema_version": "recovery_episodes.v1",
        "episodes": [
            {
                "recovery_episode_id": "re_001",
                "start_ms": 1000,
                "end_ms": 1300,
                "global_player_id": "global_1",
                "donor_view": "cam_1",
                "target_view": "cam_2",
                "outcome": "guided_recovery_success",
                "guidance_attempts": 2,
                "pre_gate_rejections": 1,
                "lock_rejections": 0,
                "debug_video_seek_ms": 1100,
            },
            {
                "recovery_episode_id": "re_002",
                "start_ms": 3000,
                "end_ms": 3300,
                "global_player_id": "global_2",
                "donor_view": "cam_2",
                "target_view": "cam_1",
                "outcome": "base_recovered",
                "guidance_attempts": 1,
                "pre_gate_rejections": 0,
                "lock_rejections": 0,
                "debug_video_seek_ms": 3100,
            },
        ],
    })
    storage.write_json(storage.multiview_run_dir(job.id, "run-observe") / "fused_player_trajectory.f1.v2.json", {"schema_version": "fused_player_trajectory.v2", "samples": []})


def test_projector_preserves_authority_and_refinement_decisions(tmp_path):
    storage = StorageService()
    storage.settings.outputs_dir = tmp_path / "outputs"
    storage.settings.ensure_data_dirs()
    job = make_multiview_job()
    write_source_artifacts(storage, job)

    summary = MultiviewObservabilityProjector(storage).project(job)

    assert summary["schema_version"] == "multiview_observability_summary.v1"
    assert summary["sync"]["status"] == "authoritative"
    assert summary["sync"]["data"]["per_view_authority"]["cam_1"] == "source_pts"
    assert summary["fusion"]["data"]["status_counts"]["single_view_fallback"] == 2
    assert summary["refinement"]["data"]["publication_decision"] == "rejected_by_safety_gate"
    assert summary["refinement"]["data"]["execution_status"] == "completed"
    assert summary["refinement"]["data"]["candidate_f1"]["available"] is True
    assert summary["refinement"]["data"]["final_source"] == "first_pass_f0"
    assert summary["debug"]["availability"] == "unavailable"
    assert "joint_debug_trace" not in json.dumps(summary)
    assert "media_path" not in json.dumps(summary)
    assert "sidecar_path" not in json.dumps(summary)


def test_projector_keeps_partial_sections_independent(tmp_path):
    storage = StorageService()
    storage.settings.outputs_dir = tmp_path / "outputs"
    storage.settings.ensure_data_dirs()
    job = make_multiview_job("job-partial")
    storage.write_json(storage.fusion_manifest_json_path(job.id), {"run_id": "run-partial", "effective_mode": "multiview_degraded"})
    storage.write_json(storage.fusion_diagnostics_json_path(job.id), {"execution_mode": "joint_tracking_v2", "fusion_status_counts": {"single_view_fallback": 4}})

    summary = MultiviewObservabilityProjector(storage).project(job)

    assert summary["sync"]["availability"] in {"partial", "unavailable"}
    assert summary["fusion"]["availability"] == "available"
    assert summary["recovery"]["availability"] == "unavailable"
    assert summary["refinement"]["availability"] == "unavailable"


def test_episode_projector_filters_and_paginates(tmp_path):
    storage = StorageService()
    storage.settings.outputs_dir = tmp_path / "outputs"
    storage.settings.ensure_data_dirs()
    job = make_multiview_job("job-episodes")
    write_source_artifacts(storage, job)
    projector = MultiviewObservabilityProjector(storage)

    first = projector.episodes.list_episodes(job=job, run_id="run-observe", limit=1)
    assert len(first["items"]) == 1
    assert first["next_cursor"]
    second = projector.episodes.list_episodes(job=job, run_id="run-observe", limit=1, cursor=first["next_cursor"], target_view="cam_1")
    assert second["items"] == []
    filtered = projector.episodes.list_episodes(job=job, run_id="run-observe", outcome="guided_recovery_success", target_view="cam_2")
    assert [item["recovery_episode_id"] for item in filtered["items"]] == ["re_001"]


def test_api_returns_structured_not_applicable_and_range_video(monkeypatch, tmp_path):
    storage = StorageService()
    storage.settings.outputs_dir = tmp_path / "outputs"
    storage.settings.ensure_data_dirs()
    job = make_multiview_job("job-route")
    single = job.model_copy(update={"id": "job-single", "analysisKind": "single_view"})
    write_source_artifacts(storage, job)
    video_path = storage.canonical_debug_video_path(job.id, "run-observe")
    video_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"0123456789")
    debug_job = job.model_copy(update={"debugTraceEnabled": True})

    monkeypatch.setattr(routes_analysis, "_STORAGE", storage)
    monkeypatch.setattr(routes_analysis, "_MULTIVIEW_OBSERVABILITY", MultiviewObservabilityProjector(storage))
    snapshot = JOBS.copy(), RESULTS.copy()
    JOBS.clear()
    RESULTS.clear()
    JOBS.update({job.id: debug_job, single.id: single})
    try:
        with TestClient(app) as client:
            not_applicable = client.get(f"/api/analysis/jobs/{single.id}/multiview/observability")
            assert not_applicable.status_code == 404
            assert not_applicable.json()["error"]["code"] == "not_applicable"
            raw_trace = client.get(f"/api/analysis/jobs/{job.id}/artifacts/joint_debug_trace.v1.json")
            assert raw_trace.status_code == 422
            response = client.get(f"/api/analysis/jobs/{job.id}/multiview/debug-video", headers={"Range": "bytes=2-5"})
            assert response.status_code == 206
            assert response.content == b"2345"
            assert "joint_debug_trace.v1.json" not in str(response.request.url)
    finally:
        JOBS.clear()
        JOBS.update(snapshot[0])
        RESULTS.clear()
        RESULTS.update(snapshot[1])


def test_projector_distinguishes_failed_fallback_and_published_f1(tmp_path):
    storage = StorageService()
    storage.settings.outputs_dir = tmp_path / "outputs"
    storage.settings.ensure_data_dirs()
    job = make_multiview_job("job-refinement")
    write_source_artifacts(storage, job)
    manifest_path = storage.fusion_manifest_json_path(job.id)

    storage.write_json(manifest_path, {"run_id": "run-observe", "execution_mode": "joint_authoritative", "refinement": {"status": "failed_fallback", "final_source": "first_pass_f0", "reason": "renderer_error"}})
    failed = MultiviewObservabilityProjector(storage).project(job)
    assert failed["refinement"]["data"]["execution_status"] == "failed_fallback"
    assert failed["refinement"]["data"]["publication_decision"] == "failed_fallback"
    assert failed["refinement"]["data"]["final_source"] == "first_pass_f0"

    storage.write_json(manifest_path, {"run_id": "run-observe", "execution_mode": "joint_authoritative", "refinement": {"status": "completed", "final_source": "refined_f1", "refined_artifact": "fused_player_trajectory.f1.v2.json"}})
    published = MultiviewObservabilityProjector(storage).project(job)
    assert published["refinement"]["data"]["execution_status"] == "completed"
    assert published["refinement"]["data"]["publication_decision"] == "passed"
    assert published["refinement"]["data"]["final_source"] == "refined_f1"


def test_episode_projection_preserves_global_mismatch_outcome():
    projection = build_recovery_episode_projection({
        "run_id": "run-mismatch",
        "capture_take_id": "take-mismatch",
        "ticks": [
            {
                "canonical_timestamp_ms": 1000,
                "recovery": {},
                "views": {
                    "cam_2": {
                        "guidance": [{
                            "recovery_episode_id": "re-mismatch",
                            "global_player_id": "global_1",
                            "donor_view": "cam_1",
                            "target_view": "cam_2",
                        }],
                    },
                },
                "canonical_observations": [{
                    "global_player_id": "global_2",
                    "view_id": "cam_2",
                    "detection_origin": "guided_roi",
                    "expected_global_player_id": "global_1",
                }],
            },
        ],
    })

    assert projection["episodes"][0]["outcome"] == "global_mismatch"
