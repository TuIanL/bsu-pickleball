"""CaptureTakeSummary —— 用于 CaptureStopResult 的轻量 CaptureTake 摘要。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class CaptureTakeSummary(BaseModel):
    id: str
    field_session_id: str
    capture_mode: str
    source_session_type: str
    source_session_id: str
    status: str
    started_at: datetime
    ended_at: datetime | None = None
    duration_ms: int | None = None
    revision: int = 0

    class Config:
        from_attributes = True
