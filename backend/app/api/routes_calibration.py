from fastapi import APIRouter, HTTPException

# 导入标定相关的模式（Schemas）
from app.schemas.calibration import CalibrationCreate, CalibrationResult, ProjectionRequest, ProjectionResult
# 导入标定服务
from app.services.calibration_service import calibration_service
# 导入单应性矩阵错误处理
from app.vision.courtvision_calibration_engine.homography import HomographyError

# 定义 API 路由，前缀为 /api/calibrations，标签为 calibrations
router = APIRouter(prefix="/api/calibrations", tags=["calibrations"])


@router.post("", response_model=CalibrationResult)
def create_calibration(payload: CalibrationCreate) -> CalibrationResult:
    """
    创建标定
    """
    try:
        return calibration_service.create_calibration(payload)
    except HomographyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{calibration_id}", response_model=CalibrationResult)
def read_calibration(calibration_id: str) -> CalibrationResult:
    """
    读取标定详情
    """
    calibration = calibration_service.get_calibration(calibration_id)
    if calibration is None:
        raise HTTPException(status_code=404, detail="Calibration not found")
    return calibration


@router.post("/project", response_model=ProjectionResult)
def project_image_point(payload: ProjectionRequest) -> ProjectionResult:
    """
    将图像坐标点投影到实际坐标（球场坐标）
    """
    projection = calibration_service.project(payload.calibration_id, payload.image_point)
    if projection is None:
        raise HTTPException(status_code=404, detail="Calibration not found")
    return projection
