"""摄像头管理 API 路由。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.camera.camera_registry import camera_registry
from app.camera.models import CameraCreateRequest, CameraDeleteResponse, CameraInfo, ProbeResult
from app.camera.stream_probe import probe_camera

router = APIRouter(prefix="/api/cameras", tags=["cameras"])


def _sanitize(camera: CameraInfo) -> CameraInfo:
    data = camera.model_dump()
    if data.get("password"):
        data["password"] = "***"
    return CameraInfo.model_validate(data)


@router.get("", response_model=list[CameraInfo])
def list_cameras() -> list[CameraInfo]:
    return [_sanitize(c) for c in camera_registry.list_all()]


@router.post("", response_model=CameraInfo, status_code=201)
def create_camera(payload: CameraCreateRequest) -> CameraInfo:
    if camera_registry.exists(payload.camera_id):
        raise HTTPException(status_code=409, detail=f"摄像头 {payload.camera_id} 已存在，请先删除再重新注册")
    camera = camera_registry.create(
        camera_id=payload.camera_id,
        name=payload.name,
        stream_url=payload.stream_url,
        protocol=payload.protocol,
        username=payload.username,
        password=payload.password,
    )
    return _sanitize(camera)


@router.delete("/{camera_id}", response_model=CameraDeleteResponse)
def delete_camera(camera_id: str) -> CameraDeleteResponse:
    from app.camera.session_service import session_service

    active = session_service.find_active_session(camera_id)
    if active is not None:
        raise HTTPException(status_code=409, detail=f"摄像头 {camera_id} 正在录制中，无法删除")
    if not camera_registry.delete(camera_id):
        raise HTTPException(status_code=404, detail=f"摄像头 {camera_id} 不存在")
    return CameraDeleteResponse(deleted=True)


@router.post("/{camera_id}/probe", response_model=ProbeResult)
async def probe_camera_endpoint(camera_id: str) -> ProbeResult:
    camera = camera_registry.get(camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail=f"摄像头 {camera_id} 不存在")
    return await probe_camera(
        camera_id=camera_id,
        stream_url=camera.stream_url,
        username=camera.username,
        password=camera.password,
    )
