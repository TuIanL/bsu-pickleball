"""录制核心协议 —— FragmentRepository、ProcessRegistry、Clock、ProcessFactory"""

from typing import Protocol, Optional
from datetime import datetime
from pathlib import Path


class FragmentRepository(Protocol):
    def create_starting(self, *, capture_take_id: str, capture_track_id: str,
                        fragment_index: int, rotation_index: int,
                        file_path: str, take_start_offset_ms: int) -> str: ...
    def mark_recording(self, fragment_id: str) -> None: ...
    def complete(self, fragment_id: str, *, status: str, file_size: int = 0,
                 media_duration_ms: int = 0, return_code: int = 0,
                 take_end_offset_ms: int = 0, stop_reason: str = "",
                 error_message: str = "") -> None: ...


class ProcessRegistry(Protocol):
    def register_started(self, *, capture_take_id: str, capture_track_id: str,
                         fragment_id: str, pid: int, pgid: int,
                         command_fingerprint: str, output_path: str) -> int: ...
    def register_ended(self, registration_id: int, *, return_code: int,
                       exit_reason: str, ended_at: datetime) -> None: ...


class Clock(Protocol):
    def utc_now(self) -> datetime: ...
    def monotonic_ms(self) -> int: ...


class ProcessFactory(Protocol):
    def start(self, cmd: list[str], output_path: Path) -> tuple[int, int, str]: ...
