from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.config import Settings
from app.main import app
from app.schemas.analysis import AnalysisJobSummary as AnalysisJobSummarySchema
from app.schemas.tracking import Detection
from app.services.storage_service import StorageService
from app.services.analysis_pipeline import AnalysisPipeline
from app.vision.pickleball_game_analysis.minimap_visualizer import MinimapVisualizer
from app.vision.pickleball_game_analysis.overlay_video_writer import OverlayVideoWriter
from app.vision.pickleball_game_analysis.position_visualizer import PositionVisualizer
from app.vision.pickleball_game_analysis.visualization_schemas import (
    VisualizationConfig,
    VisualizationPoint,
    ball_points_from_artifact,
    normalize_court_point,
    player_points_from_artifact,
)
from fastapi.testclient import TestClient


client = TestClient(app)


def test_normalize_court_point_accepts_feet_and_meters():
    assert normalize_court_point([10, 22], "ft") == pytest.approx((10, 22))
    assert normalize_court_point({"x": 3.048, "y": 6.7056, "unit": "m"}) == pytest.approx((10, 22))
    assert normalize_court_point({"x": "bad", "y": 1}, "ft") is None


def test_player_and_ball_artifact_points_are_normalized_to_feet():
    player_payload = {
        "court": {"court_unit": "m"},
        "players": {
            "Player_1": [
                {
                    "frame_index": 0,
                    "timestamp_seconds": 0.0,
                    "court_x": 3.048,
                    "court_y": 6.7056,
                    "court_unit": "m",
                    "confidence": 0.9,
                }
            ]
        },
    }
    ball_payload = {
        "coordinate_system": {"court": "feet"},
        "samples": [{"frame_index": 1, "timestamp_sec": 0.2, "court_xy": [12, 24], "confidence": 0.8}],
    }

    player_points = player_points_from_artifact(player_payload)
    ball_points = ball_points_from_artifact(ball_payload)

    assert player_points[0].court_xy == pytest.approx((10, 22))
    assert player_points[0].label == "Player_1"
    assert ball_points[0].court_xy == pytest.approx((12, 24))


def test_minimap_maps_court_geometry_and_skips_out_of_bounds():
    minimap = MinimapVisualizer(VisualizationConfig(minimap_width=120, minimap_height=240, minimap_padding=10))

    assert minimap.court_to_pixel(0, 0) == (10, 10)
    assert minimap.court_to_pixel(20, 44) == (110, 230)
    assert minimap.court_to_pixel(10, 22) == (60, 120)
    assert minimap.court_to_pixel(-1, 22) is None

    image = minimap.render(
        player_points=[VisualizationPoint(10, 22, label="Player_1")],
        ball_points=[VisualizationPoint(11, 23)],
        bounce_points=[VisualizationPoint(12, 24)],
    )
    assert image.shape == (240, 120, 3)
    assert image.sum() > 0


def test_position_visualizer_writes_manifests_and_images(tmp_path):
    config = VisualizationConfig(minimap_width=120, minimap_height=240, minimap_padding=10)
    visualizer = PositionVisualizer(config)
    heat_result, scatter_result = visualizer.generate(
        job_id="job-vis",
        heatmaps_dir=tmp_path / "heatmaps",
        scatter_plots_dir=tmp_path / "scatter_plots",
        heatmaps_manifest_path=tmp_path / "heatmaps" / "manifest.json",
        scatter_manifest_path=tmp_path / "scatter_plots" / "manifest.json",
        image_url_prefix="/api/analysis/jobs/job-vis/artifacts/position-visualization-images",
        heatmaps_artifact_url="/api/analysis/jobs/job-vis/artifacts/position-heatmaps",
        scatter_artifact_url="/api/analysis/jobs/job-vis/artifacts/position-scatter-plots",
        player_points=[VisualizationPoint(10, 22, label="Player_1")],
        ball_points=[VisualizationPoint(11, 23)],
        bounce_points=[VisualizationPoint(12, 24)],
    )

    assert heat_result.status == "available"
    assert scatter_result.status == "available"
    heat_manifest = json.loads((tmp_path / "heatmaps" / "manifest.json").read_text(encoding="utf-8"))
    scatter_manifest = json.loads((tmp_path / "scatter_plots" / "manifest.json").read_text(encoding="utf-8"))
    assert heat_manifest["items"][0]["artifact_url"].endswith("/position-heatmaps")
    assert heat_manifest["items"][0]["source_artifacts"] == ["players_trajectory.json"]
    assert len(scatter_manifest["items"]) == 3
    assert (tmp_path / "heatmaps" / heat_manifest["items"][0]["file_name"]).exists()


