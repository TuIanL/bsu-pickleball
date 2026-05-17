from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import numpy as np

from app.schemas.calibration import (
    CalibrationCreate,
    CalibrationKeypoint,
    CalibrationPreviewResponse,
    CalibrationQuality,
    CalibrationReadResponse,
    CalibrationResult,
    CourtCoordinateSystem,
    CourtPoint2D,
    HomographyMatrix,
    ImagePoint,
    ManualCalibrationResponse,
    ManualKeypointCalibrationRequest,
    ProjectionResult,
)
from app.services.storage_service import StorageService
from app.services.video_service import video_service
from app.vision.courtvision_calibration_engine.court_geometry import PickleballCourtGeometry, standard_court
from app.vision.courtvision_calibration_engine.court_overlay import draw_court_overlay
from app.vision.courtvision_calibration_engine.homography import compute_homography, image_to_court, project_point


CALIBRATIONS: dict[str, CalibrationResult] = {}


class CalibrationService:
    """Stores manual court calibration payloads and homography matrices."""

    def __init__(self, storage: StorageService | None = None, court: PickleballCourtGeometry | None = None) -> None:
        self.storage = storage or StorageService()
        self.court = court or standard_court()

    def create_calibration(self, payload: CalibrationCreate) -> CalibrationResult:
        image_points = [(item.image.x, item.image.y) for item in payload.keypoints]
        court_points = [(item.court.x, item.court.y) for item in payload.keypoints]
        matrix = compute_homography(image_points, court_points)
        inverse_matrix = np.linalg.inv(matrix)
        quality = self._quality(image_points, court_points, matrix)
        calibration_id = f"calib-{uuid4().hex[:10]}"
        result = CalibrationResult(
            id=calibration_id,
            video_id=payload.video_id,
            keypoints=payload.keypoints,
            homography=HomographyMatrix(values=matrix.tolist()),
            inverse_homography=HomographyMatrix(values=inverse_matrix.tolist()),
            court_coordinate_system=CourtCoordinateSystem(**self.court.coordinate_system),
            quality=quality,
            method=payload.method,
            created_at=datetime.now(timezone.utc),
        )
        return self._save_calibration(result)

    def create_manual_calibration(self, payload: ManualKeypointCalibrationRequest) -> CalibrationResult:
        standard_keypoints = self.court.standard_keypoints
        keypoints: list[CalibrationKeypoint] = []

        for name, image_point in payload.image_points.as_named_points().items():
            court_point = standard_keypoints[name]
            keypoints.append(
                CalibrationKeypoint(
                    name=name,
                    image=ImagePoint(x=image_point[0], y=image_point[1]),
                    court=CourtPoint2D(x=court_point.x, y=court_point.y),
                )
            )

        return self.create_calibration(
            CalibrationCreate(
                video_id=payload.video_id,
                keypoints=keypoints,
                method="manual",
            )
        )

    def create_semi_automatic_calibration(self, payload: ManualKeypointCalibrationRequest) -> CalibrationResult:
        standard_keypoints = self.court.standard_keypoints
        keypoints: list[CalibrationKeypoint] = []

        for name, image_point in payload.image_points.as_named_points().items():
            court_point = standard_keypoints[name]
            keypoints.append(
                CalibrationKeypoint(
                    name=name,
                    image=ImagePoint(x=image_point[0], y=image_point[1]),
                    court=CourtPoint2D(x=court_point.x, y=court_point.y),
                )
            )

        return self.create_calibration(
            CalibrationCreate(
                video_id=payload.video_id,
                keypoints=keypoints,
                method="semi-automatic",
            )
        )

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

    def manual_response(self, calibration: CalibrationResult) -> ManualCalibrationResponse:
        inverse = calibration.inverse_homography
        if inverse is None:
            inverse = HomographyMatrix(values=np.linalg.inv(np.asarray(calibration.homography.values, dtype=float)).tolist())

        return ManualCalibrationResponse(
            calibration_id=calibration.id,
            homography=calibration.homography.values,
            inverse_homography=inverse.values,
            court_coordinate_system=calibration.court_coordinate_system,
            quality=calibration.quality,
        )

    def read_response(self, calibration: CalibrationResult) -> CalibrationReadResponse:
        response = self.manual_response(calibration)
        return CalibrationReadResponse(
            calibration_id=response.calibration_id,
            video_id=calibration.video_id,
            keypoints=calibration.keypoints,
            homography=response.homography,
            inverse_homography=response.inverse_homography,
            court_coordinate_system=response.court_coordinate_system,
            quality=response.quality,
            created_at=calibration.created_at,
        )

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

    def create_preview(self, calibration_id: str, frame_path: str | None = None) -> CalibrationPreviewResponse | None:
        calibration = self.get_calibration(calibration_id)
        if calibration is None:
            return None
        if calibration.inverse_homography is None:
            calibration.inverse_homography = HomographyMatrix(
                values=np.linalg.inv(np.asarray(calibration.homography.values, dtype=float)).tolist()
            )

        frame = self._read_preview_frame(calibration, frame_path)
        if frame is None:
            raise ValueError("No usable frame was provided or available for this calibration")

        output = draw_court_overlay(frame, calibration.inverse_homography.values, self.court)
        path = self.storage.preview_image_path(calibration_id)

        try:
            import cv2  # type: ignore
        except ImportError as exc:
            raise ValueError("OpenCV is required to generate calibration previews") from exc

        if not cv2.imwrite(str(path), output):
            raise ValueError("Failed to write calibration preview image")

        return CalibrationPreviewResponse(calibration_id=calibration_id, preview_image_path=str(path))

    def _save_calibration(self, result: CalibrationResult) -> CalibrationResult:
        CALIBRATIONS[result.id] = result
        self.storage.write_json(
            self.storage.calibration_json_path(result.id),
            result.model_dump(mode="json"),
        )
        return result

    def _quality(
        self,
        image_points: list[tuple[float, float]],
        court_points: list[tuple[float, float]],
        homography: np.ndarray,
    ) -> CalibrationQuality:
        projected = image_to_court(image_points, homography)
        projected_points = projected if isinstance(projected, list) else [projected]
        errors = [
            float(np.linalg.norm(np.asarray(projected_point, dtype=float) - np.asarray(court_point, dtype=float)))
            for projected_point, court_point in zip(projected_points, court_points)
        ]
        reprojection_error = float(np.mean(errors)) if errors else 0.0
        status = "ok" if reprojection_error <= 1.0 else "warning"
        return CalibrationQuality(reprojection_error=reprojection_error, status=status)

    def _read_preview_frame(self, calibration: CalibrationResult, frame_path: str | None):
        try:
            import cv2  # type: ignore
        except ImportError as exc:
            raise ValueError("OpenCV is required to generate calibration previews") from exc

        if frame_path:
            path = Path(frame_path)
            if not path.exists():
                raise ValueError("Provided frame_path does not exist")
            frame = cv2.imread(str(path))
            if frame is None:
                raise ValueError("Provided frame_path could not be read as an image")
            return frame

        if calibration.video_id:
            video = video_service.get_video(calibration.video_id)
            if video is not None and Path(video.path).exists():
                capture = cv2.VideoCapture(video.path)
                try:
                    ok, frame = capture.read()
                finally:
                    capture.release()
                if ok and frame is not None:
                    return frame

        return None


calibration_service = CalibrationService()
