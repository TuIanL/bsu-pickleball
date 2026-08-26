from __future__ import annotations

from datetime import UTC, datetime

from app.schemas.analysis import AnalysisJobCreate, AnalysisUploadMetadata, MultiViewCreateRequest, MultiViewViewPayload
from app.schemas.metric_court_scene import MetricCourtSceneCalibration, SceneViewCalibration
from app.services.job_orchestration import analysis_signature
from app.services.multiview_coordinator import preflight_multiview, validate_scene_view_provenance
from app.vision.multiview.metric_court_scene import build_standard_net_profile


def _payload(*, revision: int | None, mode: str = "metric") -> AnalysisJobCreate:
    metadata = AnalysisUploadMetadata(
        fileName="take.mp4",
        matchTitle="test",
        venue="court",
        matchDate="2026-08-25",
        matchFormat="singles",
        cameraAngle="baseline",
        athleteLabel="test",
        level="test",
        capture_take_id="take-1",
    )
    return AnalysisJobCreate(
        metadata=metadata,
        analysisKind="multiview",
        multiview=MultiViewCreateRequest(
            referenceViewId="cam_1",
            views=[
                MultiViewViewPayload(viewId="cam_1", videoId="video-a", calibrationId="cal-a"),
                MultiViewViewPayload(viewId="cam_2", videoId="video-b", calibrationId="cal-b"),
            ],
            sceneCalibrationMode=mode,
            sceneCalibrationRevision=revision,
        ),
    )


def test_metric_mode_requires_a_scene_revision_before_storage_checks() -> None:
    result = preflight_multiview(_payload(revision=None))
    assert not result.ok
    assert result.issues == ["metric scene calibration revision required"]


def test_scene_revision_and_fallback_mode_change_job_signature() -> None:
    metric_v1 = _payload(revision=1)
    metric_v2 = _payload(revision=2)
    approximate = _payload(revision=None, mode="approximate")

    assert analysis_signature(metric_v1) != analysis_signature(metric_v2)
    assert analysis_signature(metric_v1) != analysis_signature(approximate)


def test_scene_provenance_reports_camera_video_and_image_size_mismatches_independently() -> None:
    now = datetime.now(UTC)
    scene = MetricCourtSceneCalibration(
        capture_take_id="take-1",
        status="ready",
        canonical_frame_id="frame-1",
        net_profile=build_standard_net_profile(),
        views=[SceneViewCalibration(
            view_id="cam_1",
            camera_id="camera-a",
            video_id="video-a",
            image_width=1280,
            image_height=720,
        )],
        created_at=now,
        updated_at=now,
    )
    views = [MultiViewViewPayload(
        viewId="cam_1",
        cameraId="camera-b",
        videoId="video-b",
        calibrationId="cal-1",
        imageWidth=1920,
        imageHeight=1080,
    )]

    issues = validate_scene_view_provenance(scene, "take-1", views)
    assert "scene camera provenance mismatch for view cam_1" in issues
    assert "scene video provenance mismatch for view cam_1" in issues
    assert "scene image width mismatch for view cam_1" in issues
    assert "scene image height mismatch for view cam_1" in issues
