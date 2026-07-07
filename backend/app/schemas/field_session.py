"""
Field Session Pydantic schemas —— 创建、更新、详情、列表。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class FieldSessionCreate(BaseModel):
    """创建 Field Session 的请求体。"""
    title: str = Field(default="", description="任务名称")
    venue: str = Field(default="", description="场馆")
    court_name: str = Field(default="", description="球场名称")
    capture_mode: Literal["practice", "match", "engineering"] = Field(default="practice", description="采集模式: practice / match / engineering")
    match_format: Literal["singles", "doubles"] = Field(default="doubles", description="比赛形式: singles / doubles")
    camera_setup: Literal["single", "dual", "debug_single"] = Field(default="single", description="摄像头方案: single / dual / debug_single")
    notes: str = Field(default="", description="备注")


class FieldSessionUpdate(BaseModel):
    """更新 Field Session 元数据的请求体。"""
    title: Optional[str] = None
    venue: Optional[str] = None
    court_name: Optional[str] = None
    capture_mode: Optional[Literal["practice", "match", "engineering"]] = None
    match_format: Optional[Literal["singles", "doubles"]] = None
    camera_setup: Optional[Literal["single", "dual", "debug_single"]] = None
    notes: Optional[str] = None


class FieldSessionSummary(BaseModel):
    """Field Session 列表项。"""
    id: str
    title: str
    venue: str
    court_name: str
    capture_mode: str
    match_format: str
    camera_setup: str
    status: str
    notes: str
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
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
    status: str
    notes: str
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FieldSessionDeleteResult(BaseModel):
    id: str
    status: Literal["deleted", "blocked", "not_found"]
    detail: str = ""
