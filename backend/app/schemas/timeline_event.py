"""
Session Timeline Event Pydantic schemas —— 创建、更新、详情、列表筛选。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

# -- 事件类型枚举 --
TimelineEventTypeStr = Literal[
    "session_note",
    "non_play_start",
    "non_play_end",
    "game_start",
    "game_end",
    "set_start",
    "set_end",
    "rally_start",
    "rally_end",
    "score_update",
    "score_correction",
    "side_change",
    "timeout_start",
    "timeout_end",
    "drill_start",
    "drill_end",
    "custom_marker",
]

TimelineEventSourceStr = Literal["manual", "algorithm", "corrected"]


def _parse_payload_json(v: Any, *, allow_none: bool = False) -> dict[str, Any] | None:
    if v is None:
        return None if allow_none else {}
    if isinstance(v, dict):
        return v
    if isinstance(v, str):
        try:
            parsed = json.loads(v)
        except json.JSONDecodeError:
            raise ValueError("payload_json 必须是有效的 JSON 对象")
        if not isinstance(parsed, dict):
            raise ValueError("payload_json 必须是 JSON 对象")
        return parsed
    raise ValueError("payload_json 必须是 JSON 对象")


class TimelineEventCreate(BaseModel):
    """创建 Session Timeline Event 的请求体。"""
    recording_session_id: Optional[str] = Field(default=None, description="关联的录制会话 ID")
    timestamp_ms: Optional[int] = Field(default=None, description="视频内时间戳（毫秒），未提交时后端兜底计算")
    occurred_at: Optional[datetime] = Field(default=None, description="真实世界时间")
    event_type: TimelineEventTypeStr = Field(..., description="事件类型")
    source: TimelineEventSourceStr = Field(default="manual", description="事件来源")
    label: Optional[str] = Field(default="", description="事件标签")
    note: Optional[str] = Field(default="", description="事件备注")
    payload_json: dict[str, Any] = Field(default_factory=dict, description="扩展数据 JSON 对象")

    @field_validator("timestamp_ms")
    @classmethod
    def timestamp_ms_non_negative(cls, v: int | None) -> int | None:
        if v is not None and v < 0:
            raise ValueError("timestamp_ms 必须大于或等于 0")
        return v

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        valid = [
            "session_note", "non_play_start", "non_play_end",
            "game_start", "game_end", "set_start", "set_end",
            "rally_start", "rally_end", "score_update", "score_correction",
            "side_change", "timeout_start", "timeout_end",
            "drill_start", "drill_end", "custom_marker",
        ]
        if v not in valid:
            raise ValueError(f"event_type 必须是以下之一: {', '.join(valid)}")
        return v

    @field_validator("source")
    @classmethod
    def validate_source(cls, v: str) -> str:
        if v not in ("manual", "algorithm", "corrected"):
            raise ValueError("source 必须是 manual、algorithm 或 corrected")
        return v

    @field_validator("payload_json", mode="before")
    @classmethod
    def validate_payload_json(cls, v: Any) -> dict[str, Any]:
        payload = _parse_payload_json(v)
        return payload or {}


class TimelineEventUpdate(BaseModel):
    """更新 Session Timeline Event 的请求体。不允许修改 field_session_id。"""
    timestamp_ms: Optional[int] = None
    event_type: Optional[TimelineEventTypeStr] = None
    source: Optional[TimelineEventSourceStr] = None
    label: Optional[str] = None
    note: Optional[str] = None
    payload_json: Optional[dict[str, Any]] = None

    @field_validator("timestamp_ms")
    @classmethod
    def timestamp_ms_non_negative(cls, v: int | None) -> int | None:
        if v is not None and v < 0:
            raise ValueError("timestamp_ms 必须大于或等于 0")
        return v

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: str | None) -> str | None:
        if v is None:
            return None
        valid = [
            "session_note", "non_play_start", "non_play_end",
            "game_start", "game_end", "set_start", "set_end",
            "rally_start", "rally_end", "score_update", "score_correction",
            "side_change", "timeout_start", "timeout_end",
            "drill_start", "drill_end", "custom_marker",
        ]
        if v not in valid:
            raise ValueError(f"event_type 必须是以下之一: {', '.join(valid)}")
        return v

    @field_validator("source")
    @classmethod
    def validate_source(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if v not in ("manual", "algorithm", "corrected"):
            raise ValueError("source 必须是 manual、algorithm 或 corrected")
        return v

    @field_validator("payload_json", mode="before")
    @classmethod
    def validate_payload_json(cls, v: Any) -> dict[str, Any] | None:
        return _parse_payload_json(v, allow_none=True)


class TimelineEventSummary(BaseModel):
    """Session Timeline Event 列表项。"""
    id: str
    field_session_id: str
    recording_session_id: Optional[str] = None
    timestamp_ms: int
    occurred_at: datetime
    event_type: str
    source: str
    label: str
    note: str
    payload_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("payload_json", mode="before")
    @classmethod
    def parse_payload_json(cls, v: Any) -> dict[str, Any]:
        payload = _parse_payload_json(v)
        return payload or {}


class TimelineEventDetail(BaseModel):
    """Session Timeline Event 详情。"""
    id: str
    field_session_id: str
    recording_session_id: Optional[str] = None
    timestamp_ms: int
    occurred_at: datetime
    event_type: str
    source: str
    label: str
    note: str
    payload_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("payload_json", mode="before")
    @classmethod
    def parse_payload_json(cls, v: Any) -> dict[str, Any]:
        payload = _parse_payload_json(v)
        return payload or {}
