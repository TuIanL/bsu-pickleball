"""
录制退出原因 —— 解耦 Recorder 退出码与业务语义。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RecorderExit:
    """Recorder / SyncRecorder 退出时携带的业务语义。"""
    returncode: int
    stop_requested: bool = False
    cancel_requested: bool = False
