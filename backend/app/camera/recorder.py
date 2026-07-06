"""FFmpeg 子进程录制器 —— 负责 RTSP 流的拉取和视频文件写入。"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

OnExitCallback = Callable[[int], None]


class Recorder:
    """管理一个 FFmpeg 子进程，将 RTSP 流录制为 MP4 文件。"""

    def __init__(self) -> None:
        self._process: subprocess.Popen[bytes] | None = None
        self._monitor_thread: threading.Thread | None = None
        self._on_exit: OnExitCallback | None = None

    def start(
        self,
        stream_url: str,
        output_path: Path,
        username: str | None = None,
        password: str | None = None,
        fps: int = 30,
        resolution: str = "1920x1080",
        on_exit: OnExitCallback | None = None,
    ) -> None:
        if self._process is not None:
            raise RuntimeError("录制进程已在运行")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        url = stream_url
        if username and password:
            parsed = url.split("://", 1)
            if len(parsed) == 2:
                url = f"{parsed[0]}://{username}:{password}@{parsed[1]}"

        cmd = [
            "ffmpeg",
            "-rtsp_transport", "tcp",
            "-reconnect", "1",
            "-reconnect_at_eof", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "30",
            "-i", url,
            "-c:v", "copy",
            "-c:a", "aac",
            "-fps_mode", "cfr",
            "-r", str(fps),
            "-s", resolution,
            "-y",
            str(output_path),
        ]

        logger.info("启动 FFmpeg 录制: %s", " ".join(cmd))

        self._on_exit = on_exit
        self._process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        self._monitor_thread = threading.Thread(target=self._monitor, daemon=True)
        self._monitor_thread.start()

    def _monitor(self) -> None:
        if self._process is None:
            return
        returncode = self._process.wait()
        logger.info("FFmpeg 进程退出, returncode=%d", returncode)
        if self._on_exit:
            self._on_exit(returncode)

    def stop(self, timeout_seconds: float = 30.0) -> None:
        if self._process is None or self._process.poll() is not None:
            return

        logger.info("正在停止 FFmpeg 录制进程...")
        try:
            self._process.stdin.write(b"q")
            self._process.stdin.flush()
        except Exception:
            pass

        try:
            self._process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            logger.warning("FFmpeg 进程未在 %s 秒内退出，强制终止", timeout_seconds)
            self._process.kill()
            self._process.wait()

    def cancel(self) -> None:
        if self._process is None or self._process.poll() is not None:
            return

        logger.info("正在取消 FFmpeg 录制进程...")
        self._process.kill()
        self._process.wait()

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None


def check_ffmpeg_available() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        return True
    except Exception:
        return False
