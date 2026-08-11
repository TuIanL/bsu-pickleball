"""
Field Session Pydantic schemas —— 创建、更新、详情、列表。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

DisplayModeLiteral = Literal["standard", "showcase"]


class FieldSessionCreate(BaseModel):
    """创建 Field Session 的请求体。"""

    title: str = Field(default="", description="任务名称")
    venue: str = Field(default="", description="场馆")
    court_name: str = Field(default="", description="球场名称")
    capture_mode: Literal["practice", "match", "engineering"] = Field(
        default="practice", description="采集模式: practice / match / engineering"
    )
    match_format: Literal["singles", "doubles"] = Field(default="doubles", description="比赛形式: singles / doubles")
    camera_setup: Literal["single", "dual", "debug_single"] = Field(
        default="single", description="摄像头方案: single / dual / debug_single"
    )
    display_mode: DisplayModeLiteral = Field(default="standard", description="显示模式: standard / showcase")
    notes: str = Field(default="", description="备注")

    @model_validator(mode="after")
    def validate_showcase_camera(self) -> "FieldSessionCreate":
        if self.display_mode == "showcase" and self.camera_setup != "dual":
            raise ValueError("展示模式只能与双摄方案组合")
        return self


class FieldSessionUpdate(BaseModel):
    """更新 Field Session 元数据的请求体。"""

    title: str | None = None
    venue: str | None = None
    court_name: str | None = None
    capture_mode: Literal["practice", "match", "engineering"] | None = None
    match_format: Literal["singles", "doubles"] | None = None
    camera_setup: Literal["single", "dual", "debug_single"] | None = None
    display_mode: DisplayModeLiteral | None = None
    notes: str | None = None


class FieldSessionSummary(BaseModel):
    """Field Session 列表项。"""

    id: str
    title: str
    venue: str
    court_name: str
    capture_mode: str
    match_format: str
    camera_setup: str
    display_mode: str = "standard"
    status: str
    notes: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FieldSessionDetail(BaseModel):
    """Field Session 详情。"""

    id: str
    title: str
    venue: str
    court_name: str
    capture_mode: str
    match_format: str
    camera_setup: str
    display_mode: str = "standard"
    status: str
    notes: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FieldSessionDeleteResult(BaseModel):
    id: str
    status: Literal["deleted", "blocked", "not_found"]
    detail: str = ""
