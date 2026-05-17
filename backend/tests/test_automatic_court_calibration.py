import numpy as np

from app.core.config import Settings
from app.schemas.calibration import (
    AutomaticCalibrationRequest,
    ManualImageKeypoints,
    SemiAutomaticCalibrationAcceptRequest,
)
from app.services.automatic_calibration_service import AutomaticCalibrationService
from app.services.calibration_service import CALIBRATIONS, CalibrationService
from app.services.storage_service import StorageService
from app.services.video_service import VideoService
from app.vision.courtvision_calibration_engine.court_line_segmentation import CourtLineSegmentationResult
from app.vision.courtvision_calibration_engine.mask_to_keypoints import mask_to_court_keypoints


def test_mask_to_court_keypoints_extracts_synthetic_court_boundary():
    mask = np.zeros((120, 160), dtype=np.uint8)
    mask[20:25, 30:130] = 255
    mask[95:100, 30:130] = 255
    mask[20:100, 30:35] = 255
    mask[20:100, 125:130] = 255

    result = mask_to_court_keypoints(mask, min_area_ratio=0.01)

    assert result.line_count >= 4
    assert result.confidence > 0.4
    assert result.keypoints.top_left.x < result.keypoints.top_right.x
    assert result.keypoints.top_left.y < result.keypoints.bottom_left.y


def test_automatic_calibration_service_returns_unavailable_without_model(tmp_path):
    settings = Settings(
        uploads_dir=tmp_path / "uploads",
        outputs_dir=tmp_path / "outputs",
        calibrations_dir=tmp_path / "calibrations",
        tmp_dir=tmp_path / "tmp",
        court_line_model_path=None,
    )
    storage = StorageService(settings)
    service = AutomaticCalibrationService(
        video_service=VideoService(storage),
        calibration_service=CalibrationService(storage),
        storage=storage,
        settings=settings,
    )

    response = service.suggest(AutomaticCalibrationRequest(video_id="missing-video"))

    assert response.status == "unavailable"
    assert response.mask.model_configured is False


def test_automatic_calibration_service_accepts_corrected_keypoints(tmp_path):
    CALIBRATIONS.clear()
    settings = Settings(
        uploads_dir=tmp_path / "uploads",
        outputs_dir=tmp_path / "outputs",
        calibrations_dir=tmp_path / "calibrations",
        tmp_dir=tmp_path / "tmp",
    )
    storage = StorageService(settings)
    service = AutomaticCalibrationService(
        video_service=VideoService(storage),
        calibration_service=CalibrationService(storage),
        storage=storage,
        settings=settings,
    )

    response = service.response_for_accepted(
        SemiAutomaticCalibrationAcceptRequest(
            video_id="video-auto-test",
            source="corrected",
            image_points=ManualImageKeypoints(
                top_left=(0, 0),
                top_right=(100, 0),
                bottom_right=(100, 200),
                bottom_left=(0, 200),
            ),
        )
    )

    assert response.status == "accepted"
    assert response.calibration_id
    saved = service.calibration_service.get_calibration(response.calibration_id)
    assert saved is not None
    assert saved.method == "semi-automatic"


def test_automatic_calibration_service_uses_injected_segmenter(tmp_path):
    video_path = tmp_path / "input.avi"
    make_test_video(video_path)
    settings = Settings(
        uploads_dir=tmp_path / "uploads",
        outputs_dir=tmp_path / "outputs",
        calibrations_dir=tmp_path / "calibrations",
        tmp_dir=tmp_path / "tmp",
        court_line_model_path="fake-model.pt",
        court_line_confidence=0.2,
        court_line_geometry_min_area_ratio=0.01,
    )
    storage = StorageService(settings)
    video_service = VideoService(storage)
    metadata = video_service.get_video("missing")
    assert metadata is None
    from app.schemas.video import VideoMetadata

    video_service.storage.write_json(
        video_service.storage.video_metadata_path("video-synthetic"),
        VideoMetadata(
            id="video-synthetic",
            original_filename="input.avi",
            content_type="video/avi",
            size_bytes=video_path.stat().st_size,
            path=str(video_path),
            uploaded_at="2026-05-17T00:00:00Z",
        ).model_dump(mode="json"),
    )
    service = AutomaticCalibrationService(
        video_service=video_service,
        calibration_service=CalibrationService(storage),
        storage=storage,
        settings=settings,
        segmenter=SyntheticSegmenter(),
    )

    response = service.suggest(AutomaticCalibrationRequest(video_id="video-synthetic"))

    assert response.status == "available"
    assert response.keypoints is not None
    assert response.preview_image_url


class SyntheticSegmenter:
    configured = True

    def segment(self, frame):
        mask = np.zeros(frame.shape[:2], dtype=np.uint8)
        height, width = mask.shape
        left = int(width * 0.2)
        right = int(width * 0.8)
        top = int(height * 0.18)
        bottom = int(height * 0.82)
        mask[top : top + 5, left:right] = 255
        mask[bottom : bottom + 5, left:right] = 255
        mask[top:bottom, left : left + 5] = 255
        mask[top:bottom, right : right + 5] = 255
        return CourtLineSegmentationResult(mask=mask, confidence=0.9, model_path="fake-model.pt")


def make_test_video(path):
    import cv2

    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    writer = cv2.VideoWriter(str(path), fourcc, 10, (96, 96))
    for _index in range(3):
        frame = np.full((96, 96, 3), 80, dtype=np.uint8)
        writer.write(frame)
    writer.release()
