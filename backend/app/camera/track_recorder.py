"""TrackRecorder —— 独立单轨分片录制组件"""
from __future__ import annotations

import hashlib
import logging
import os
import platform
import subprocess
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from app.camera.recording_protocols import ProcessFactory, ProcessRegistry, Clock

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FragmentStartSpec:
    """启动一个 FFmpeg 分段录制所需的完整参数"""
    capture_take_id: str
    capture_track_id: str
    fragment_id: str
    camera_id: str
    stream_url: str
    output_path: Path
    fragment_index: int
    rotation_index: int
    take_start_offset_ms: int
    fps: int = 60
    resolution: str = "1920x1080"
    sync_to_host_clock: bool = False


@dataclass
class FragmentExit:
    """FFmpeg 进程退出时的基本信息"""
    fragment_id: str
    return_code: int
    unexpected: bool = False
    stderr_tail: str = ""


@dataclass
class FragmentResult:
    """分段录制结果：成功/失败/丢弃"""
    fragment_id: str
    status: str  # completed / failed / discarded
    return_code: int
    file_size: int = 0
    media_duration_ms: int = 0
    take_end_offset_ms: int = 0
    error_message: str = ""


class FragmentHandle:
    """分段录制句柄，用于向录制器发送停止/等待/取消指令"""
    def __init__(self, fragment_id: str, recorder: "TrackRecorder"):
        self._fragment_id = fragment_id
        self._recorder = recorder

    def request_stop(self, reason: str) -> None:
        """请求停止当前分段录制（输入 'q' 给 FFmpeg）"""
        self._recorder._request_stop(reason)

    def wait(self, timeout: float = 30) -> FragmentResult:
        """等待录制进程退出并返回结果"""
        return self._recorder._wait_for_exit(timeout)

    def cancel(self) -> None:
        """强制杀死当前分段录制"""
        self._recorder._cancel()


