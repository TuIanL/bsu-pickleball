"""
FFmpeg 子进程录制器 —— 负责从视频流（如 RTSP）拉流并写入 MP4 文件。

本模块不直接处理视频解码 / 编码，而是调用系统里的 FFmpeg 外部程序，
让它来完成"拉流 + 写文件"。我们用 Python 启动并管理这个 FFmpeg 进程。
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

# 回调类型：FFmpeg 进程退出时会被调用，参数为退出码
OnExitCallback = Callable[[int], None]


class Recorder:
    """管理一个 FFmpeg 子进程，将视频流录制为 MP4 文件。"""

    def __init__(self) -> None:
        # 当前运行的 FFmpeg 进程对象（未运行时为 None）
        self._process: subprocess.Popen[bytes] | None = None
        # 监控线程：用来等待 FFmpeg 退出并触发回调
        self._monitor_thread: threading.Thread | None = None
        # 退出回调（由调用方传入）
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
        # 已有进程在跑则报错（一个 Recorder 同时只录一路）
        if self._process is not None:
            raise RuntimeError("录制进程已在运行")

        # 确保输出文件的上级目录存在
        output_path.parent.mkdir(parents=True, exist_ok=True)

        url = stream_url
        # 带账号密码时拼进 URL
        if username and password:
            parsed = url.split("://", 1)
            if len(parsed) == 2:
                url = f"{parsed[0]}://{username}:{password}@{parsed[1]}"

        # 组装 FFmpeg 命令行参数
        cmd = [
            "ffmpeg",
            "-rtsp_transport", "tcp",          # RTSP 用 TCP 传输（比 UDP 更稳定）
            "-reconnect", "1",                 # 开启断线重连
            "-reconnect_at_eof", "1",          # 读到结尾时重连
            "-reconnect_streamed", "1",        # 流式内容也重连
            "-reconnect_delay_max", "30",      # 重连最大间隔 30 秒
            "-i", url,                         # 输入：视频流地址
            "-c:v", "copy",                    # 视频编码：直接拷贝（不重新编码，省 CPU）
            "-c:a", "aac",                     # 音频编码：AAC
            "-fps_mode", "cfr",                # 固定帧率模式
            "-r", str(fps),                    # 输出帧率
            "-s", resolution,                  # 输出分辨率
            "-y",                              # 输出文件已存在则覆盖
            str(output_path),                  # 输出文件路径
        ]

        logger.info("启动 FFmpeg 录制: %s", " ".join(cmd))

        self._on_exit = on_exit
        # 启动 FFmpeg 子进程
        self._process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,       # 保留标准输入（用于发 'q' 停止）
            stdout=subprocess.DEVNULL,   # 丢弃标准输出
            stderr=subprocess.PIPE,      # 保留标准错误（用于看日志 / 调试）
        )
        # 开一个后台线程监控进程退出
        self._monitor_thread = threading.Thread(target=self._monitor, daemon=True)
        self._monitor_thread.start()

    def _monitor(self) -> None:
        # 等待 FFmpeg 进程结束，拿到退出码，再调用回调
        if self._process is None:
            return
        returncode = self._process.wait()
        logger.info("FFmpeg 进程退出, returncode=%d", returncode)
        if self._on_exit:
            self._on_exit(returncode)

    def stop(self, timeout_seconds: float = 30.0) -> None:
        # 进程不存在或已经结束就直接返回
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

    def cancel(self) -> None:
        # 取消 = 直接杀掉进程（不保证文件完整，随后由调用方删除半成品）
        if self._process is None or self._process.poll() is not None:
            return

        logger.info("正在取消 FFmpeg 录制进程...")
        self._process.kill()
        self._process.wait()

    def is_running(self) -> bool:
        # 进程存在且还没结束，说明正在录制
        return self._process is not None and self._process.poll() is None


# 检查系统是否安装了 FFmpeg（能运行 `ffmpeg -version` 即视为可用）
def check_ffmpeg_available() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        return True
    except Exception:
        return False
