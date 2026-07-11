"""
测试替身 —— FakeRecorder、FakeSyncRecorder、FakeLeaseManager。

所有替身均为内存实现，不启动真实 FFmpeg 进程，不访问真实数据库。
通过构造函数配置行为，提供可控的录制生命周期供业务逻辑测试使用。
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from app.camera.recorder_exit import RecorderExit


# ── FakeRecorder ────────────────────────────────────────────────

class FakeRecorder:
    """可控的单摄 Recorder 替身。"""

    def __init__(
        self,
        *,
        simulate_crash: bool = False,
        exit_code: int = 0,
        exit_delay: float = 0,
    ) -> None:
        self.started = False
        self.stopped = False
        self.cancelled = False
        self._stop_requested = False
        self._cancel_requested = False
        self._simulate_crash = simulate_crash
        self._exit_code = exit_code
        self._exit_delay = exit_delay
        self._on_exit: Callable[[RecorderExit], None] | None = None
        self.pid = 99999
        self.pgid = 99999
        self.command_fingerprint = "fake-fingerprint"
        self._stream_url: str = ""
        self._output_path: Path | None = None
        self._fps: int = 60

    @property
    def stream_url(self) -> str:
        return self._stream_url

    @property
    def output_path(self) -> Path | None:
        return self._output_path

    @property
    def fps(self) -> int:
        return self._fps

    def start(
        self,
        stream_url: str,
        output_path: Path,
        username: str | None = None,
        password: str | None = None,
        fps: int = 60,
        resolution: str = "1920x1080",
        on_exit: Callable[[RecorderExit], None] | None = None,
    ) -> None:
        self.started = True
        self._stop_requested = False
        self._cancel_requested = False
        self._stream_url = stream_url
        self._output_path = output_path
        self._fps = fps
        self._on_exit = on_exit

        if self._simulate_crash:
            t = threading.Thread(target=self._simulate_crash_exit, daemon=True)
            t.start()

    def _simulate_crash_exit(self) -> None:
        if self._exit_delay > 0:
            time.sleep(self._exit_delay)
        if self._on_exit:
            exit_info = RecorderExit(
                returncode=self._exit_code,
                stop_requested=self._stop_requested,
                cancel_requested=self._cancel_requested,
            )
            self._on_exit(exit_info)

    def stop(self, timeout_seconds: float = 30.0) -> None:
        self._stop_requested = True
        self.stopped = True
        if self._on_exit:
            exit_info = RecorderExit(
                returncode=0,
                stop_requested=True,
                cancel_requested=False,
            )
            self._on_exit(exit_info)

    def cancel(self) -> None:
        self._cancel_requested = True
        self.cancelled = True
        if self._on_exit:
            exit_info = RecorderExit(
                returncode=-9,
                stop_requested=False,
                cancel_requested=True,
            )
            self._on_exit(exit_info)

    def simulate_unexpected_exit(self, returncode: int = 0) -> None:
        """模拟无用户请求的异常退出（用于测试 returncode=0 意外退出场景）。"""
        if self._on_exit:
            exit_info = RecorderExit(
                returncode=returncode,
                stop_requested=False,
                cancel_requested=False,
            )
            self._on_exit(exit_info)

    def is_running(self) -> bool:
        return self.started and not self.stopped and not self.cancelled


# ── FakeSyncRecorder ────────────────────────────────────────────

@dataclass
class FakeSyncSegment:
    segment_index: int
    files: list[str] = field(default_factory=list)


class FakeSyncRecorder:
    """可控的双摄 SyncRecorder 替身。"""

    def __init__(
        self,
        *,
        simulate_crash: bool = False,
        exit_code: int = 0,
    ) -> None:
        self.started = False
        self.stopped = False
        self.cancelled = False
        self._simulate_crash = simulate_crash
        self._exit_code = exit_code
        self._stop_requested = False
        self._cancel_requested = False
        self._on_all_complete: Callable | None = None
        self.segments: list[FakeSyncSegment] = [FakeSyncSegment(segment_index=0)]
        self.restart_count: int = 0

    def start_recording(
        self,
        cam_1_url: str,
        cam_2_url: str,
        output_dir: Path,
        fps: int = 60,
        resolution: str = "1920x1080",
        on_segment_start=None,
        on_segment_end=None,
        on_stream_error=None,
        on_all_complete=None,
    ) -> None:
        self.started = True
        self._on_all_complete = on_all_complete
        self.restart_count = 0

    def start_test(self, *args, **kwargs):
        self.started = True
        return True

    def stop_recording(self) -> None:
        self._stop_requested = True
        self.stopped = True
        if self._on_all_complete:
            self._on_all_complete()

    def cancel_recording(self) -> None:
        self._cancel_requested = True
        self.cancelled = True

    def simulate_sync_crash(self) -> None:
        """模拟同步录制的异常退出"""
        if self._on_all_complete:
            self._on_all_complete()

    def is_running(self) -> bool:
        return self.started and not self.stopped and not self.cancelled


# ── FakeLeaseManager ────────────────────────────────────────────

@dataclass
class FakeLease:
    camera_id: str
    capture_take_id: str
    status: str = "active"


class FakeLeaseManager:
    """可控的 CameraLeaseManager 替身（内存实现）。"""

    def __init__(self, *, simulate_conflict: list[str] | None = None) -> None:
        self._leases: dict[str, FakeLease] = {}
        self._simulate_conflict: set[str] = set(simulate_conflict or [])
        self.acquire_calls: list[dict] = []
        self.release_calls: list[str] = []
        self.heartbeat_calls: list[str] = []

    def set_conflict(self, camera_ids: list[str]) -> None:
        """模拟指定摄像机已被占用"""
        self._simulate_conflict = set(camera_ids)

    def acquire(self, camera_ids: list[str], capture_take_id: str) -> list[FakeLease]:
        self.acquire_calls.append({"camera_ids": camera_ids, "capture_take_id": capture_take_id})
        for cid in camera_ids:
            if cid in self._simulate_conflict:
                raise RuntimeError(f"Camera {cid} is already leased")
        leases = []
        for cid in camera_ids:
            lease = FakeLease(camera_id=cid, capture_take_id=capture_take_id, status="active")
            self._leases[cid] = lease
            leases.append(lease)
        return leases

    def release(self, capture_take_id: str) -> None:
        self.release_calls.append(capture_take_id)
        to_release = [cid for cid, lease in self._leases.items() if lease.capture_take_id == capture_take_id]
        for cid in to_release:
            if cid in self._leases:
                self._leases[cid].status = "released"

    def heartbeat(self, capture_take_id: str) -> None:
        self.heartbeat_calls.append(capture_take_id)

    def is_camera_available(self, camera_id: str) -> bool:
        return camera_id not in self._simulate_conflict and (
            camera_id not in self._leases or self._leases[camera_id].status == "released"
        )

    def find_active_lease(self, camera_id: str) -> FakeLease | None:
        lease = self._leases.get(camera_id)
        if lease and lease.status == "active":
            return lease
        return None

    def cleanup_stale_leases(self) -> None:
        pass
