from __future__ import annotations

from app.schemas.calibration import CalibrationCreate, CalibrationResult, ManualKeypointCalibrationRequest
from app.services.calibration_service import CalibrationService


class ManualKeypointCalibrator:
    """Engine wrapper for manual court keypoint calibration."""

    def __init__(self, service: CalibrationService | None = None) -> None:
        self.service = service or CalibrationService()

    def calibrate(self, payload: ManualKeypointCalibrationRequest | CalibrationCreate) -> CalibrationResult:
        if isinstance(payload, ManualKeypointCalibrationRequest):
            return self.service.create_manual_calibration(payload)
        return self.service.create_calibration(payload)
