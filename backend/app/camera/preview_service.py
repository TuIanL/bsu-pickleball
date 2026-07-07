"""
摄像头实时预览服务（MJPEG over HTTP）

职责：
- 根据摄像头配置拼接鉴权 URL（支持 RTSP 的 username:password@host 格式）
- 通过 cv2.VideoCapture 打开摄像头流
- 按受控帧率读取帧并编码为 JPEG
- 生成 multipart/x-mixed-replace 响应，供浏览器 <img> 直接展示
- 客户端断开时释放 VideoCapture 资源

设计决策（见 design.md）：
- 每请求独立打开 VideoCapture，避免共享全局 capture 的复杂生命周期管理
- 限制帧率 5-10 FPS 以减少 CPU、网络和摄像头压力
- JPEG 编码固定质量，浏览器兼容性最好
"""

from __future__ import annotations

import time
from typing import Generator

import cv2

# 默认预览帧率（Hz）。5 FPS 足以确认角度和画面，同时降低资源占用。
DEFAULT_PREVIEW_FPS = 5.0

# JPEG 编码质量（0-100）。85 在清晰度和带宽之间取得平衡。
DEFAULT_JPEG_QUALITY = 85


def _build_auth_stream_url(
    stream_url: str,
    protocol: str,
    username: str | None = None,
    password: str | None = None,
) -> str:
    """
    拼接带鉴权的流地址。

    对于 RTSP 协议，标准鉴权格式为：
        rtsp://username:password@host:port/path

    如果已有用户名密码，则插入到协议和主机之间；
    如果原 URL 已包含鉴权信息，则直接使用原 URL。
    """
    if not username or not password:
        return stream_url

    # 如果 URL 已经包含 @，说明已有鉴权信息，直接使用
    if "@" in stream_url:
        return stream_url

    # 将 protocol:// 替换为 protocol://username:password@
    prefix = f"{protocol}://"
    if stream_url.startswith(prefix):
        rest = stream_url[len(prefix):]
        return f"{prefix}{username}:{password}@{rest}"

    return stream_url


def preview_frames(
    stream_url: str,
    protocol: str,
    username: str | None = None,
    password: str | None = None,
    fps: float = DEFAULT_PREVIEW_FPS,
    jpeg_quality: int = DEFAULT_JPEG_QUALITY,
) -> Generator[bytes, None, None]:
    """
    生成摄像头预览帧的生成器。

    参数：
        stream_url: 摄像头视频流地址
        protocol: 流协议（rtsp / rtmp / http）
        username: 登录用户名（可选）
        password: 登录密码（可选）
        fps: 预览帧率上限（Hz）
        jpeg_quality: JPEG 编码质量（0-100）

    Yields:
        JPEG 编码的帧字节

    用法：
        cap = None
        try:
            for jpeg_bytes in preview_frames(...):
                yield jpeg_bytes
        finally:
            if cap is not None:
                cap.release()
    """
    # 拼接鉴权 URL
    authed_url = _build_auth_stream_url(
        stream_url=stream_url,
        protocol=protocol,
        username=username,
        password=password,
    )

    cap = cv2.VideoCapture(authed_url)

    if not cap.isOpened():
        cap.release()
        raise RuntimeError(f"无法打开摄像头流: {stream_url}")

    frame_interval = 1.0 / max(fps, 0.1)  # 防止除零
    last_frame_time = 0.0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                # 读帧失败（流断开、摄像头离线等）
                raise RuntimeError("摄像头流读取失败，可能已断开连接")

            now = time.monotonic()
            elapsed = now - last_frame_time

            # 帧率控制：如果距离上一帧不到 frame_interval，跳过本帧
            if elapsed < frame_interval:
                # 短暂休眠避免忙等待
                time.sleep(0.001)
                continue

            last_frame_time = now

            # JPEG 编码
            success, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
            if not success:
                continue

            yield jpeg.tobytes()
    finally:
        cap.release()
