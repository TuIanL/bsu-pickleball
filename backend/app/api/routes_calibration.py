"""
球场标定接口路由

【什么是"标定"？】
标定就是把"视频画面里的像素坐标"映射到"真实球场的尺寸坐标"。
只有完成标定，系统才知道球员在球场上的真实位置（以米为单位），
而不是仅仅知道他在屏幕上的像素位置。后续的速度、距离等指标都依赖它。

本文件提供两套路由：
1. manual_router（前缀 /calibration）：给前端"标定工作台"用的完整流程接口，
   包括手工四角标定、自动/半自动标定建议、预览图等。
2. router（前缀 /api/calibrations）：早期的基础标定接口（创建 / 读取 / 投影）。

三种标定方式：
- 手工标定：用户在画面上手动点出球场四个角 → 后端计算"单应性矩阵"（投影关系）
- 自动标定：用场地边线检测模型自动找出角点，给出"建议"
- 半自动标定：用户在自动建议基础上手动微调，再确认保存
"""

# 让 list[str] 这类类型注解在较旧的 Python 版本也能使用
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

# 标定相关的数据模型（Schema，规定请求/响应的字段与类型）
from app.schemas.calibration import (
    CalibrationCreate,                      # 基础"创建标定"的请求
    CalibrationPreviewRequest,              # 生成预览图的请求（可选携带某一帧画面）
    CalibrationPreviewResponse,             # 预览图的结果
    CalibrationReadResponse,                # 读取标定的响应
    CalibrationResult,                      # 标定结果
    AutomaticCalibrationRequest,            # 请求生成"自动标定建议"
    AutomaticCalibrationResponse,           # 自动标定建议的结果
    ManualCalibrationResponse,              # 手工标定的响应
    ManualKeypointCalibrationRequest,       # 手工四角点标定的请求（含四个角点的像素坐标）
    ProjectionRequest,                      # 投影请求（输入图像坐标，求球场坐标）
    ProjectionResult,                       # 投影结果
    SemiAutomaticCalibrationAcceptRequest,  # 半自动：接受或微调后的角点
)
# 自动标定服务：负责生成建议、保存半自动结果
from app.services.automatic_calibration_service import automatic_calibration_service
# 标定核心服务：计算单应性矩阵、保存标定、生成预览图
from app.services.calibration_service import calibration_service
# 存储服务：负责拼出各类文件在磁盘上的路径
from app.services.storage_service import StorageService
# 单应性矩阵计算可能抛出的错误（例如四个角点给得不对、近似共线时无法求解）
from app.vision.courtvision_calibration_engine.homography import HomographyError

# 基础标定路由：/api/calibrations
router = APIRouter(prefix="/api/calibrations", tags=["calibrations"])
# 标定工作台路由：/calibration（前端主流程使用）
manual_router = APIRouter(prefix="/calibration", tags=["calibration"])
# 一个存储服务对象，用于拼出预览图等文件的磁盘路径
_storage = StorageService()


# ---------- 标定工作台接口（manual_router，前缀 /calibration） ----------

@manual_router.post("/manual", response_model=ManualCalibrationResponse)
def create_manual_calibration(payload: ManualKeypointCalibrationRequest) -> ManualCalibrationResponse:
    """
    创建四角手工标定

    前端把用户点选的球场四个角点（图像像素坐标）发过来，
    后端计算单应性矩阵并保存，返回标定详情。
    """
    try:
        # 调用标定服务，根据四个角点创建标定
        calibration = calibration_service.create_manual_calibration(payload)
        # 把内部数据转换成给前端看的响应格式
        return calibration_service.manual_response(calibration)
    except HomographyError as exc:
        # 角点无法算出有效投影（如四点几乎共线）时，返回 HTTP 400
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@manual_router.post("/automatic", response_model=AutomaticCalibrationResponse)
def suggest_automatic_calibration(payload: AutomaticCalibrationRequest) -> AutomaticCalibrationResponse:
    """
    基于场地边线模型生成半自动标定建议

    后端用场地线检测模型，从视频帧里自动找出球场边界，
    推导出四个角点作为"建议"返回给前端，供用户确认或微调。
    """
    return automatic_calibration_service.suggest(payload)


@manual_router.post("/automatic/accept", response_model=AutomaticCalibrationResponse)
def accept_automatic_calibration(payload: SemiAutomaticCalibrationAcceptRequest) -> AutomaticCalibrationResponse:
    """
    接受自动建议或修正后的角点，并存储为半自动标定

    用户在自动建议基础上微调后点击"确认"，后端据此生成正式标定并保存。
    """
    try:
        return automatic_calibration_service.response_for_accepted(payload)
    except HomographyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@manual_router.get("/automatic/previews/{suggestion_id}")
def read_automatic_calibration_preview(suggestion_id: str) -> FileResponse:
    """
    读取自动标定预览图

    返回一张标注了检测到的场地线的图片，方便前端展示给用户查看效果。
    """
    # 拼出该"建议"对应的预览图磁盘路径
    path = _storage.automatic_calibration_preview_path(suggestion_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Automatic calibration preview not found")
    # 以图片形式返回（PNG）
    return FileResponse(path, media_type="image/png", filename=f"{suggestion_id}.png")


@manual_router.get("/{calibration_id}", response_model=CalibrationReadResponse)
def read_manual_calibration(calibration_id: str) -> CalibrationReadResponse:
    """
    读取标定详情

    根据标定 id 返回已保存的标定信息（含角点、单应性参数等）。
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

    在视频某一帧上叠加画出标定出的球场线/区域，生成一张预览图返回。
    可选携带 frame_path 指定用哪一帧画面作为底图（不传则用默认帧）。
    """
    try:
        preview = calibration_service.create_preview(
            calibration_id,
            # 如果前端带了 payload 且里面有 frame_path，就传给服务层；否则传 None
            frame_path=payload.frame_path if payload else None,
        )
    except ValueError as exc:
        # 参数不对（例如指定的帧不存在）返回 HTTP 400
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if preview is None:
        raise HTTPException(status_code=404, detail="Calibration not found")
    return preview


# ---------- 基础标定接口（router，前缀 /api/calibrations） ----------

@router.post("", response_model=CalibrationResult)
def create_calibration(payload: CalibrationCreate) -> CalibrationResult:
    """
    创建标定（基础接口）

    与上面的手工标定类似，但走早期约定的 /api/calibrations 路径。
    """
    try:
        return calibration_service.create_calibration(payload)
    except HomographyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{calibration_id}", response_model=CalibrationResult)
def read_calibration(calibration_id: str) -> CalibrationResult:
    """
    读取标定详情（基础接口）
    """
    calibration = calibration_service.get_calibration(calibration_id)
    if calibration is None:
        raise HTTPException(status_code=404, detail="Calibration not found")
    return calibration


@router.post("/project", response_model=ProjectionResult)
def project_image_point(payload: ProjectionRequest) -> ProjectionResult:
    """
    将图像坐标点投影到实际球场坐标

    输入画面上的某个像素坐标，利用标定得到的单应性矩阵，
    换算成真实球场里的位置（单位通常是米）。这是后续所有运动指标计算的基础。
    """
    projection = calibration_service.project(payload.calibration_id, payload.image_point)
    if projection is None:
        raise HTTPException(status_code=404, detail="Calibration not found")
    return projection
