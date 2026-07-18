"""
摄像头管理接口路由（/api/cameras）

本文件负责"摄像头设备"的登记、查询、删除、连接探测和实时预览。
摄像头登记之后，才能用录制接口（见 routes_recording.py）对它进行录制。

安全提示：摄像头密码属于敏感信息，所以返回给前端之前会做"脱敏"处理，
也就是把真实密码替换成 ***，避免明文密码泄露到浏览器里。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from starlette.responses import StreamingResponse

# 摄像头登记中心：负责在内存/文件里维护一份"已登记摄像头"的清单
from app.camera.camera_registry import VIRTUAL_CAMERA_ID, camera_registry
# 摄像头相关的数据模型（请求/响应格式）
from app.camera.models import CameraCreateRequest, CameraDeleteResponse, CameraInfo, CameraUpdateRequest, ProbeResult
# 预览服务：将摄像头流转换为 MJPEG over HTTP
from app.camera.preview_service import preview_frames
# 连接探测工具：尝试连上摄像头，返回能否播放、分辨率、帧率等信息
from app.camera.stream_probe import probe_camera

# 创建路由表，前缀 /api/cameras 表示本文件所有接口都以它开头
router = APIRouter(prefix="/api/cameras", tags=["cameras"])


def _sanitize(camera: CameraInfo) -> CameraInfo:
    """
    脱敏处理：把摄像头密码替换成 *** 再返回给前端。

    原因：密码是敏感信息，列表/详情接口不应把明文密码透传给浏览器。
    """
    # 先把模型对象转成普通字典
    data = camera.model_dump()
    # 如果存在 password 字段，就把它替换成星号
    if data.get("password"):
        data["password"] = "***"
    # 用脱敏后的数据重新构建 CameraInfo 对象并返回
    return CameraInfo.model_validate(data)


@router.get("", response_model=list[CameraInfo])
def list_cameras() -> list[CameraInfo]:
    """
    列出所有已登记的摄像头

    每个摄像头都会先经过 _sanitize 脱敏，避免泄露密码。
    """
    # 用列表推导式：对登记中心里的每一个摄像头都做脱敏，再组成列表返回
    return [_sanitize(c) for c in camera_registry.list_all()]


@router.post("", response_model=CameraInfo, status_code=201)
def create_camera(payload: CameraCreateRequest) -> CameraInfo:
    """
    登记一个新摄像头

    如果同名（同 camera_id）的摄像头已经存在，返回 409（冲突），
    要求用户先删除旧的再重新注册。
    """
    if payload.camera_id == VIRTUAL_CAMERA_ID or camera_registry.exists(payload.camera_id):
        raise HTTPException(status_code=409, detail=f"摄像头 {payload.camera_id} 已存在，请先删除再重新注册")
    # 把摄像头信息写入登记中心
    camera = camera_registry.create(
        camera_id=payload.camera_id,
        name=payload.name,
        stream_url=payload.stream_url,
        protocol=payload.protocol,
        username=payload.username,
        password=payload.password,
    )
    # 返回时同样脱敏
    return _sanitize(camera)


@router.patch("/{camera_id}", response_model=CameraInfo)
def update_camera(camera_id: str, payload: CameraUpdateRequest) -> CameraInfo:
    """修改摄像头 ID 和显示名称。"""
    if camera_id == VIRTUAL_CAMERA_ID:
        raise HTTPException(status_code=409, detail="虚拟测试摄像头不可修改")
    from app.camera.session_service import session_service
    from app.camera.sync_recorder_service import sync_recording_service

    camera = camera_registry.get(camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail=f"摄像头 {camera_id} 不存在")
    if not payload.camera_id.strip() or not payload.name.strip():
        raise HTTPException(status_code=422, detail="摄像头 ID 和名称不能为空")
    if payload.camera_id != camera_id and camera_registry.exists(payload.camera_id):
        raise HTTPException(status_code=409, detail=f"摄像头 {payload.camera_id} 已存在")
    if session_service.find_active_session(camera_id) is not None or sync_recording_service.is_camera_in_sync_recording(camera_id):
        raise HTTPException(status_code=409, detail=f"摄像头 {camera_id} 正在录制中，无法修改")

    updated = camera_registry.update(camera_id, payload.camera_id.strip(), payload.name.strip())
    if updated is None:
        raise HTTPException(status_code=404, detail=f"摄像头 {camera_id} 不存在")
    return _sanitize(updated)


@router.delete("/{camera_id}", response_model=CameraDeleteResponse)
def delete_camera(camera_id: str) -> CameraDeleteResponse:
    """
    删除一个摄像头

    如果该摄像头正在录制（有进行中的录制会话），则不允许删除，返回 409，
    避免打断正在进行的录制。
    """
    if camera_id == VIRTUAL_CAMERA_ID:
        raise HTTPException(status_code=409, detail="虚拟测试摄像头不可删除")

    # 延迟导入：只在真正需要时才加载会话服务。
    # 这样写可以避开"模块 A 导入 B、B 又导入 A"造成的循环导入问题。
    from app.camera.session_service import session_service
    from app.camera.sync_recorder_service import sync_recording_service

    # 检查是否有正在进行的单摄录制会话
    active = session_service.find_active_session(camera_id)
    if active is not None:
        raise HTTPException(status_code=409, detail=f"摄像头 {camera_id} 正在录制中，无法删除")

    # 检查是否正在参与双摄同步录制
    if sync_recording_service.is_camera_in_sync_recording(camera_id):
        raise HTTPException(status_code=409, detail=f"摄像头 {camera_id} 正在参与双摄同步录制中，无法删除")
    # 执行删除；登记中心返回 True 表示删除成功
    if not camera_registry.delete(camera_id):
        raise HTTPException(status_code=404, detail=f"摄像头 {camera_id} 不存在")
    return CameraDeleteResponse(deleted=True)


@router.post("/{camera_id}/probe", response_model=ProbeResult)
async def probe_camera_endpoint(camera_id: str) -> ProbeResult:
    """
    探测摄像头连接

    尝试连接该摄像头的视频流，返回是否可用、分辨率、帧率等信息，
    帮助用户确认登记的地址/账号是否正确（相当于"测试连接"按钮）。
    """
    camera = camera_registry.get(camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail=f"摄像头 {camera_id} 不存在")
    # 调用探测工具，把连接所需参数传给它
    return await probe_camera(
        camera_id=camera_id,
        stream_url=camera.stream_url,
        username=camera.username,
        password=camera.password,
    )


@router.get("/{camera_id}/preview")
def preview_stream(camera_id: str):
    """
    摄像头实时预览（MJPEG over HTTP）

    返回 multipart/x-mixed-replace 响应，持续输出 JPEG 帧。
    浏览器可用 <img src="..."> 直接展示预览画面。

    行为：
    - 摄像头不存在 → 404
    - 摄像头无法打开或读帧失败 → 502（标明预览不可用）
    - 客户端断开连接 → 停止帧循环并释放 VideoCapture
    """
    camera = camera_registry.get(camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail=f"摄像头 {camera_id} 不存在")

    def generate():
        try:
            for jpeg_bytes in preview_frames(
                stream_url=camera.stream_url,
                protocol=camera.protocol,
                username=camera.username,
                password=camera.password,
            ):
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(jpeg_bytes)).encode() + b"\r\n"
                    b"\r\n"
                    + jpeg_bytes
                    + b"\r\n"
                )
        except RuntimeError as exc:
            # 流不可达或读帧失败：记录错误信息
            raise HTTPException(
                status_code=502,
                detail=f"摄像头 {camera_id} 预览不可用: {exc}",
            )

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
