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


def _build_video_filter(fps: int, resolution: str | None) -> str:
    safe_fps = max(1, min(int(fps or 30), 120))
    filters = [f"fps={safe_fps}"]
    if resolution and "x" in resolution:
        width, height = resolution.lower().split("x", 1)
        if width.isdigit() and height.isdigit():
            filters.append(f"scale={int(width)}:{int(height)}")
    filters.append("format=yuv420p")
    return ",".join(filters)


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
        # RTSP 摄像头的原始 H.264 包时间戳经常不适合浏览器直接回放；
        # 直接 -c:v copy 写 MP4 时容易出现播放几秒卡一下。这里重新生成时间戳，
        # 转成恒定帧率的 H.264 MP4，优先保证回放稳定。
        cmd = [
            "ffmpeg",
            "-rtsp_transport", "tcp",          # RTSP 用 TCP 传输（比 UDP 更稳定）
            "-timeout", "5000000",             # RTSP 建连/读包超时 5 秒，避免网络异常时长时间卡住
            "-fflags", "+genpts",              # 为时间戳异常的流生成连续 PTS
            "-use_wallclock_as_timestamps", "1",
            "-i", url,                         # 输入：视频流地址
            "-map", "0:v:0",                   # 只录第一路视频，避免音频时间戳拖慢浏览器回放
            "-an",
            "-vf", _build_video_filter(fps, resolution),
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-movflags", "+faststart",
            "-avoid_negative_ts", "make_zero",
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
        self._monitor_thread = threading.Thread(
            target=self._monitor,
            args=(self._process, on_exit),
            daemon=True,
        )
        self._monitor_thread.start()

    def _monitor(self, process: subprocess.Popen[bytes], on_exit: OnExitCallback | None) -> None:
        # 等待 FFmpeg 进程结束，拿到退出码，再调用回调
        returncode = process.wait()
        logger.info("FFmpeg 进程退出, returncode=%d", returncode)
        if on_exit:
            on_exit(returncode)
        if self._process is process:
            self._process = None
            self._monitor_thread = None
            self._on_exit = None

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
        finally:
            if self._process is not None and self._process.poll() is not None:
                self._process = None

    def cancel(self) -> None:
        # 取消 = 直接杀掉进程（不保证文件完整，随后由调用方删除半成品）
        if self._process is None or self._process.poll() is not None:
            self._process = None
            return

        logger.info("正在取消 FFmpeg 录制进程...")
        self._process.kill()
        self._process.wait()
        self._process = None

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
