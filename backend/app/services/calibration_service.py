from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.schemas.calibration import CalibrationCreate, CalibrationResult, HomographyMatrix, ImagePoint, ProjectionResult
from app.services.storage_service import StorageService
from app.vision.courtvision_calibration_engine.homography import compute_homography, project_point


CALIBRATIONS: dict[str, CalibrationResult] = {}


class CalibrationService:
    """Stores manual court calibration payloads and homography matrices."""

    def __init__(self, storage: StorageService | None = None) -> None:
        self.storage = storage or StorageService()

    def create_calibration(self, payload: CalibrationCreate) -> CalibrationResult:
        image_points = [(item.image.x, item.image.y) for item in payload.keypoints]
        court_points = [(item.court.x, item.court.y) for item in payload.keypoints]
        matrix = compute_homography(image_points, court_points)
        calibration_id = f"calib-{uuid4().hex[:10]}"
        result = CalibrationResult(
            id=calibration_id,
            video_id=payload.video_id,
            keypoints=payload.keypoints,
            homography=HomographyMatrix(values=matrix.tolist()),
            method=payload.method,
            created_at=datetime.now(timezone.utc),
        )
        CALIBRATIONS[calibration_id] = result
        self.storage.write_json(
            self.storage.calibration_json_path(calibration_id),
            result.model_dump(mode="json"),
        )
        return result

    def get_calibration(self, calibration_id: str) -> CalibrationResult | None:
        cached = CALIBRATIONS.get(calibration_id)
        if cached is not None:
            return cached

        path = self.storage.calibration_json_path(calibration_id)
        if not path.exists():
            return None

        result = CalibrationResult.model_validate(self.storage.read_json(path))
        CALIBRATIONS[calibration_id] = result
        return result

    def project(self, calibration_id: str, image_point: ImagePoint) -> ProjectionResult | None:
        calibration = self.get_calibration(calibration_id)
        if calibration is None:
            return None

        x, y = project_point(calibration.homography.values, (image_point.x, image_point.y))
        return ProjectionResult(
            calibration_id=calibration_id,
            image_point=image_point,
            court_point={"x": x, "y": y},
        )


calibration_service = CalibrationService()