def test_position_visualizer_writes_no_data_manifests(tmp_path):
    visualizer = PositionVisualizer(VisualizationConfig(minimap_width=120, minimap_height=240, minimap_padding=10))
    heat_result, scatter_result = visualizer.generate(
        job_id="job-empty",
        heatmaps_dir=tmp_path / "heatmaps",
        scatter_plots_dir=tmp_path / "scatter_plots",
        heatmaps_manifest_path=tmp_path / "heatmaps" / "manifest.json",
        scatter_manifest_path=tmp_path / "scatter_plots" / "manifest.json",
        image_url_prefix="/api/analysis/jobs/job-empty/artifacts/position-visualization-images",
        heatmaps_artifact_url="/api/analysis/jobs/job-empty/artifacts/position-heatmaps",
        scatter_artifact_url="/api/analysis/jobs/job-empty/artifacts/position-scatter-plots",
        player_points=[],
        ball_points=[],
        bounce_points=[],
    )

    assert heat_result.status == "no_data"
    assert scatter_result.status == "no_data"
    assert json.loads((tmp_path / "heatmaps" / "manifest.json").read_text(encoding="utf-8"))["items"] == []
    assert json.loads((tmp_path / "scatter_plots" / "manifest.json").read_text(encoding="utf-8"))["items"] == []


def test_overlay_writer_generates_video_with_tracking_only(tmp_path):
    video = _make_video(tmp_path / "source.avi")
    output = tmp_path / "analysis_overlay.mp4"
    result = OverlayVideoWriter(VisualizationConfig(minimap_width=80, minimap_height=160, minimap_padding=8)).write(
        source_video_path=video,
        output_path=output,
        tracking_overlay={
            "frames": [
                {
                    "frame_index": 0,
                    "detections": [{"bbox": [5, 5, 25, 25], "label": "P1 / T1"}],
                }
            ]
        },
    )

    assert result.status == "available"
    assert output.exists()
    assert output.stat().st_size > 0


def test_overlay_writer_generates_video_with_ball_and_bounce_points(tmp_path):
    video = _make_video(tmp_path / "source-ball.avi")
    output = tmp_path / "analysis_overlay_ball.mp4"
    result = OverlayVideoWriter(VisualizationConfig(minimap_width=80, minimap_height=160, minimap_padding=8)).write(
        source_video_path=video,
        output_path=output,
        ball_overlay={
            "frames": [
                {
                    "frame_index": 0,
                    "ball": {"center": {"x": 20, "y": 20}, "track_status": "detected"},
                }
            ]
        },
        ball_points=[VisualizationPoint(11, 22, frame_index=0)],
        bounce_points=[VisualizationPoint(12, 24, frame_index=0, label="bounce-1")],
    )

    assert result.status == "available"
    assert output.exists()
    assert output.stat().st_size > 0


def test_overlay_writer_reports_unavailable_source(tmp_path):
    result = OverlayVideoWriter().write(source_video_path=tmp_path / "missing.mp4", output_path=tmp_path / "out.mp4")

    assert result.status == "unavailable"
    assert not (tmp_path / "out.mp4").exists()


def test_position_visualization_image_route_returns_png(monkeypatch, tmp_path):
    from app.services.mock_analysis import JOBS

    storage = StorageService(Settings(uploads_dir=tmp_path / "uploads", outputs_dir=tmp_path / "outputs", calibrations_dir=tmp_path / "calibrations", tmp_dir=tmp_path / "tmp"))
    monkeypatch.setattr("app.api.routes_analysis._STORAGE", storage)
    snapshot = JOBS.copy()
    JOBS.clear()
    job = _make_job_summary("job-image-route")
    JOBS[job.id] = job
    path = storage.heatmaps_dir(job.id) / "plot.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n")

    try:
        response = client.get(f"/api/analysis/jobs/{job.id}/artifacts/position-visualization-images/heatmaps/plot.png")
    finally:
        JOBS.clear()
        JOBS.update(snapshot)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")


