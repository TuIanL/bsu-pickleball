"""Preflight / InMemory adapters —— 用于短录测试的临时 Fragment 和 Process 存储"""
from __future__ import annotations

from datetime import datetime, timezone


class InMemoryFragmentRepository:
    """临时 Fragment 仓库（不写入正式 DB），用于 Preflight。"""

    def __init__(self):
        self.fragments: list[dict] = []

    def create_starting(self, *, capture_take_id: str = "", capture_track_id: str = "",
                        fragment_index: int = 0, rotation_index: int = 0,
                        file_path: str = "", take_start_offset_ms: int = 0) -> str:
        fid = f"ephemeral_{len(self.fragments)}"
        self.fragments.append({
            "id": fid, "capture_take_id": capture_take_id,
            "capture_track_id": capture_track_id,
            "fragment_index": fragment_index, "rotation_index": rotation_index,
            "file_path": file_path, "status": "starting",
            "started_at": datetime.now(timezone.utc),
        })
        return fid

    def mark_recording(self, fragment_id: str) -> None:
        for f in self.fragments:
            if f["id"] == fragment_id:
                f["status"] = "recording"

    def complete(self, fragment_id: str, *, status: str = "completed", file_size: int = 0,
                 media_duration_ms: int = 0, return_code: int = 0,
                 take_end_offset_ms: int = 0, stop_reason: str = "",
                 error_message: str = "") -> None:
        for f in self.fragments:
            if f["id"] == fragment_id:
                f["status"] = status
                f["file_size"] = file_size
                f["media_duration_ms"] = media_duration_ms
                f["return_code"] = return_code


class NullProcessRegistry:
    """Preflight 用空 Process Registry"""

    def register_started(self, *, capture_take_id: str = "", capture_track_id: str = "",
                         fragment_id: str = "", pid: int = 0, pgid: int = 0,
                         command_fingerprint: str = "", output_path: str = "") -> int:
        return 0

    def register_ended(self, registration_id: int = 0, *, return_code: int = 0,
                       exit_reason: str = "", ended_at=None) -> None:
        pass
