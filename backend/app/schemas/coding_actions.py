"""Coding Actions API schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class CodingActionRequest(BaseModel):
    action: str = Field(..., description="语义命令类型")
    timestamp_ms: int | None = Field(None, ge=0, description="相对 CaptureTake 的时间戳（毫秒）")
    client_occurred_at: str | None = Field(None, description="前端操作发生的时刻（ISO 8601）")
    client_action_id: str = Field(..., description="客户端幂等 ID")
    expected_revision: int = Field(..., ge=0, description="期望的当前 revision")
    payload: dict[str, Any] = Field(default_factory=dict, description="可选的 action payload")

    @field_validator("action", mode="before")
    @classmethod
    def validate_action(cls, v: str) -> str:
        from app.services.coding_actions_service import VALID_ACTIONS

        if str(v) not in VALID_ACTIONS:
            raise ValueError(f"无效的 action: {v}，合法值: {sorted(VALID_ACTIONS)}")
        return str(v)


class CodingActionResponse(BaseModel):
    revision: int
    created_events: list[dict[str, Any]]
    updated_segments: list[dict[str, Any]]
    live_state: dict[str, Any]
    timeline_events: list[dict[str, Any]] = Field(default_factory=list)
    segments: list[dict[str, Any]] = Field(default_factory=list)
    duplicate: bool = False

    model_config = {"from_attributes": False}


class LiveCodingStateResponse(BaseModel):
    capture_take_id: str
    revision: int
    set_ordinal: int
    game_ordinal: int
    rally_ordinal: int
    non_play: bool
    match_phase: str = "idle"
    intermission_kind: str | None = None
    current_set_segment_id: str | None = None
    current_game_segment_id: str | None = None
    current_rally_segment_id: str | None = None
    server_team: str | None = None
    score_a: int = 0
    score_b: int = 0
    scoring_mode: str = "none"
    scoring_ruleset_version: str | None = None
    recent_results: list[dict] = []
    games_won_a: int = 0
    games_won_b: int = 0
    scoring_phase: str = "rally"
    serving_side: str | None = None
    match_status: str = "not_started"
    match_winner: str | None = None

    model_config = {"from_attributes": True}


class CaptureTakeSummary(BaseModel):
    id: str
    field_session_id: str
    capture_mode: str
    source_session_type: str
    source_session_id: str
    status: str
    started_at: str
    ended_at: str | None = None
    duration_ms: int | None = None
    revision: int

    model_config = {"from_attributes": True}