def test_pipeline_generates_position_visualization_when_enabled(tmp_path):
    video_bytes = _make_video(tmp_path / "pipeline-source.avi").read_bytes()
    upload_response = client.post(
        "/api/videos/upload",
        files={"file": ("visualization.avi", video_bytes, "video/avi")},
    )
    assert upload_response.status_code == 200
    video_id = upload_response.json()["video"]["id"]
    calibration_response = client.post(
        "/calibration/manual",
        json={
            "video_id": video_id,
            "image_points": {
                "top_left": [0, 0],
                "top_right": [64, 0],
                "bottom_right": [64, 64],
                "bottom_left": [0, 64],
            },
        },
    )
    assert calibration_response.status_code == 200

    pipeline = AnalysisPipeline(detector=_StaticDetector(), frame_stride=1)
    previous_overlay = pipeline.settings.enable_analysis_overlay_video
    previous_positions = pipeline.settings.enable_position_visualizations
    pipeline.settings.enable_position_visualizations = True
    pipeline.settings.enable_analysis_overlay_video = False
    try:
        result = pipeline.run(
            job_id="job-position-visualization",
            video_id=video_id,
            calibration_id=calibration_response.json()["calibration_id"],
            frame_stride=1,
        )
    finally:
        pipeline.settings.enable_analysis_overlay_video = previous_overlay
        pipeline.settings.enable_position_visualizations = previous_positions

    storage = StorageService()
    heat_manifest = storage.read_json(storage.heatmaps_manifest_json_path("job-position-visualization"))
    scatter_manifest = storage.read_json(storage.scatter_plots_manifest_json_path("job-position-visualization"))

    assert result.status == "completed"
    assert result.artifacts.heatmaps_url == "/api/analysis/jobs/job-position-visualization/artifacts/position-heatmaps"
    assert result.artifacts.scatter_plots_url == "/api/analysis/jobs/job-position-visualization/artifacts/position-scatter-plots"
    assert result.artifacts.position_visualizations_status == "available"
    assert result.artifacts.analysis_overlay_video_url is None
    assert any(stage.id == "visualization" and stage.status == "done" for stage in result.stages)
    assert heat_manifest["items"]
    assert scatter_manifest["items"]


def test_pipeline_reports_overlay_failure_without_failing_job(monkeypatch, tmp_path):
    video_bytes = _make_video(tmp_path / "pipeline-overlay-source.avi").read_bytes()
    upload_response = client.post(
        "/api/videos/upload",
        files={"file": ("overlay-fail.avi", video_bytes, "video/avi")},
    )
    video_id = upload_response.json()["video"]["id"]
    calibration_response = client.post(
        "/calibration/manual",
        json={
            "video_id": video_id,
            "image_points": {
                "top_left": [0, 0],
                "top_right": [64, 0],
                "bottom_right": [64, 64],
                "bottom_left": [0, 64],
            },
        },
    )

    def fail_write(self, **kwargs):
        from app.vision.pickleball_game_analysis.visualization_schemas import VisualizationResult

        return VisualizationResult("failed", "forced overlay failure")

    monkeypatch.setattr("app.services.analysis_pipeline.OverlayVideoWriter.write", fail_write)
    pipeline = AnalysisPipeline(detector=_StaticDetector(), frame_stride=1)
    previous_overlay = pipeline.settings.enable_analysis_overlay_video
    previous_positions = pipeline.settings.enable_position_visualizations
    pipeline.settings.enable_analysis_overlay_video = True
    pipeline.settings.enable_position_visualizations = False
    try:
        result = pipeline.run(
            job_id="job-overlay-failure",
            video_id=video_id,
            calibration_id=calibration_response.json()["calibration_id"],
            frame_stride=1,
        )
    finally:
        pipeline.settings.enable_analysis_overlay_video = previous_overlay
        pipeline.settings.enable_position_visualizations = previous_positions

    assert result.status == "completed"
    assert result.artifacts.analysis_overlay_video_status == "failed"
    assert result.artifacts.analysis_overlay_video_url is None
    assert any(stage.id == "visualization" and stage.status == "failed" for stage in result.stages)


def _make_video(path: Path) -> Path:
    import cv2  # type: ignore
    import numpy as np

    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 5.0, (64, 64))
    for index in range(2):
        frame = np.zeros((64, 64, 3), dtype=np.uint8)
        frame[10 + index : 30 + index, 12:32] = (255, 255, 255)
        writer.write(frame)
    writer.release()
    return path


class _StaticDetector:
    def detect_frame(self, frame, frame_index):
        return [Detection(bbox=[12.0, 10.0, 32.0, 42.0], confidence=0.91)]


def _make_job_summary(job_id: str) -> AnalysisJobSummarySchema:
    return AnalysisJobSummarySchema(
        id=job_id,
        status="completed",
        stage="report",
        progress=100,
        createdAt="2026-05-20T09:00:00+00:00",
        updatedAt="2026-05-20T09:00:00+00:00",
        metadata={
            "fileName": f"{job_id}.mp4",
            "fileSize": 100,
            "matchTitle": "Visualization Test",
            "venue": "Task Test Court",
            "matchDate": "2026-05-20",
            "matchFormat": "doubles",
            "cameraAngle": "elevated",
            "athleteLabel": "Task Player",
            "level": "MVP",
        },
        stages=[],
        reportId=f"PV-{job_id.upper()}",
        analysisMode="real",
    )
