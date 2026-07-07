"""
摄像头流探测 —— 使用 OpenCV 的 VideoCapture 测试摄像头是否在线。

"探测"就是尝试连上摄像头视频流、读一帧画面，从而判断：
- 摄像头是否在线（online）
- 分辨率是多少
- 连上并读到第一帧花了多少毫秒（延迟）
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from app.camera.models import ProbeResult


# 异步包装函数：对外提供 async 接口，内部把耗时的同步操作丢到线程池执行，避免阻塞事件循环
async def probe_camera(camera_id: str, stream_url: str, username: str | None = None, password: str | None = None, timeout_seconds: float = 10.0) -> ProbeResult:
    """尝试连接摄像头流，返回在线状态 + 分辨率 + 延迟。"""
    import asyncio

    loop = asyncio.get_running_loop()
    # run_in_executor 把同步的 _probe_sync 放到默认线程池里跑，不阻塞主线程
    return await loop.run_in_executor(None, _probe_sync, camera_id, stream_url, username, password, timeout_seconds)


# 真正干活的同步函数（在线程里执行）
def _probe_sync(camera_id: str, stream_url: str, username: str | None, password: str | None, timeout_seconds: float) -> ProbeResult:
    import cv2

    url = stream_url
    # 如果提供了账号密码，把它们拼进 URL（如 rtsp://user:pass@host/...）
    if username and password:
        parsed = url.split("://", 1)
        if len(parsed) == 2:
            url = f"{parsed[0]}://{username}:{password}@{parsed[1]}"

    # 记录开始时间，用于计算延迟
    started_at = time.monotonic()

    cap = cv2.VideoCapture(url)
    try:
        # 打不开流（地址错 / 网络不通）
        if not cap.isOpened():
            return ProbeResult(
                camera_id=camera_id,
                online=False,
                detected_at=datetime.now(timezone.utc),
                error_message="cv2.VideoCapture could not open stream URL",
            )

        # 设置打开超时（毫秒）
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, int(timeout_seconds * 1000))

        # 尝试读一帧
        ret, frame = cap.read()
        latency_ms = int((time.monotonic() - started_at) * 1000)

        # 读不到画面（流打开但没数据，可能超时）
        if not ret or frame is None:
            return ProbeResult(
                camera_id=camera_id,
                online=False,
                latency_ms=latency_ms,
                detected_at=datetime.now(timezone.utc),
                error_message="Stream opened but no frame could be read within timeout",
            )

        # 成功读到画面：取高、宽得到分辨率
        h, w = frame.shape[:2]
        return ProbeResult(
            camera_id=camera_id,
            online=True,
            latency_ms=latency_ms,
            resolution=f"{w}x{h}",
            detected_at=datetime.now(timezone.utc),
        )
    except Exception as exc:
        # 任何异常都当作"不在线"，并记录错误
        return ProbeResult(
            camera_id=camera_id,
            online=False,
            detected_at=datetime.now(timezone.utc),
            error_message=str(exc),
        )
    finally:
        # 无论成功失败，都释放摄像头资源
        cap.release()
