from __future__ import annotations

from math import isfinite
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


TargetClassName = Literal["player"]
MultiTargetStatus = Literal["available", "partial", "no_detections", "unavailable", "skipped", "failed"]


def validate_bbox_values(values: list[float]) -> list[float]:
    if len(values) != 4:
        raise ValueError("bbox must contain exactly 4 numeric values")
    bbox = [float(value) for value in values]
    if not all(isfinite(value) for value in bbox):
        raise ValueError("bbox must contain only finite numeric values")
    x1, y1, x2, y2 = bbox
    if x2 <= x1 or y2 <= y1:
        raise ValueError("bbox must have positive width and height")
    return bbox


class MultiTargetDetection(BaseModel):
    frame_index: int = Field(ge=0)
    timestamp_seconds: float = Field(ge=0)
    class_name: TargetClassName
    bbox: list[float] = Field(min_length=4, max_length=4)
    confidence: float = Field(ge=0, le=1)
    source_width: int = Field(ge=1)
    source_height: int = Field(ge=1)
    track_id: Optional[str] = None

    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, value: list[float]) -> list[float]:
        return validate_bbox_values(value)

    @model_validator(mode="after")
    def validate_frame_bounds(self) -> "MultiTargetDetection":
        x1, y1, x2, y2 = self.bbox
        if x2 < 0 or y2 < 0 or x1 > self.source_width or y1 > self.source_height:
            raise ValueError("bbox must intersect the source frame")
        return self


class MultiTargetDetectionFrame(BaseModel):
    frame_index: int = Field(ge=0)
    timestamp_seconds: float = Field(ge=0)
    detections: list[MultiTargetDetection] = Field(default_factory=list)


def bbox_center(bbox: list[float]) -> list[float]:
    x1, y1, x2, y2 = bbox
    return [(x1 + x2) / 2.0, (y1 + y2) / 2.0]