class TrackRecorder:
    """管理一个 CaptureTrack 的当前 FFmpeg 进程。"""

    def __init__(self, *, process_registry=None, clock=None):
        self._process_registry = process_registry  # 进程注册表，用于记录进程生命周期
        self._clock = clock or _DefaultClock()      # 时钟源，默认使用系统单调时钟
        self._process: subprocess.Popen[bytes] | None = None  # 当前 FFmpeg 进程
        self._lock = threading.Lock()      # 保护共享状态的锁
        self._completed = threading.Event()  # 录制完成信号量
        self._callback_emitted = False     # 是否已发送退出回调
        self._result: FragmentResult | None = None  # 录制结果
        self._on_exit: Callable[[FragmentExit], None] | None = None  # 退出回调函数
        self._stop_reason = ""             # 停止原因
        self._spec: FragmentStartSpec | None = None  # 当前分段规格
        self._monitor_thread: threading.Thread | None = None  # 监控线程
        self._start_ms: int = 0            # 启动时的单调时钟（毫秒）
        self._fragment_id: str = ""        # 当前分段 ID
        self._pid: int = 0                 # FFmpeg 进程 PID
        self._pgid: int = 0                # FFmpeg 进程组 ID
        self._fingerprint: str = ""        # 命令指纹（用于去重/追踪）
        self._registration_id: int = 0     # 进程注册表返回的注册 ID

    def start_fragment(self, spec: FragmentStartSpec,
                       on_exit: Callable[[FragmentExit], None],
                       launch_barrier: threading.Barrier | None = None) -> FragmentHandle:
        """启动新的 FFmpeg 分段录制，返回操作句柄"""
        with self._lock:
            self._spec = spec
            self._fragment_id = spec.fragment_id
            self._on_exit = on_exit
            self._result = None
            self._callback_emitted = False
            self._completed.clear()

            output_path = spec.output_path
            output_path.parent.mkdir(parents=True, exist_ok=True)

            cmd = self._build_command(spec)
            cmd_str = " ".join(cmd)
            self._fingerprint = hashlib.sha256(cmd_str.encode()).hexdigest()[:16]

            # The coordinator releases all tracks together immediately before
            # process creation, minimizing software-induced start skew.
            if launch_barrier is not None:
                launch_barrier.wait()

            self._process = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE, start_new_session=True,
            )
            self._pid = self._process.pid or 0
            try:
                self._pgid = os.getpgid(self._process.pid) if self._process.pid else 0
            except (ProcessLookupError, OSError):
                self._pgid = 0
            self._start_ms = int(self._clock.monotonic_ms())

            if self._process_registry:
                try:
                    self._registration_id = self._process_registry.register_started(
                        capture_take_id=spec.capture_take_id,
                        capture_track_id=spec.capture_track_id,
                        fragment_id=spec.fragment_id,
                        pid=self._pid, pgid=self._pgid,
                        command_fingerprint=self._fingerprint,
                        output_path=str(output_path),
                    )
                except Exception:
                    pass

            self._monitor_thread = threading.Thread(target=self._monitor, daemon=True)
            self._monitor_thread.start()

            return FragmentHandle(spec.fragment_id, self)

    @staticmethod
    def _sync_encoder() -> str:
        configured = os.environ.get("PICKLEBALL_SYNC_VIDEO_ENCODER")
        if configured:
            return configured
        return "h264_videotoolbox" if platform.system() == "Darwin" else "libx264"

    def _build_command(self, spec: FragmentStartSpec) -> list[str]:
        """根据分段规格构建 FFmpeg 命令行"""
        cmd = [
            "ffmpeg",
            "-rtsp_transport", "tcp",
            "-timeout", "5000000",
        ]
        if spec.sync_to_host_clock:
            encoder = self._sync_encoder()
            cmd.extend([
                # Timestamp each input frame on this host's shared clock, then
                # make both outputs advance at the requested identical cadence.
                "-use_wallclock_as_timestamps", "1",
                "-fflags", "+genpts",
                "-i", spec.stream_url,
                "-map", "0:v:0",
                "-an",
                "-vf", f"fps={spec.fps}",
                "-fps_mode", "cfr",
                "-r", str(spec.fps),
                "-c:v", encoder,
            ])
            if encoder == "libx264":
                cmd.extend(["-preset", "veryfast", "-tune", "zerolatency", "-crf", "20"])
            else:
                cmd.extend(["-b:v", "12M"])
        else:
            cmd.extend([
                "-fflags", "+genpts",
                "-i", spec.stream_url,
                "-map", "0:v:0",
                "-an",
                "-c", "copy",
            ])
        cmd.extend(["-f", "mpegts", "-y", str(spec.output_path)])
        return cmd

    def _monitor(self) -> None:
        """后台线程：等待 FFmpeg 退出并收集结果"""
        if not self._process:
            return
        return_code = self._process.wait()
        elapsed_ms = int(self._clock.monotonic_ms()) - self._start_ms

        with self._lock:
            if self._process_registry:
                try:
                    self._process_registry.register_ended(
                        self._registration_id, return_code=return_code,
                        exit_reason=self._stop_reason or ("unexpected" if return_code != 0 or not self._stop_reason else "stopped"),
                        ended_at=datetime.now(timezone.utc),
                    )
                except Exception:
                    pass

            is_unexpected = not self._stop_reason and not self._spec

            status = "completed"
            if self._stop_reason == "cancelled":
                status = "discarded"
            elif return_code != 0 or is_unexpected:
                status = "failed"

            self._result = FragmentResult(
                fragment_id=self._fragment_id,
                status=status,
                return_code=return_code,
                media_duration_ms=elapsed_ms,
                take_end_offset_ms=(self._spec.take_start_offset_ms + elapsed_ms) if self._spec else elapsed_ms,
                error_message="" if status == "completed" else f"FFmpeg exit code={return_code}",
            )

            if not self._callback_emitted and self._on_exit:
                self._callback_emitted = True
                self._on_exit(FragmentExit(
                    fragment_id=self._fragment_id,
                    return_code=return_code,
                    unexpected=is_unexpected,
                ))

            self._completed.set()
            self._process = None

    def _request_stop(self, reason: str) -> None:
        """向 FFmpeg 发送 'q' 命令请求优雅停止"""
        with self._lock:
            self._stop_reason = reason
        if self._process and self._process.poll() is None:
            try:
                self._process.stdin.write(b"q")
                self._process.stdin.flush()
            except Exception:
                pass

    def _cancel(self) -> None:
        """强制杀死 FFmpeg 进程"""
        with self._lock:
            self._stop_reason = "cancelled"
        p = self._process
        if p and p.poll() is None:
            try:
                p.kill()
                p.wait()
            except Exception:
                pass

    def _wait_for_exit(self, timeout: float = 30) -> FragmentResult:
        """等待录制进程退出，超时则强制杀死"""
        self._completed.wait(timeout=timeout)
        if self._result:
            return self._result
        if self._process and self._process.poll() is None:
            self._process.kill()
            self._process.wait()
        return FragmentResult(
            fragment_id=self._fragment_id,
            status="failed", return_code=-1,
            error_message="timeout waiting for exit",
        )

    def is_running(self) -> bool:
        """检查当前 FFmpeg 进程是否仍在运行"""
        return self._process is not None and self._process.poll() is None


class _DefaultClock:
    """默认时钟实现，基于 time 模块"""
    import time as _time
    def utc_now(self) -> datetime:
        return datetime.now(timezone.utc)
    def monotonic_ms(self) -> int:
        return int(self._time.monotonic() * 1000)
