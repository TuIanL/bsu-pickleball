from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

# 导入标定相关的模式（Schemas）
from app.schemas.calibration import (
    CalibrationCreate,
    CalibrationPreviewRequest,
    CalibrationPreviewResponse,
    CalibrationReadResponse,
    CalibrationResult,
    AutomaticCalibrationRequest,
    AutomaticCalibrationResponse,
    ManualCalibrationResponse,
    ManualKeypointCalibrationRequest,
    ProjectionRequest,
    ProjectionResult,
    SemiAutomaticCalibrationAcceptRequest,
)
# 导入标定服务
from app.services.automatic_calibration_service import automatic_calibration_service
from app.services.calibration_service import calibration_service
from app.services.storage_service import StorageService
# 导入单应性矩阵错误处理
from app.vision.courtvision_calibration_engine.homography import HomographyError

# 定义 API 路由，前缀为 /api/calibrations，标签为 calibrations
router = APIRouter(prefix="/api/calibrations", tags=["calibrations"])
manual_router = APIRouter(prefix="/calibration", tags=["calibration"])
_storage = StorageService()


@manual_router.post("/manual", response_model=ManualCalibrationResponse)
def create_manual_calibration(payload: ManualKeypointCalibrationRequest) -> ManualCalibrationResponse:
    """
    创建四角手工标定
    """
    try:
        calibration = calibration_service.create_manual_calibration(payload)
        return calibration_service.manual_response(calibration)
    except HomographyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@manual_router.post("/automatic", response_model=AutomaticCalibrationResponse)
def suggest_automatic_calibration(payload: AutomaticCalibrationRequest) -> AutomaticCalibrationResponse:
    """
    基于场地边线模型生成半自动标定建议
    """
    return automatic_calibration_service.suggest(payload)


@manual_router.post("/automatic/accept", response_model=AutomaticCalibrationResponse)
def accept_automatic_calibration(payload: SemiAutomaticCalibrationAcceptRequest) -> AutomaticCalibrationResponse:
    """
    接受自动建议或修正后的角点，并存储为半自动标定
    """
    try:
        return automatic_calibration_service.response_for_accepted(payload)
    except HomographyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@manual_router.get("/automatic/previews/{suggestion_id}")
def read_automatic_calibration_preview(suggestion_id: str) -> FileResponse:
    """
    读取自动标定预览图
    """
    path = _storage.automatic_calibration_preview_path(suggestion_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Automatic calibration preview not found")
    return FileResponse(path, media_type="image/png", filename=f"{suggestion_id}.png")


@manual_router.get("/{calibration_id}", response_model=CalibrationReadResponse)
def read_manual_calibration(calibration_id: str) -> CalibrationReadResponse:
    """
    读取 CourtVision 标定详情
    """
    calibration = calibration_service.get_calibration(calibration_id)
    if calibration is None:
        raise HTTPException(status_code=404, detail="Calibration not found")
    return calibration_service.read_response(calibration)


@manual_router.post("/{calibration_id}/preview", response_model=CalibrationPreviewResponse)
def create_calibration_preview(
    calibration_id: str,
    payload: Optional[CalibrationPreviewRequest] = None,
) -> CalibrationPreviewResponse:
    """
    生成场地 overlay 预览图
    """
    try:
        preview = calibration_service.create_preview(
            calibration_id,
            frame_path=payload.frame_path if payload else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if preview is None:
        raise HTTPException(status_code=404, detail="Calibration not found")
    return preview


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
