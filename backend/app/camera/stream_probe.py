"""摄像头流探测 —— 使用 OpenCV VideoCapture 测试摄像头是否在线。"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from app.camera.models import ProbeResult


async def probe_camera(camera_id: str, stream_url: str, username: str | None = None, password: str | None = None, timeout_seconds: float = 10.0) -> ProbeResult:
    """尝试连接摄像头流，返回在线状态 + 分辨率 + 延迟。"""
    import asyncio

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _probe_sync, camera_id, stream_url, username, password, timeout_seconds)


def _probe_sync(camera_id: str, stream_url: str, username: str | None, password: str | None, timeout_seconds: float) -> ProbeResult:
    import cv2

    url = stream_url
    if username and password:
        parsed = url.split("://", 1)
        if len(parsed) == 2:
            url = f"{parsed[0]}://{username}:{password}@{parsed[1]}"

    started_at = time.monotonic()

    cap = cv2.VideoCapture(url)
    try:
        if not cap.isOpened():
            return ProbeResult(
                camera_id=camera_id,
                online=False,
                detected_at=datetime.now(timezone.utc),
                error_message="cv2.VideoCapture could not open stream URL",
            )

        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, int(timeout_seconds * 1000))

        ret, frame = cap.read()
        latency_ms = int((time.monotonic() - started_at) * 1000)

        if not ret or frame is None:
            return ProbeResult(
                camera_id=camera_id,
                online=False,
                latency_ms=latency_ms,
                detected_at=datetime.now(timezone.utc),
                error_message="Stream opened but no frame could be read within timeout",
            )

        h, w = frame.shape[:2]
        return ProbeResult(
            camera_id=camera_id,
            online=True,
            latency_ms=latency_ms,
            resolution=f"{w}x{h}",
            detected_at=datetime.now(timezone.utc),
        )
    except Exception as exc:
        return ProbeResult(
            camera_id=camera_id,
            online=False,
            detected_at=datetime.now(timezone.utc),
            error_message=str(exc),
        )
    finally:
        cap.release()
