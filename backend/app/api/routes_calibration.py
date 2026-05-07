from fastapi import APIRouter, HTTPException

from app.schemas.calibration import CalibrationCreate, CalibrationResult, ProjectionRequest, ProjectionResult
from app.services.calibration_service import calibration_service
from app.vision.courtvision_calibration_engine.homography import HomographyError

router = APIRouter(prefix="/api/calibrations", tags=["calibrations"])


@router.post("", response_model=CalibrationResult)
def create_calibration(payload: CalibrationCreate) -> CalibrationResult:
    try:
        return calibration_service.create_calibration(payload)
    except HomographyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{calibration_id}", response_model=CalibrationResult)
def read_calibration(calibration_id: str) -> CalibrationResult:
    calibration = calibration_service.get_calibration(calibration_id)
    if calibration is None:
        raise HTTPException(status_code=404, detail="Calibration not found")
    return calibration


@router.post("/project", response_model=ProjectionResult)
def project_image_point(payload: ProjectionRequest) -> ProjectionResult:
    projection = calibration_service.project(payload.calibration_id, payload.image_point)
    if projection is None:
        raise HTTPException(status_code=404, detail="Calibration not found")
    return projection
