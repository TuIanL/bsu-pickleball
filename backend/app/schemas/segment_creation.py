"""工作台补录漏记 rally 的请求契约。"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


RALLY_CREATION_SCHEMA_VERSION = "manual-rally-creation.v1"


class RallyCreateRequest(BaseModel):
    start_ms: int = Field(ge=0, description="相对 CaptureTake 的起始毫秒偏移")
    end_ms: int = Field(ge=0, description="相对 CaptureTake 的结束毫秒偏移")
    label: str = Field(default="", max_length=256)

    @model_validator(mode="after")
    def validate_order(self):
        if self.end_ms <= self.start_ms:
            raise ValueError("新增回合的结束时间必须晚于开始时间")
        return self
