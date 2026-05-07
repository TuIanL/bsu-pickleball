from __future__ import annotations

from app.schemas.calibration import CalibrationCreate, CalibrationResult
from app.services.calibration_service import CalibrationService


class ManualKeypointCalibrator:
    """Thin engine wrapper around manual keypoint calibration storage."""

    def __init__(self, service: CalibrationService | None = None) -> None:
        self.service = service or CalibrationService()

    def calibrate(self, payload: CalibrationCreate) -> CalibrationResult:
        return self.service.create_calibration(payload)
