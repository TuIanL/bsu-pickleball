"""Showcase-only status and MJPEG endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from starlette.responses import StreamingResponse

from app.services.showcase_runtime import showcase_runtime_manager

router = APIRouter(prefix="/api/showcase-runtimes", tags=["showcase"])


@router.get("/{runtime_id}")
def get_showcase_status(runtime_id: str):
    runtime = showcase_runtime_manager.get(runtime_id)
    if runtime is None:
        raise HTTPException(status_code=404, detail="展示旁路不存在或已停止")
    return runtime.snapshot()


@router.get("/{runtime_id}/streams/{slot}")
def showcase_stream(runtime_id: str, slot: str):
    runtime = showcase_runtime_manager.get(runtime_id)
    if runtime is None:
        raise HTTPException(status_code=404, detail="展示旁路不存在或已停止")
    if slot not in {"cam_1", "cam_2"}:
        raise HTTPException(status_code=422, detail="机位必须是 cam_1 或 cam_2")
    frames = runtime.stream(slot)
    if frames is None:
        raise HTTPException(status_code=404, detail=f"{slot} 展示流不可用")

    def generate():
        for jpeg in frames:
            yield b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n"

    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")
