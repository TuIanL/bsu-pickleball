from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app
from app.schemas.analysis import AnalysisJobCreate
from app.schemas.analysis import AnalysisJobSummary as AnalysisJobSummarySchema
from app.schemas.pipeline import AnalysisArtifacts, PipelineStageResult
from app.schemas.pose import PoseKeypoint, PoseOverlayFrame, PoseSubject
from app.schemas.tracking import Detection
from app.services.analysis_pipeline import AnalysisPipeline
from app.services.mock_analysis import (
    JOBS,
    REPORTS,
    RESULTS,
    build_stages,
    cancel_analysis_job,
    create_analysis_job,
    delete_analysis_job,
    get_mock_job,
    list_analysis_jobs,
    run_analysis_job,
)
from app.services.storage_service import StorageService
from app.services.video_service import VIDEOS
from app.vision.player_tracking_engine.person_detector import EmptyPersonDetector
from app.vision.pose.rtmpose26_adapter import RTMPose26Adapter


client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_metadata_only_analysis_job_still_completes():
    payload = {
        "metadata": {
            "fileName": "demo.mp4",
            "fileSize": 1234,
            "matchTitle": "MVP Test Match",
            "venue": "Test Court",
            "matchDate": "2026-05-07",
            "matchFormat": "doubles",
            "cameraAngle": "elevated",
            "athleteLabel": "Player A",
            "level": "MVP",
        }
    }

    response = client.post("/api/analysis/jobs", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["metadata"]["matchTitle"] == "MVP Test Match"


def test_analysis_job_list_returns_empty_for_no_jobs(tmp_path):
    storage = make_temp_storage(tmp_path)
    snapshot = JOBS.copy()
    JOBS.clear()

    try:
        assert list_analysis_jobs(storage) == []
    finally:
        JOBS.clear()
        JOBS.update(snapshot)


def test_analysis_job_list_merges_persisted_active_and_skips_malformed(tmp_path):
    storage = make_temp_storage(tmp_path)
    snapshot = JOBS.copy()
    JOBS.clear()

    persisted = make_job_summary(
        "job-persisted-list",
        status="completed",
        match_title="Persisted Match",
        created_at="2026-05-19T10:00:00+00:00",
        updated_at="2026-05-19T10:10:00+00:00",
    )
    active = make_job_summary(
        "job-active-list",
        status="processing",
        match_title="Active Match",
        progress=44,
        created_at="2026-05-20T10:00:00+00:00",
        updated_at="2026-05-20T10:02:00+00:00",
    )
    storage.write_json(storage.job_json_path(persisted.id), persisted.model_dump(mode="json"))
    storage.job_json_path("job-broken-list").write_text("{not-json", encoding="utf-8")
    JOBS[active.id] = active

    try:
        jobs = list_analysis_jobs(storage)
    finally:
        JOBS.clear()
        JOBS.update(snapshot)

    assert [job.id for job in jobs] == ["job-active-list", "job-persisted-list"]
    assert jobs[0].status == "processing"
    assert jobs[0].progress == 44
    assert jobs[1].metadata.matchTitle == "Persisted Match"


def test_analysis_jobs_endpoint_lists_created_jobs():
    payload = {
        "metadata": {
            "fileName": "list-route.mp4",
            "fileSize": 4321,
            "matchTitle": "List Route Match",
            "venue": "Task Court",
            "matchDate": "2026-05-20",
            "matchFormat": "doubles",
            "cameraAngle": "elevated",
            "athleteLabel": "Route Player",
            "level": "MVP",
        }
    }
    create_response = client.post("/api/analysis/jobs", json=payload)
    assert create_response.status_code == 200
    job_id = create_response.json()["id"]

    list_response = client.get("/api/analysis/jobs")

    assert list_response.status_code == 200
    jobs = list_response.json()
    listed = next(job for job in jobs if job["id"] == job_id)
    assert listed["metadata"]["matchTitle"] == "List Route Match"
    assert listed["status"] == "completed"


def test_delete_completed_analysis_job_removes_persisted_artifacts(monkeypatch, tmp_path):
    storage = make_temp_storage(tmp_path)
    monkeypatch.setattr("app.services.mock_analysis._STORAGE", storage)
    snapshot = snapshot_analysis_state()
    JOBS.clear()
    REPORTS.clear()
    RESULTS.clear()

    job = make_job_summary("job-delete-completed", status="completed")
    JOBS[job.id] = job
    storage.write_json(storage.job_json_path(job.id), job.model_dump(mode="json"))
    storage.write_json(storage.report_json_path(job.id), {"jobId": job.id})
    storage.write_json(storage.output_json_path(job.id), {"job_id": job.id})
    storage.write_json(storage.tracking_overlay_json_path(job.id), {"job_id": job.id})

    try:
        result = delete_analysis_job(job.id)
    finally:
        restore_analysis_state(snapshot)

    assert result.status == "deleted"
    assert not storage.job_json_path(job.id).exists()
    assert not storage.report_json_path(job.id).exists()
    assert not storage.output_json_path(job.id).exists()
    assert not (storage.outputs_dir / job.id).exists()


def test_delete_active_analysis_job_is_blocked(monkeypatch, tmp_path):
    storage = make_temp_storage(tmp_path)
    monkeypatch.setattr("app.services.mock_analysis._STORAGE", storage)
    snapshot = snapshot_analysis_state()
    JOBS.clear()
    REPORTS.clear()
    RESULTS.clear()

    job = make_job_summary("job-delete-active", status="processing", progress=42)
    JOBS[job.id] = job
    storage.write_json(storage.job_json_path(job.id), job.model_dump(mode="json"))

    try:
        result = delete_analysis_job(job.id)
    finally:
        restore_analysis_state(snapshot)

    assert result.status == "blocked"
    assert storage.job_json_path(job.id).exists()


def test_batch_delete_endpoint_returns_partial_results(monkeypatch, tmp_path):
    storage = make_temp_storage(tmp_path)
    monkeypatch.setattr("app.services.mock_analysis._STORAGE", storage)
    snapshot = snapshot_analysis_state()
    JOBS.clear()
    REPORTS.clear()
    RESULTS.clear()

    completed = make_job_summary("job-batch-completed", status="completed")
    active = make_job_summary("job-batch-active", status="queued", progress=12)
    for job in [completed, active]:
        JOBS[job.id] = job
        storage.write_json(storage.job_json_path(job.id), job.model_dump(mode="json"))

    try:
        response = client.post(
            "/api/analysis/jobs/delete",
            json={"job_ids": [completed.id, active.id, "job-batch-missing"]},
        )
    finally:
        restore_analysis_state(snapshot)

    assert response.status_code == 200
    results = {item["job_id"]: item["status"] for item in response.json()}
    assert results == {
        completed.id: "deleted",
        active.id: "blocked",
        "job-batch-missing": "not_found",
    }
    assert not storage.job_json_path(completed.id).exists()
    assert storage.job_json_path(active.id).exists()


def test_player_trajectory_artifact_route_returns_json(monkeypatch, tmp_path):
    storage = make_temp_storage(tmp_path)
    monkeypatch.setattr("app.api.routes_analysis._STORAGE", storage)
    snapshot = snapshot_analysis_state()
    JOBS.clear()
    REPORTS.clear()
    RESULTS.clear()

    job = make_job_summary("job-player-trajectory-route", status="completed")
    JOBS[job.id] = job
    storage.write_json(storage.player_trajectory_json_path(job.id), {"job_id": job.id, "court": {"court_unit": "m"}})

    try:
        response = client.get(f"/api/analysis/jobs/{job.id}/artifacts/player-trajectories")
    finally:
        restore_analysis_state(snapshot)

    assert response.status_code == 200
    assert response.json()["court"]["court_unit"] == "m"


def test_serve_events_artifact_route_returns_json(monkeypatch, tmp_path):
    storage = make_temp_storage(tmp_path)
    monkeypatch.setattr("app.api.routes_analysis._STORAGE", storage)
    snapshot = snapshot_analysis_state()
    JOBS.clear()
    REPORTS.clear()
    RESULTS.clear()

    job = make_job_summary("job-serve-events-route", status="completed")
    JOBS[job.id] = job
    storage.write_json(storage.serve_events_json_path(job.id), {"job_id": job.id, "status": "no_candidates", "detail": "none", "events": []})

    try:
        response = client.get(f"/api/analysis/jobs/{job.id}/artifacts/serve-events")
    finally:
        restore_analysis_state(snapshot)

    assert response.status_code == 200
    assert response.json()["status"] == "no_candidates"


def test_storage_service_resolves_extended_analysis_artifact_paths(tmp_path):
    storage = make_temp_storage(tmp_path)
    job_id = "job-extended-artifacts"

    assert storage.ball_overlay_json_path(job_id) == storage.outputs_dir / job_id / "ball_overlay.json"
    assert storage.detections_jsonl_path(job_id) == storage.outputs_dir / job_id / "detections.jsonl"
    assert storage.ball_trajectory_json_path(job_id) == storage.outputs_dir / job_id / "ball_trajectory.json"
    assert storage.cleaned_ball_trajectory_json_path(job_id) == storage.outputs_dir / job_id / "cleaned_ball_trajectory.json"
    assert storage.bounce_events_json_path(job_id) == storage.outputs_dir / job_id / "bounce_events.json"
    assert storage.analysis_overlay_video_path(job_id) == storage.outputs_dir / job_id / "analysis_overlay.mp4"
    assert storage.heatmaps_manifest_json_path(job_id) == (
        storage.outputs_dir / job_id / "position_visualizations" / "heatmaps" / "manifest.json"
    )
    assert storage.scatter_plots_manifest_json_path(job_id) == (
        storage.outputs_dir / job_id / "position_visualizations" / "scatter_plots" / "manifest.json"
    )


def test_analysis_artifacts_extended_fields_are_optional_and_serializable():
    legacy = AnalysisArtifacts(result_json_path="/tmp/result.json")

    assert legacy.ball_overlay_json_path is None
    assert legacy.detections_jsonl_path is None
    assert legacy.analysis_overlay_video_url is None

    artifact = AnalysisArtifacts(
        detections_jsonl_path="/tmp/detections.jsonl",
        detections_url="/api/analysis/jobs/job-1/artifacts/detections",
        detections_status="available",
        detections_detail="generated",
        ball_overlay_json_path="/tmp/ball_overlay.json",
        ball_overlay_url="/api/analysis/jobs/job-1/artifacts/ball-overlay",
        ball_overlay_status="available",
        ball_overlay_detail="generated",
        ball_trajectory_json_path="/tmp/ball_trajectory.json",
        ball_trajectory_url="/api/analysis/jobs/job-1/artifacts/ball-trajectory",
        cleaned_ball_trajectory_json_path="/tmp/cleaned_ball_trajectory.json",
        cleaned_ball_trajectory_url="/api/analysis/jobs/job-1/artifacts/cleaned-ball-trajectory",
        bounce_events_json_path="/tmp/bounce_events.json",
        bounce_events_url="/api/analysis/jobs/job-1/artifacts/bounce-events",
        analysis_overlay_video_path="/tmp/analysis_overlay.mp4",
        analysis_overlay_video_url="/api/analysis/jobs/job-1/artifacts/analysis-overlay-video",
        heatmaps_manifest_json_path="/tmp/heatmaps/manifest.json",
        heatmaps_url="/api/analysis/jobs/job-1/artifacts/position-heatmaps",
        scatter_plots_manifest_json_path="/tmp/scatter_plots/manifest.json",
        scatter_plots_url="/api/analysis/jobs/job-1/artifacts/position-scatter-plots",
        position_visualizations_status="available",
        position_visualizations_detail="generated",
    )

    dumped = artifact.model_dump(mode="json")

    assert dumped["detections_url"].endswith("/detections")
    assert dumped["ball_overlay_status"] == "available"
    assert dumped["position_visualizations_detail"] == "generated"


def test_pipeline_stage_result_accepts_unavailable_status():
    stage = PipelineStageResult(id="ball-detection", label="球检测", status="unavailable", detail="缺少球模型")

    assert stage.status == "unavailable"


def test_extended_json_artifact_routes_return_json(monkeypatch, tmp_path):
    storage = make_temp_storage(tmp_path)
    monkeypatch.setattr("app.api.routes_analysis._STORAGE", storage)
    snapshot = snapshot_analysis_state()
    JOBS.clear()
    REPORTS.clear()
    RESULTS.clear()

    job = make_job_summary("job-extended-json-route", status="completed")
    JOBS[job.id] = job
    storage.write_json(storage.ball_overlay_json_path(job.id), {"job_id": job.id, "schema_version": "1.0"})
    storage.write_json(storage.ball_trajectory_json_path(job.id), {"job_id": job.id, "samples": []})
    storage.write_json(storage.cleaned_ball_trajectory_json_path(job.id), {"job_id": job.id, "samples": []})
    storage.write_json(storage.bounce_events_json_path(job.id), {"job_id": job.id, "events": []})
    storage.write_json(storage.heatmaps_manifest_json_path(job.id), {"job_id": job.id, "items": []})
    storage.write_json(storage.scatter_plots_manifest_json_path(job.id), {"job_id": job.id, "items": []})

    try:
        responses = {
            name: client.get(f"/api/analysis/jobs/{job.id}/artifacts/{name}")
            for name in [
                "ball-overlay",
                "ball-trajectory",
                "cleaned-ball-trajectory",
                "bounce-events",
                "position-heatmaps",
                "position-scatter-plots",
            ]
        }
    finally:
        restore_analysis_state(snapshot)

    assert all(response.status_code == 200 for response in responses.values())
    assert responses["ball-overlay"].json()["schema_version"] == "1.0"
    assert responses["position-scatter-plots"].json()["items"] == []


def test_known_extended_artifact_route_returns_404_when_missing(monkeypatch, tmp_path):
    storage = make_temp_storage(tmp_path)
    monkeypatch.setattr("app.api.routes_analysis._STORAGE", storage)
    snapshot = snapshot_analysis_state()
    JOBS.clear()
    REPORTS.clear()
    RESULTS.clear()

    job = make_job_summary("job-missing-ball-overlay", status="completed")
    JOBS[job.id] = job

    try:
        response = client.get(f"/api/analysis/jobs/{job.id}/artifacts/ball-overlay")
    finally:
        restore_analysis_state(snapshot)

    assert response.status_code == 404


def test_detections_jsonl_artifact_route_preserves_record_boundaries(monkeypatch, tmp_path):
    storage = make_temp_storage(tmp_path)
    monkeypatch.setattr("app.api.routes_analysis._STORAGE", storage)
    snapshot = snapshot_analysis_state()
    JOBS.clear()
    REPORTS.clear()
    RESULTS.clear()

    job = make_job_summary("job-detections-jsonl-route", status="completed")
    JOBS[job.id] = job
    path = storage.detections_jsonl_path(job.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '{"schema_version":"1.0","job_id":"job-detections-jsonl-route","frame_index":0}\n'
        '{"schema_version":"1.0","job_id":"job-detections-jsonl-route","frame_index":1}\n',
        encoding="utf-8",
    )

    try:
        response = client.get(f"/api/analysis/jobs/{job.id}/artifacts/detections")
    finally:
        restore_analysis_state(snapshot)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert response.text.count("\n") == 2
    assert '"frame_index":0' in response.text
    assert '"frame_index":1' in response.text


def test_analysis_overlay_video_artifact_route_returns_mp4(monkeypatch, tmp_path):
    storage = make_temp_storage(tmp_path)
    monkeypatch.setattr("app.api.routes_analysis._STORAGE", storage)
    snapshot = snapshot_analysis_state()
    JOBS.clear()
    REPORTS.clear()
    RESULTS.clear()

    job = make_job_summary("job-analysis-overlay-video-route", status="completed")
    JOBS[job.id] = job
    path = storage.analysis_overlay_video_path(job.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"fake mp4")

    try:
        response = client.get(f"/api/analysis/jobs/{job.id}/artifacts/analysis-overlay-video")
    finally:
        restore_analysis_state(snapshot)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("video/mp4")
    assert response.content == b"fake mp4"


def test_serve_debug_artifact_routes_return_json(monkeypatch, tmp_path):
    storage = make_temp_storage(tmp_path)
    monkeypatch.setattr("app.api.routes_analysis._STORAGE", storage)
    snapshot = snapshot_analysis_state()
    JOBS.clear()
    REPORTS.clear()
    RESULTS.clear()

    job = make_job_summary("job-serve-debug-route", status="completed")
    JOBS[job.id] = job
    storage.write_json(storage.serve_debug_candidates_json_path(job.id), {"job_id": job.id, "candidates": []})
    storage.write_json(storage.serve_score_series_json_path(job.id), {"job_id": job.id, "series": []})
    storage.write_json(storage.serve_clips_manifest_json_path(job.id), {"job_id": job.id, "clips": []})

    try:
        candidates = client.get(f"/api/analysis/jobs/{job.id}/artifacts/serve-debug-candidates")
        scores = client.get(f"/api/analysis/jobs/{job.id}/artifacts/serve-score-series")
        clips = client.get(f"/api/analysis/jobs/{job.id}/artifacts/serve-clips-manifest")
    finally:
        restore_analysis_state(snapshot)

    assert candidates.status_code == 200
    assert scores.status_code == 200
    assert clips.status_code == 200


def test_court_view_roi_artifact_route_returns_json(monkeypatch, tmp_path):
    storage = make_temp_storage(tmp_path)
    monkeypatch.setattr("app.api.routes_analysis._STORAGE", storage)
    snapshot = snapshot_analysis_state()
    JOBS.clear()
    REPORTS.clear()
    RESULTS.clear()

    job = make_job_summary("job-court-view-roi-route", status="completed")
    JOBS[job.id] = job
    storage.write_json(
        storage.court_view_roi_json_path(job.id),
        {"job_id": job.id, "status": "available", "detail": "court-view candidates are not rallies"},
    )

    try:
        response = client.get(f"/api/analysis/jobs/{job.id}/artifacts/court-view-roi")
    finally:
        restore_analysis_state(snapshot)

    assert response.status_code == 200
    assert response.json()["status"] == "available"


def test_player_selection_artifact_routes_return_json(monkeypatch, tmp_path):
    storage = make_temp_storage(tmp_path)
    monkeypatch.setattr("app.api.routes_analysis._STORAGE", storage)
    snapshot = snapshot_analysis_state()
    JOBS.clear()
    REPORTS.clear()
    RESULTS.clear()

    job = make_job_summary("job-player-selection-route", status="completed")
    JOBS[job.id] = job
    storage.write_json(storage.player_selection_json_path(job.id), {"job_id": job.id, "selection_mode": "rule"})
    storage.write_json(storage.player_selection_training_samples_json_path(job.id), {"job_id": job.id, "samples": []})

    try:
        selection = client.get(f"/api/analysis/jobs/{job.id}/artifacts/player-selection")
        samples = client.get(f"/api/analysis/jobs/{job.id}/artifacts/player-selection-training-samples")
    finally:
        restore_analysis_state(snapshot)

    assert selection.status_code == 200
    assert selection.json()["selection_mode"] == "rule"
    assert samples.status_code == 200
    assert samples.json()["samples"] == []


def test_delete_job_cleans_unreferenced_video_and_preserves_shared_calibration(monkeypatch, tmp_path):
    storage = make_temp_storage(tmp_path)
    monkeypatch.setattr("app.services.mock_analysis._STORAGE", storage)
    snapshot = snapshot_analysis_state()
    JOBS.clear()
    REPORTS.clear()
    RESULTS.clear()

    video_path = storage.uploads_dir / "video-delete-source.mp4"
    video_path.write_bytes(b"video")
    storage.write_json(
        storage.video_metadata_path("video-delete-source"),
        {
            "id": "video-delete-source",
            "original_filename": "source.mp4",
            "content_type": "video/mp4",
            "size_bytes": 5,
            "path": str(video_path),
            "uploaded_at": "2026-05-20T00:00:00Z",
        },
    )
    storage.write_json(storage.calibration_json_path("calib-shared"), {"id": "calib-shared"})
    storage.preview_image_path("calib-shared").write_bytes(b"preview")

    deleted = make_job_summary("job-delete-video", status="completed")
    deleted.videoId = "video-delete-source"
    deleted.calibrationId = "calib-shared"
    shared = make_job_summary("job-keep-calib", status="completed")
    shared.calibrationId = "calib-shared"
    for job in [deleted, shared]:
        JOBS[job.id] = job
        storage.write_json(storage.job_json_path(job.id), job.model_dump(mode="json"))

    try:
        result = delete_analysis_job(deleted.id)
    finally:
        restore_analysis_state(snapshot)

    assert result.status == "deleted"
    assert not video_path.exists()
    assert not storage.video_metadata_path("video-delete-source").exists()
    assert storage.calibration_json_path("calib-shared").exists()
    assert storage.preview_image_path("calib-shared").exists()


def test_manual_calibration_endpoint_creates_and_reads_result():
    payload = {
        "video_id": "video-api-test",
        "image_points": {
            "top_left": [0, 0],
            "top_right": [100, 0],
            "bottom_right": [100, 200],
            "bottom_left": [0, 200],
        },
    }

    create_response = client.post("/calibration/manual", json=payload)

    assert create_response.status_code == 200
    created = create_response.json()
    assert created["calibration_id"].startswith("calib-")
    assert created["court_coordinate_system"] == {"unit": "feet", "width": 20.0, "length": 44.0}
    assert created["quality"]["status"] == "ok"
    assert len(created["homography"]) == 3
    assert len(created["inverse_homography"]) == 3

    read_response = client.get(f"/calibration/{created['calibration_id']}")

    assert read_response.status_code == 200
    read_body = read_response.json()
    assert read_body["calibration_id"] == created["calibration_id"]
    assert read_body["video_id"] == "video-api-test"
    assert len(read_body["keypoints"]) == 4


def test_manual_calibration_endpoint_rejects_bad_geometry():
    payload = {
        "image_points": {
            "top_left": [0, 0],
            "top_right": [1, 1],
            "bottom_right": [2, 2],
            "bottom_left": [3, 3],
        },
    }

    response = client.post("/calibration/manual", json=payload)

    assert response.status_code == 400


def test_automatic_calibration_endpoint_degrades_when_model_is_unavailable():
    upload_response = client.post(
        "/api/videos/upload",
        files={"file": ("auto-unavailable.mp4", b"not-a-real-video", "video/mp4")},
    )
    assert upload_response.status_code == 200
    video_id = upload_response.json()["video"]["id"]

    response = client.post("/calibration/automatic", json={"video_id": video_id})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["mask"]["model_configured"] is False


def test_automatic_calibration_accept_endpoint_stores_semi_automatic_result():
    payload = {
        "video_id": "video-api-auto-test",
        "source": "corrected",
        "image_points": {
            "top_left": [0, 0],
            "top_right": [100, 0],
            "bottom_right": [100, 200],
            "bottom_left": [0, 200],
        },
    }

    response = client.post("/calibration/automatic/accept", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "accepted"
    assert body["calibration_id"].startswith("calib-")

    read_response = client.get(f"/api/calibrations/{body['calibration_id']}")
    assert read_response.status_code == 200
    assert read_response.json()["method"] == "semi-automatic"


def test_video_upload_persists_metadata_after_cache_miss():
    response = client.post(
        "/api/videos/upload",
        files={"file": ("smoke.mp4", b"not-a-real-video", "video/mp4")},
    )

    assert response.status_code == 200
    video = response.json()["video"]
    assert video["id"].startswith("video-")
    assert video["original_filename"] == "smoke.mp4"

    VIDEOS.pop(video["id"], None)

    read_response = client.get(f"/api/videos/{video['id']}")

    assert read_response.status_code == 200
    assert read_response.json()["id"] == video["id"]

    stream_response = client.get(f"/api/videos/{video['id']}/stream")

    assert stream_response.status_code == 200
    assert stream_response.content == b"not-a-real-video"


def test_pipeline_backed_job_lifecycle_and_raw_result():
    upload_response = client.post(
        "/api/videos/upload",
        files={"file": ("limited.mp4", b"not-a-real-video", "video/mp4")},
    )
    video_id = upload_response.json()["video"]["id"]
    deferred = DeferredTasks()
    payload = AnalysisJobCreate(
        videoId=video_id,
        metadata={
            "fileName": "limited.mp4",
            "fileSize": 16,
            "matchTitle": "Lifecycle Test",
            "venue": "Test Court",
            "matchDate": "2026-05-07",
            "matchFormat": "doubles",
            "cameraAngle": "elevated",
            "athleteLabel": "Player A",
            "level": "MVP",
        },
        frameStride=5,
    )

    job = create_analysis_job(payload, background_tasks=deferred)

    assert job.status == "queued"
    not_ready = client.get(f"/api/analysis/jobs/{job.id}/result")
    assert not_ready.status_code == 200
    assert not_ready.json()["status"] == "queued"

    deferred.run_all()

    completed = client.get(f"/api/analysis/jobs/{job.id}")
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert completed.json()["analysisMode"] == "limited"

    result = client.get(f"/api/analysis/jobs/{job.id}/result")
    assert result.status_code == 200
    result_body = result.json()
    assert result_body["job_id"] == job.id
    assert result_body["status"] == "completed"
    assert result_body["video_id"] == video_id
    assert any(stage["id"] == "projection" for stage in result_body["stages"])

    JOBS.pop(job.id, None)
    REPORTS.pop(job.id, None)
    RESULTS.pop(job.id, None)

    assert client.get(f"/api/analysis/jobs/{job.id}").json()["id"] == job.id
    assert client.get(f"/api/analysis/jobs/{job.id}/report").json()["jobId"] == job.id
    assert client.get(f"/api/analysis/jobs/{job.id}/result").json()["job_id"] == job.id


def test_duplicate_pipeline_submission_reuses_active_job():
    upload_response = client.post(
        "/api/videos/upload",
        files={"file": ("duplicate.mp4", b"not-a-real-video", "video/mp4")},
    )
    video_id = upload_response.json()["video"]["id"]
    payload = AnalysisJobCreate(
        videoId=video_id,
        metadata={
            "fileName": "duplicate.mp4",
            "fileSize": 16,
            "matchTitle": "Duplicate Test",
            "venue": "Test Court",
            "matchDate": "2026-05-07",
            "matchFormat": "doubles",
            "cameraAngle": "elevated",
            "athleteLabel": "Player A",
            "level": "MVP",
        },
        frameStride=5,
    )

    first = create_analysis_job(payload, background_tasks=DeferredTasks())
    second = create_analysis_job(payload, background_tasks=DeferredTasks())
    rerun_payload = payload.model_copy(update={"requestNewVersion": True})
    rerun = create_analysis_job(rerun_payload, background_tasks=DeferredTasks())

    assert second.id == first.id
    assert rerun.id != first.id
    assert first.inputSignature == second.inputSignature
    assert first.configSignature == second.configSignature


def test_cancel_queued_job_marks_terminal_state():
    upload_response = client.post(
        "/api/videos/upload",
        files={"file": ("cancel.mp4", b"not-a-real-video", "video/mp4")},
    )
    video_id = upload_response.json()["video"]["id"]
    payload = AnalysisJobCreate(
        videoId=video_id,
        metadata={
            "fileName": "cancel.mp4",
            "fileSize": 16,
            "matchTitle": "Cancel Test",
            "venue": "Test Court",
            "matchDate": "2026-05-07",
            "matchFormat": "doubles",
            "cameraAngle": "elevated",
            "athleteLabel": "Player A",
            "level": "MVP",
        },
        frameStride=5,
    )
    job = create_analysis_job(payload, background_tasks=DeferredTasks())

    canceled = cancel_analysis_job(job.id)
    route_response = client.post(f"/api/analysis/jobs/{job.id}/cancel")

    assert canceled is not None
    assert canceled.status == "canceled"
    assert canceled.canonicalStatus == "canceled"
    assert canceled.cancelRequestedAt is not None
    assert route_response.status_code == 200
    assert route_response.json()["status"] == "canceled"


def test_pipeline_job_persists_intermediate_stage_progress():
    upload_response = client.post(
        "/api/videos/upload",
        files={"file": ("limited-progress.mp4", b"not-a-real-video", "video/mp4")},
    )
    video_id = upload_response.json()["video"]["id"]
    deferred = DeferredTasks()
    payload = AnalysisJobCreate(
        videoId=video_id,
        metadata={
            "fileName": "limited-progress.mp4",
            "fileSize": 16,
            "matchTitle": "Progress Test",
            "venue": "Test Court",
            "matchDate": "2026-05-07",
            "matchFormat": "doubles",
            "cameraAngle": "elevated",
            "athleteLabel": "Player A",
            "level": "MVP",
        },
        frameStride=5,
    )

    job = create_analysis_job(payload, background_tasks=deferred)
    deferred.run_all()
    completed = get_mock_job(job.id)

    assert completed is not None
    assert completed.status == "completed"
    assert completed.progress == 100
    stage_ids = [stage.id for stage in completed.stages]
    assert "frame-sampling" in stage_ids
    assert len(stage_ids) == len(set(stage_ids))
    assert all(stage.status != "active" for stage in completed.stages)
    assert completed.canonicalStatus == "succeeded"
    assert completed.inputSignature
    assert completed.configSignature
    assert any(stage.endedAt for stage in completed.stages if stage.status in {"done", "skipped"})


def test_pipeline_job_records_failed_stage(monkeypatch):
    upload_response = client.post(
        "/api/videos/upload",
        files={"file": ("failed-progress.mp4", b"not-a-real-video", "video/mp4")},
    )
    video_id = upload_response.json()["video"]["id"]
    payload = AnalysisJobCreate(
        videoId=video_id,
        metadata={
            "fileName": "failed-progress.mp4",
            "fileSize": 16,
            "matchTitle": "Failed Progress Test",
            "venue": "Test Court",
            "matchDate": "2026-05-07",
            "matchFormat": "doubles",
            "cameraAngle": "elevated",
            "athleteLabel": "Player A",
            "level": "MVP",
        },
        frameStride=5,
    )
    job = create_analysis_job(payload, background_tasks=DeferredTasks())

    class FailingPipeline:
        def __init__(self, *args, **kwargs):
            pass

        def run(self, job_id, video_id, calibration_id=None, frame_stride=None, progress_callback=None):
            from app.schemas.pipeline import AnalysisArtifacts, AnalysisPipelineResult, PipelineStageResult
            from datetime import datetime, timezone

            failed_stage = PipelineStageResult(
                id="video-read",
                label="读取视频",
                status="failed",
                detail="Could not read uploaded video",
            )
            if progress_callback:
                progress_callback(failed_stage)
            return AnalysisPipelineResult(
                job_id=job_id,
                video_id=video_id,
                calibration_id=calibration_id,
                status="failed",
                generated_at=datetime.now(timezone.utc),
                stages=[failed_stage],
                tracks=[],
                metrics=AnalysisPipeline(detector=EmptyPersonDetector())._compute_metrics([]),
                artifacts=AnalysisArtifacts(),
                message="Could not read uploaded video",
            )

    monkeypatch.setattr("app.services.mock_analysis.AnalysisPipeline", FailingPipeline)
    run_analysis_job(job.id, payload, "PV-FAILED")
    failed = get_mock_job(job.id)

    assert failed is not None
    assert failed.status == "failed"
    assert failed.stage == "video-read"
    assert failed.errorMessage == "Could not read uploaded video"
    assert any(stage.id == "video-read" and stage.status == "failed" for stage in failed.stages)


def test_pipeline_generates_tracking_and_pose_overlay_artifacts(tmp_path):
    video_bytes = make_test_video_bytes(tmp_path)
    upload_response = client.post(
        "/api/videos/upload",
        files={"file": ("overlay.avi", video_bytes, "video/avi")},
    )
    assert upload_response.status_code == 200
    video_id = upload_response.json()["video"]["id"]
    calibration_response = client.post(
        "/calibration/manual",
        json={
            "video_id": video_id,
            "image_points": {
                "top_left": [0, 0],
                "top_right": [96, 0],
                "bottom_right": [96, 96],
                "bottom_left": [0, 96],
            },
        },
    )
    assert calibration_response.status_code == 200
    calibration_id = calibration_response.json()["calibration_id"]

    result = AnalysisPipeline(
        detector=StaticDetector(),
        pose_estimator=StaticPoseEstimator(),
        frame_stride=1,
    ).run(
        job_id="job-overlay-test",
        video_id=video_id,
        calibration_id=calibration_id,
        frame_stride=1,
    )

    assert result.status == "completed"
    assert result.artifacts.source_video_url == f"/api/videos/{video_id}/stream"
    assert result.artifacts.tracking_overlay_url == "/api/analysis/jobs/job-overlay-test/artifacts/tracking-overlay"
    assert result.artifacts.player_selection_url == "/api/analysis/jobs/job-overlay-test/artifacts/player-selection"
    assert result.artifacts.player_selection_training_samples_url == "/api/analysis/jobs/job-overlay-test/artifacts/player-selection-training-samples"
    assert result.artifacts.pose_overlay_url == "/api/analysis/jobs/job-overlay-test/artifacts/pose-overlay"
    assert result.artifacts.player_trajectory_url == "/api/analysis/jobs/job-overlay-test/artifacts/player-trajectories"
    assert result.artifacts.serve_events_url == "/api/analysis/jobs/job-overlay-test/artifacts/serve-events"
    assert result.artifacts.court_view_roi_url == "/api/analysis/jobs/job-overlay-test/artifacts/court-view-roi"
    assert result.artifacts.tracking_overlay_status == "available"
    assert result.artifacts.pose_overlay_status == "available"
    assert result.artifacts.player_trajectory_status == "available"
    assert result.artifacts.serve_events_status in {"partial", "no_candidates"}
    assert result.artifacts.court_view_roi_status in {"available", "partial"}
    assert any(stage.id == "pose" and stage.status == "done" for stage in result.stages)
    assert any(stage.id == "serve-start-detection" for stage in result.stages)
    assert any(stage.id == "court-view-roi" for stage in result.stages)

    storage = StorageService()
    tracking_overlay = storage.read_json(storage.tracking_overlay_json_path("job-overlay-test"))
    player_selection = storage.read_json(storage.player_selection_json_path("job-overlay-test"))
    player_selection_samples = storage.read_json(storage.player_selection_training_samples_json_path("job-overlay-test"))
    player_trajectories = storage.read_json(storage.player_trajectory_json_path("job-overlay-test"))
    pose_overlay = storage.read_json(storage.pose_overlay_json_path("job-overlay-test"))
    serve_events = storage.read_json(storage.serve_events_json_path("job-overlay-test"))
    court_view_roi = storage.read_json(storage.court_view_roi_json_path("job-overlay-test"))
    assert tracking_overlay["frames"][0]["detections"][0]["track_id"] == "1"
    assert tracking_overlay["frames"][0]["detections"][0]["player_id"] == "Player_1"
    assert tracking_overlay["frames"][0]["detections"][0]["label"] == "P1 / T1"
    assert player_selection["selection_mode"] in {"rule", "fallback"}
    assert player_selection["diagnostics"]
    assert player_selection_samples["labels"] == ["target_player", "neighbor_court_player", "spectator", "uncertain"]
    assert player_selection_samples["samples"]
    assert player_trajectories["court"]["court_unit"] == "m"
    assert player_trajectories["players"]["Player_1"][0]["court_unit"] == "m"
    assert storage.player_trajectory_csv_path("job-overlay-test").exists()
    assert pose_overlay["frames"][0]["subjects"][0]["keypoints"][0]["name"] == "nose"
    assert serve_events["detector_version"] == "serve-moment-context-v1"
    assert court_view_roi["diagnostics"]["semantic_boundary"] == "court_view_candidates_are_not_rally_segmentation"
    assert court_view_roi["roi"]["status"] == "available"
    assert result.artifacts.serve_debug_candidates_url == "/api/analysis/jobs/job-overlay-test/artifacts/serve-debug-candidates"
    assert result.artifacts.serve_score_series_url == "/api/analysis/jobs/job-overlay-test/artifacts/serve-score-series"
    assert storage.serve_debug_candidates_json_path("job-overlay-test").exists()
    assert storage.serve_score_series_json_path("job-overlay-test").exists()


def test_pipeline_gates_non_court_frames_and_records_roi_artifact(tmp_path):
    video_bytes = make_court_then_non_court_video_bytes(tmp_path)
    upload_response = client.post(
        "/api/videos/upload",
        files={"file": ("court-gate.avi", video_bytes, "video/avi")},
    )
    assert upload_response.status_code == 200
    video_id = upload_response.json()["video"]["id"]
    calibration_response = client.post(
        "/calibration/manual",
        json={
            "video_id": video_id,
            "image_points": {
                "top_left": [0, 0],
                "top_right": [96, 0],
                "bottom_right": [96, 96],
                "bottom_left": [0, 96],
            },
        },
    )
    calibration_id = calibration_response.json()["calibration_id"]
    detector = RecordingStaticDetector()
    pipeline = AnalysisPipeline(detector=detector, frame_stride=1)
    pipeline.settings.court_view_start_frames = 1
    pipeline.settings.court_view_end_frames = 1
    pipeline.settings.court_view_match_threshold = 0.95

    result = pipeline.run(
        job_id="job-court-gate",
        video_id=video_id,
        calibration_id=calibration_id,
        frame_stride=1,
    )

    storage = StorageService()
    court_view_roi = storage.read_json(storage.court_view_roi_json_path("job-court-gate"))

    assert result.status == "completed"
    assert detector.frame_indices == [0]
    assert court_view_roi["processed_frame_count"] == 3
    assert court_view_roi["gated_frame_count"] == 2
    assert court_view_roi["frame_samples"][1]["reason"] == "gated_non_court_view"
    assert "不代表完整回合" in court_view_roi["detail"]


def test_pipeline_omits_ball_overlay_without_losing_player_overlay(tmp_path):
    video_bytes = make_test_video_bytes(tmp_path)
    upload_response = client.post(
        "/api/videos/upload",
        files={"file": ("player-only-overlay.avi", video_bytes, "video/avi")},
    )
    assert upload_response.status_code == 200
    video_id = upload_response.json()["video"]["id"]
    calibration_response = client.post(
        "/calibration/manual",
        json={
            "video_id": video_id,
            "image_points": {
                "top_left": [0, 0],
                "top_right": [96, 0],
                "bottom_right": [96, 96],
                "bottom_left": [0, 96],
            },
        },
    )
    assert calibration_response.status_code == 200
    calibration_id = calibration_response.json()["calibration_id"]

    result = AnalysisPipeline(
        detector=StaticDetector(),
        frame_stride=1,
    ).run(
        job_id="job-player-only-overlay",
        video_id=video_id,
        calibration_id=calibration_id,
        frame_stride=1,
    )

    assert result.status == "completed"
    assert result.artifacts.tracking_overlay_status == "available"
    assert result.artifacts.player_trajectory_status == "available"
    assert result.artifacts.ball_overlay_status is None
    assert result.artifacts.ball_overlay_url is None
    assert result.artifacts.detections_url is None
    assert result.artifacts.analysis_overlay_video_url is None
    assert all(stage.id != "ball-tracking" for stage in result.stages)

    storage = StorageService()
    assert storage.tracking_overlay_json_path("job-player-only-overlay").exists()
    assert storage.player_trajectory_json_path("job-player-only-overlay").exists()
    assert not storage.ball_overlay_json_path("job-player-only-overlay").exists()
    assert not storage.ball_trajectory_json_path("job-player-only-overlay").exists()
    assert not storage.cleaned_ball_trajectory_json_path("job-player-only-overlay").exists()
    assert not storage.bounce_events_json_path("job-player-only-overlay").exists()


def test_pipeline_filters_low_confidence_people_from_overlay_and_pose_inputs(tmp_path):
    video_bytes = make_test_video_bytes(tmp_path)
    upload_response = client.post(
        "/api/videos/upload",
        files={"file": ("filtered-overlay.avi", video_bytes, "video/avi")},
    )
    assert upload_response.status_code == 200
    video_id = upload_response.json()["video"]["id"]
    calibration_response = client.post(
        "/calibration/manual",
        json={
            "video_id": video_id,
            "image_points": {
                "top_left": [0, 0],
                "top_right": [96, 0],
                "bottom_right": [96, 96],
                "bottom_left": [0, 96],
            },
        },
    )
    assert calibration_response.status_code == 200
    calibration_id = calibration_response.json()["calibration_id"]
    pose_estimator = RecordingPoseEstimator()

    result = AnalysisPipeline(
        detector=PlayerAndLowConfidenceSpectatorDetector(),
        pose_estimator=pose_estimator,
        frame_stride=1,
    ).run(
        job_id="job-filtered-overlay",
        video_id=video_id,
        calibration_id=calibration_id,
        frame_stride=1,
    )

    assert result.status == "completed"
    assert len(result.tracks) == 3
    assert len(result.stages) > 0

    storage = StorageService()
    tracking_result = storage.read_json(storage.tracking_json_path("job-filtered-overlay"))
    tracking_overlay = storage.read_json(storage.tracking_overlay_json_path("job-filtered-overlay"))
    pose_overlay = storage.read_json(storage.pose_overlay_json_path("job-filtered-overlay"))
    overlay_track_ids = {
        detection["track_id"]
        for frame in tracking_overlay["frames"]
        for detection in frame["detections"]
    }
    pose_track_ids = {
        subject["track_id"]
        for frame in pose_overlay["frames"]
        for subject in frame["subjects"]
    }

    assert len(tracking_result["detections"]) == 6
    assert {track["track_id"] for track in tracking_result["tracks"]} == {1, 2}
    assert overlay_track_ids == {"1"}
    assert pose_track_ids == {"1"}
    assert pose_estimator.subject_track_ids == [["1"], ["1"], ["1"]]
    assert "主要球员" in (result.artifacts.tracking_overlay_detail or "")


def test_pipeline_keeps_high_confidence_line_out_players_for_overlay_and_pose(tmp_path):
    video_bytes = make_test_video_bytes(tmp_path)
    upload_response = client.post(
        "/api/videos/upload",
        files={"file": ("line-out-overlay.avi", video_bytes, "video/avi")},
    )
    assert upload_response.status_code == 200
    video_id = upload_response.json()["video"]["id"]
    calibration_response = client.post(
        "/calibration/manual",
        json={
            "video_id": video_id,
            "image_points": {
                "top_left": [0, 0],
                "top_right": [96, 0],
                "bottom_right": [96, 96],
                "bottom_left": [0, 96],
            },
        },
    )
    assert calibration_response.status_code == 200
    calibration_id = calibration_response.json()["calibration_id"]
    pose_estimator = RecordingPoseEstimator()

    result = AnalysisPipeline(
        detector=HighConfidenceLineOutDetector(),
        pose_estimator=pose_estimator,
        frame_stride=1,
    ).run(
        job_id="job-line-out-overlay",
        video_id=video_id,
        calibration_id=calibration_id,
        frame_stride=1,
    )

    assert result.status == "completed"
    assert result.tracks == []

    storage = StorageService()
    tracking_result = storage.read_json(storage.tracking_json_path("job-line-out-overlay"))
    tracking_overlay = storage.read_json(storage.tracking_overlay_json_path("job-line-out-overlay"))
    pose_overlay = storage.read_json(storage.pose_overlay_json_path("job-line-out-overlay"))
    overlay_track_ids = {
        detection["track_id"]
        for frame in tracking_overlay["frames"]
        for detection in frame["detections"]
    }
    pose_track_ids = {
        subject["track_id"]
        for frame in pose_overlay["frames"]
        for subject in frame["subjects"]
    }

    assert len(tracking_result["detections"]) == 3
    assert len(tracking_result["positions"]) == 3
    assert all(position["valid"] is False for position in tracking_result["positions"])
    assert overlay_track_ids == {"1"}
    assert pose_track_ids == {"1"}
    assert pose_estimator.subject_track_ids == [["1"], ["1"], ["1"]]


def test_pipeline_does_not_advertise_empty_pose_keypoints(tmp_path):
    video_bytes = make_test_video_bytes(tmp_path)
    upload_response = client.post(
        "/api/videos/upload",
        files={"file": ("empty-pose.avi", video_bytes, "video/avi")},
    )
    assert upload_response.status_code == 200
    video_id = upload_response.json()["video"]["id"]
    calibration_response = client.post(
        "/calibration/manual",
        json={
            "video_id": video_id,
            "image_points": {
                "top_left": [0, 0],
                "top_right": [96, 0],
                "bottom_right": [96, 96],
                "bottom_left": [0, 96],
            },
        },
    )
    assert calibration_response.status_code == 200
    calibration_id = calibration_response.json()["calibration_id"]

    result = AnalysisPipeline(
        detector=StaticDetector(),
        pose_estimator=EmptyPoseEstimator(),
        frame_stride=1,
    ).run(
        job_id="job-empty-pose",
        video_id=video_id,
        calibration_id=calibration_id,
        frame_stride=1,
    )

    assert result.artifacts.pose_overlay_url is None
    assert result.artifacts.pose_overlay_status == "unavailable"
    assert "未生成骨架关节" in (result.artifacts.pose_overlay_detail or "")
    assert any(stage.id == "pose" and stage.status == "skipped" for stage in result.stages)


def test_pipeline_reports_pose_failure_without_losing_tracking_overlay(tmp_path):
    video_bytes = make_test_video_bytes(tmp_path)
    upload_response = client.post(
        "/api/videos/upload",
        files={"file": ("failing-pose.avi", video_bytes, "video/avi")},
    )
    assert upload_response.status_code == 200
    video_id = upload_response.json()["video"]["id"]
    calibration_response = client.post(
        "/calibration/manual",
        json={
            "video_id": video_id,
            "image_points": {
                "top_left": [0, 0],
                "top_right": [96, 0],
                "bottom_right": [96, 96],
                "bottom_left": [0, 96],
            },
        },
    )
    assert calibration_response.status_code == 200
    calibration_id = calibration_response.json()["calibration_id"]

    result = AnalysisPipeline(
        detector=StaticDetector(),
        pose_estimator=FailingPoseEstimator(),
        frame_stride=1,
    ).run(
        job_id="job-failing-pose",
        video_id=video_id,
        calibration_id=calibration_id,
        frame_stride=1,
    )

    assert result.status == "completed"
    assert result.artifacts.tracking_overlay_status == "available"
    assert result.artifacts.pose_overlay_url is None
    assert result.artifacts.pose_overlay_status == "unavailable"
    assert "mmpose missing" in (result.artifacts.pose_overlay_detail or "")


def test_pipeline_reports_missing_rtmpose_assets_without_losing_tracking_overlay(tmp_path):
    video_bytes = make_test_video_bytes(tmp_path)
    upload_response = client.post(
        "/api/videos/upload",
        files={"file": ("missing-assets.avi", video_bytes, "video/avi")},
    )
    assert upload_response.status_code == 200
    video_id = upload_response.json()["video"]["id"]
    calibration_response = client.post(
        "/calibration/manual",
        json={
            "video_id": video_id,
            "image_points": {
                "top_left": [0, 0],
                "top_right": [96, 0],
                "bottom_right": [96, 96],
                "bottom_left": [0, 96],
            },
        },
    )
    assert calibration_response.status_code == 200
    calibration_id = calibration_response.json()["calibration_id"]

    result = AnalysisPipeline(
        detector=StaticDetector(),
        pose_estimator=RTMPose26Adapter(
            config_path=str(tmp_path / "missing_config.py"),
            checkpoint_path=str(tmp_path / "missing_checkpoint.pth"),
        ),
        frame_stride=1,
    ).run(
        job_id="job-missing-pose-assets",
        video_id=video_id,
        calibration_id=calibration_id,
        frame_stride=1,
    )

    assert result.status == "completed"
    assert result.artifacts.tracking_overlay_status == "available"
    assert result.artifacts.pose_overlay_url is None
    assert result.artifacts.pose_overlay_status == "unavailable"
    assert "RTMPose config not found" in (result.artifacts.pose_overlay_detail or "")


def test_pipeline_reports_unsupported_pose_schema_without_losing_tracking_overlay(tmp_path):
    video_bytes = make_test_video_bytes(tmp_path)
    upload_response = client.post(
        "/api/videos/upload",
        files={"file": ("bad-schema.avi", video_bytes, "video/avi")},
    )
    assert upload_response.status_code == 200
    video_id = upload_response.json()["video"]["id"]
    calibration_response = client.post(
        "/calibration/manual",
        json={
            "video_id": video_id,
            "image_points": {
                "top_left": [0, 0],
                "top_right": [96, 0],
                "bottom_right": [96, 96],
                "bottom_left": [0, 96],
            },
        },
    )
    assert calibration_response.status_code == 200
    calibration_id = calibration_response.json()["calibration_id"]

    result = AnalysisPipeline(
        detector=StaticDetector(),
        pose_estimator=RTMPose26Adapter(
            config_path=None,
            checkpoint_path=None,
            keypoint_schema="coco17",
        ),
        frame_stride=1,
    ).run(
        job_id="job-bad-pose-schema",
        video_id=video_id,
        calibration_id=calibration_id,
        frame_stride=1,
    )

    assert result.status == "completed"
    assert result.artifacts.tracking_overlay_status == "available"
    assert result.artifacts.pose_overlay_url is None
    assert result.artifacts.pose_overlay_status == "unavailable"
    assert "Unsupported RTMPose keypoint schema" in (result.artifacts.pose_overlay_detail or "")


def test_pipeline_reports_unavailable_overlay_when_yolo_is_disabled(tmp_path):
    video_bytes = make_test_video_bytes(tmp_path)
    upload_response = client.post(
        "/api/videos/upload",
        files={"file": ("disabled.avi", video_bytes, "video/avi")},
    )
    assert upload_response.status_code == 200
    video_id = upload_response.json()["video"]["id"]
    calibration_response = client.post(
        "/calibration/manual",
        json={
            "video_id": video_id,
            "image_points": {
                "top_left": [0, 0],
                "top_right": [96, 0],
                "bottom_right": [96, 96],
                "bottom_left": [0, 96],
            },
        },
    )
    assert calibration_response.status_code == 200
    calibration_id = calibration_response.json()["calibration_id"]

    result = AnalysisPipeline(
        detector=EmptyPersonDetector(),
        frame_stride=1,
    ).run(
        job_id="job-overlay-disabled",
        video_id=video_id,
        calibration_id=calibration_id,
        frame_stride=1,
    )

    assert result.artifacts.tracking_overlay_status == "unavailable"
    assert "YOLO 人体检测未启用" in (result.artifacts.tracking_overlay_detail or "")
    assert any(stage.id == "detection" and stage.status == "skipped" for stage in result.stages)
    assert any(stage.id == "tracking" and stage.status == "skipped" for stage in result.stages)

    storage = StorageService()
    tracking_overlay = storage.read_json(storage.tracking_overlay_json_path("job-overlay-disabled"))
    assert tracking_overlay["status"] == "unavailable"
    assert "YOLO 人体检测未启用" in tracking_overlay["detail"]


def test_analysis_artifact_endpoint_returns_browser_safe_json():
    payload = AnalysisJobCreate(
        metadata={
            "fileName": "artifact.mp4",
            "fileSize": 16,
            "matchTitle": "Artifact Test",
            "venue": "Test Court",
            "matchDate": "2026-05-07",
            "matchFormat": "doubles",
            "cameraAngle": "elevated",
            "athleteLabel": "Player A",
            "level": "MVP",
        },
    )
    job = create_analysis_job(payload)
    storage = StorageService()
    storage.write_json(
        storage.tracking_overlay_json_path(job.id),
        {
            "job_id": job.id,
            "video_id": "video-artifact",
            "status": "no_detections",
            "detail": "test artifact",
            "source": {"width": 96, "height": 96},
            "fps": 5,
            "frame_count": 1,
            "processed_frame_count": 1,
            "frame_stride": 1,
            "frames": [],
        },
    )

    response = client.get(f"/api/analysis/jobs/{job.id}/artifacts/tracking-overlay")

    assert response.status_code == 200
    assert response.json()["detail"] == "test artifact"


def test_analysis_artifact_endpoint_accepts_missing_ball_overlay_as_known_artifact():
    payload = AnalysisJobCreate(
        metadata={
            "fileName": "missing-ball-artifact.mp4",
            "fileSize": 16,
            "matchTitle": "Missing Ball Artifact Test",
            "venue": "Test Court",
            "matchDate": "2026-05-07",
            "matchFormat": "doubles",
            "cameraAngle": "elevated",
            "athleteLabel": "Player A",
            "level": "MVP",
        },
    )
    job = create_analysis_job(payload)

    response = client.get(f"/api/analysis/jobs/{job.id}/artifacts/ball-overlay")

    assert response.status_code == 404


def test_analysis_job_with_missing_video_fails_cleanly():
    payload = {
        "videoId": "video-does-not-exist",
        "metadata": {
            "fileName": "missing.mp4",
            "fileSize": 16,
            "matchTitle": "Missing Video",
            "venue": "Test Court",
            "matchDate": "2026-05-07",
            "matchFormat": "doubles",
            "cameraAngle": "elevated",
            "athleteLabel": "Player A",
            "level": "MVP",
        },
    }

    response = client.post("/api/analysis/jobs", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["errorMessage"] == "Uploaded video not found"


def make_temp_storage(tmp_path):
    settings = Settings(
        uploads_dir=tmp_path / "uploads",
        outputs_dir=tmp_path / "outputs",
        calibrations_dir=tmp_path / "calibrations",
        tmp_dir=tmp_path / "tmp",
    )
    return StorageService(settings)


def snapshot_analysis_state():
    return JOBS.copy(), REPORTS.copy(), RESULTS.copy()


def restore_analysis_state(snapshot):
    jobs, reports, results = snapshot
    JOBS.clear()
    JOBS.update(jobs)
    REPORTS.clear()
    REPORTS.update(reports)
    RESULTS.clear()
    RESULTS.update(results)


def make_job_summary(
    job_id,
    *,
    status="completed",
    match_title="Task Match",
    progress=100,
    created_at="2026-05-20T09:00:00+00:00",
    updated_at="2026-05-20T09:00:00+00:00",
):
    stage = "report" if status == "completed" else "queue"
    return AnalysisJobSummarySchema(
        id=job_id,
        status=status,
        stage=stage,
        progress=progress,
        createdAt=created_at,
        updatedAt=updated_at,
        metadata={
            "fileName": f"{job_id}.mp4",
            "fileSize": 100,
            "matchTitle": match_title,
            "venue": "Task Test Court",
            "matchDate": "2026-05-20",
            "matchFormat": "doubles",
            "cameraAngle": "elevated",
            "athleteLabel": "Task Player",
            "level": "MVP",
        },
        stages=build_stages(stage),
        reportId=f"PV-{job_id.upper()}",
        analysisMode="real",
    )


class DeferredTasks:
    def __init__(self):
        self.tasks = []

    def add_task(self, fn, *args, **kwargs):
        self.tasks.append((fn, args, kwargs))

    def run_all(self):
        for fn, args, kwargs in self.tasks:
            fn(*args, **kwargs)


class StaticDetector:
    def detect_frame(self, frame, frame_index):
        return [Detection(bbox=[18.0, 16.0, 48.0, 82.0], confidence=0.91)]


class RecordingStaticDetector:
    def __init__(self):
        self.frame_indices = []

    def detect_frame(self, frame, frame_index):
        self.frame_indices.append(frame_index)
        return [Detection(bbox=[18.0, 16.0, 48.0, 82.0], confidence=0.91)]


class PlayerAndLowConfidenceSpectatorDetector:
    def detect_frame(self, frame, frame_index):
        return [
            Detection(bbox=[18.0, 16.0, 48.0, 82.0], confidence=0.91),
            Detection(bbox=[100.0, 16.0, 130.0, 82.0], confidence=0.42),
        ]


class HighConfidenceLineOutDetector:
    def detect_frame(self, frame, frame_index):
        return [Detection(bbox=[100.0, 16.0, 130.0, 82.0], confidence=0.88)]


class StaticPoseEstimator:
    def estimate_frame(self, frame, subjects, frame_index, timestamp_seconds):
        return PoseOverlayFrame(
            frame_index=frame_index,
            timestamp_seconds=timestamp_seconds,
            subjects=[
                PoseSubject(
                    track_id=subjects[0].track_id or "1",
                    bbox=subjects[0].bbox,
                    confidence=0.9,
                    keypoints=[
                        PoseKeypoint(name="nose", x=32, y=22, confidence=0.95),
                        PoseKeypoint(name="left_shoulder", x=25, y=38, confidence=0.95),
                        PoseKeypoint(name="right_shoulder", x=40, y=38, confidence=0.95),
                    ],
                )
            ],
        )


class RecordingPoseEstimator:
    def __init__(self):
        self.subject_track_ids = []

    def estimate_frame(self, frame, subjects, frame_index, timestamp_seconds):
        self.subject_track_ids.append([subject.track_id for subject in subjects])
        return PoseOverlayFrame(
            frame_index=frame_index,
            timestamp_seconds=timestamp_seconds,
            subjects=[
                PoseSubject(
                    track_id=subject.track_id or "unknown",
                    bbox=subject.bbox,
                    confidence=0.9,
                    keypoints=[PoseKeypoint(name="nose", x=32, y=22, confidence=0.95)],
                )
                for subject in subjects
            ],
        )


class EmptyPoseEstimator:
    def estimate_frame(self, frame, subjects, frame_index, timestamp_seconds):
        return PoseOverlayFrame(
            frame_index=frame_index,
            timestamp_seconds=timestamp_seconds,
            subjects=[
                PoseSubject(
                    track_id=subjects[0].track_id or "1",
                    bbox=subjects[0].bbox,
                    confidence=0.9,
                    keypoints=[],
                )
            ],
        )


class FailingPoseEstimator:
    def estimate_frame(self, frame, subjects, frame_index, timestamp_seconds):
        raise RuntimeError("mmpose missing")


def make_test_video_bytes(tmp_path):
    import cv2  # type: ignore
    import numpy as np

    path = tmp_path / "overlay.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 5.0, (96, 96))
    for _ in range(3):
        frame = np.zeros((96, 96, 3), dtype=np.uint8)
        frame[16:82, 18:48] = (255, 255, 255)
        writer.write(frame)
    writer.release()
    return path.read_bytes()


def make_court_then_non_court_video_bytes(tmp_path):
    import cv2  # type: ignore
    import numpy as np

    path = tmp_path / "court-gate.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 5.0, (96, 96))
    court = np.zeros((96, 96, 3), dtype=np.uint8)
    court[16:82, 18:48] = (255, 255, 255)
    non_court = np.zeros((96, 96, 3), dtype=np.uint8)
    non_court[:, :] = (40, 10, 120)
    writer.write(court)
    writer.write(non_court)
    writer.write(non_court)
    writer.release()
    return path.read_bytes()
