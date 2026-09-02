"""工作台修正 rally 序号的请求契约。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


RALLY_ORDINAL_UPDATE_SCHEMA_VERSION = "manual-rally-ordinal.v1"
RallyOrdinalUpdateMode = Literal["from_anchor", "whole_take"]


class RallyOrdinalUpdateRequest(BaseModel):
    """按时间顺序修正一个 take 内 rally ordinal。"""

    mode: RallyOrdinalUpdateMode = "from_anchor"
    anchor_segment_id: str | None = None
    start_ordinal: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def validate_anchor(self):
        if self.mode == "from_anchor" and not self.anchor_segment_id:
            raise ValueError("从当前分开始连续编号时必须指定 anchor_segment_id")
        return self
