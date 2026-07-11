"""
FFmpeg 子进程录制器 —— 负责从视频流（如 RTSP）拉流并写入 MP4 文件。

本模块不直接处理视频解码 / 编码，而是调用系统里的 FFmpeg 外部程序，
让它来完成"拉流 + 写文件"。我们用 Python 启动并管理这个 FFmpeg 进程。
"""

from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

from app.camera.recorder_exit import RecorderExit

logger = logging.getLogger(__name__)

# 回调类型：FFmpeg 进程退出时会被调用，参数为 RecorderExit
OnExitCallback = Callable[[RecorderExit], None]


class Recorder:
    """管理一个 FFmpeg 子进程，将视频流录制为 MP4 文件。"""

    def __init__(self) -> None:
        self._process: subprocess.Popen[bytes] | None = None
        self._monitor_thread: threading.Thread | None = None
        self._on_exit: OnExitCallback | None = None
        self._stop_requested: bool = False
        self._cancel_requested: bool = False
        # 用于 ffmpeg_registry 登记
        self.pid: int | None = None
        self.pgid: int | None = None
        self.command_fingerprint: str | None = None

    def start(
        self,
        stream_url: str,
        output_path: Path,
        username: str | None = None,
        password: str | None = None,
        fps: int = 60,
        resolution: str = "1920x1080",
        on_exit: OnExitCallback | None = None,
    ) -> None:
        # 已有进程在跑则报错（一个 Recorder 同时只录一路）
        if self._process is not None and self._process.poll() is None:
            raise RuntimeError("录制进程已在运行")
        if self._process is not None:
            self._process = None

        # 确保输出文件的上级目录存在
        output_path.parent.mkdir(parents=True, exist_ok=True)

        url = stream_url
        # 带账号密码时拼进 URL
        if username and password:
            parsed = url.split("://", 1)
            if len(parsed) == 2:
                url = f"{parsed[0]}://{username}:{password}@{parsed[1]}"

        # 组装 FFmpeg 命令行参数。
        # 单摄训练素材优先保留摄像头原始码流：重新编码 1080p/高帧率很容易
        # 让本机 CPU 追不上，FFmpeg 随后用重复帧补齐恒定帧率，肉眼会看到
        # 周期性卡顿。这里不再强制 -r/-vsync，而是让摄像头自己决定真实帧率。
        cmd = [
            "ffmpeg",
            "-rtsp_transport", "tcp",          # RTSP 用 TCP 传输（比 UDP 更稳定）
            "-timeout", "5000000",             # RTSP 建连/读包超时 5 秒
            "-fflags", "+genpts",              # 输入时间戳不完整时生成连续 PTS
            "-i", url,                         # 输入：视频流地址
            "-map", "0:v:0",                   # 只录第一路视频
            "-an",                              # 不录音频
            "-c:v", "copy",                    # 不重编码，避免高帧率软件编码卡顿
            "-fps_mode", "passthrough",        # 保留输入帧时间戳，不补帧/丢帧
            "-movflags", "+faststart",         # MP4 moov atom 前置，支持快速打开
            "-y",                              # 输出文件已存在则覆盖
            str(output_path),                  # 输出文件路径
        ]

        logger.info("启动 FFmpeg 录制: %s", " ".join(cmd))

        self._stop_requested = False
        self._cancel_requested = False
        self._on_exit = on_exit

        cmd_fingerprint = " ".join(cmd)
        self._process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        self.pid = self._process.pid
        self.pgid = os.getpgid(self._process.pid) if self._process.pid else None
        self.command_fingerprint = hashlib.sha256(cmd_fingerprint.encode()).hexdigest()[:16]

        self._monitor_thread = threading.Thread(
            target=self._monitor,
            args=(self._process, on_exit),
            daemon=True,
        )
        self._monitor_thread.start()

    def _monitor(self, process: subprocess.Popen[bytes], on_exit: OnExitCallback | None) -> None:
        returncode = process.wait()
        logger.info("FFmpeg 进程退出, returncode=%d", returncode)
        self._update_ffmpeg_registry_ended()
        if on_exit:
            exit_info = RecorderExit(
                returncode=returncode,
                stop_requested=self._stop_requested,
                cancel_requested=self._cancel_requested,
            )
            on_exit(exit_info)
        if self._process is process:
            self._process = None
            self._monitor_thread = None
            self._on_exit = None
            self.pid = None
            self.pgid = None

    def stop(self, timeout_seconds: float = 30.0) -> None:
        self._stop_requested = True
        if self._process is None or self._process.poll() is not None:
            return

        logger.info("正在停止 FFmpeg 录制进程...")
        try:
            # 向 FFmpeg 标准输入写入 'q'，让它优雅停止并写结尾
            self._process.stdin.write(b"q")
            self._process.stdin.flush()
        except Exception:
            pass

        try:
            # 等待进程优雅退出
            self._process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            # 超时还没退，强制杀掉
            logger.warning("FFmpeg 进程未在 %s 秒内退出，强制终止", timeout_seconds)
            self._process.kill()
            self._process.wait()
        finally:
            if self._process is not None and self._process.poll() is not None:
                self._process = None

    def cancel(self) -> None:
        self._cancel_requested = True
        if self._process is None or self._process.poll() is not None:
            self._process = None
            return

        logger.info("正在取消 FFmpeg 录制进程...")
        self._process.kill()
        self._process.wait()
        self._process = None

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def _insert_ffmpeg_registry(self, capture_take_id: str = "", track_id: str = "") -> None:
        if not self.pid or not self.pgid:
            return
        try:
            from app.database import get_session_factory
            from app.models.ffmpeg_registry import FFmpegProcessRegistry
            from datetime import datetime, timezone as tz
            db = get_session_factory()()
            try:
                rec = FFmpegProcessRegistry(
                    capture_take_id=capture_take_id, track_id=track_id,
                    pid=self.pid, pgid=self.pgid,
                    command_fingerprint=self.command_fingerprint or "",
                    output_path="", started_at=datetime.now(tz.utc),
                )
                db.add(rec)
                db.commit()
            except Exception:
                db.rollback()
            finally:
                db.close()
        except Exception:
            pass

    def _update_ffmpeg_registry_ended(self) -> None:
        if not self.pid:
            return
        try:
            from datetime import datetime, timezone as tz
            from app.database import get_session_factory
            from app.models.ffmpeg_registry import FFmpegProcessRegistry
            db = get_session_factory()()
            try:
                db.query(FFmpegProcessRegistry).filter(
                    FFmpegProcessRegistry.pid == self.pid,
                    FFmpegProcessRegistry.ended_at.is_(None),
                ).update({"ended_at": datetime.now(tz.utc)})
                db.commit()
            except Exception:
                db.rollback()
            finally:
                db.close()
        except Exception:
            pass


# 检查系统是否安装了 FFmpeg（能运行 `ffmpeg -version` 即视为可用）
def check_ffmpeg_available() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        return True
    except Exception:
        return False
