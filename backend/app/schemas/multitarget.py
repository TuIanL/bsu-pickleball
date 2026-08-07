"""
多目标检测（球员 / 球 / 场地元素）相关的 Pydantic 数据模型。

这些模型描述"某一帧里检测到了哪些目标"：
- player 用一个检测框（bbox）表示位置与大小；
- ball 用一个中心点（point）表示位置；
两者都带置信度。unsupported / low-confidence 类别应在归一化阶段被排除，
而不是让整个分析任务失败。
"""

from __future__ import annotations

from math import isfinite
from typing import Literal

from pydantic import BaseModel, Field, model_validator

# 目标类别名称（player 球员 / ball 球；paddle 等作为后续可扩展目标）
TargetClassName = Literal["player", "ball"]
# 多目标检测的整体状态：可用 / 部分 / 无检测 / 不可用 / 跳过 / 失败
MultiTargetStatus = Literal["available", "partial", "no_detections", "unavailable", "skipped", "failed"]


def validate_bbox_values(values: list[float]) -> list[float]:
    # 校验检测框：必须是 4 个有限数值，且右下角在左上角右下方（宽高为正）
    if len(values) != 4:
        raise ValueError("bbox must contain exactly 4 numeric values")
    bbox = [float(value) for value in values]
    if not all(isfinite(value) for value in bbox):
        raise ValueError("bbox must contain only finite numeric values")
    x1, y1, x2, y2 = bbox
    if x2 <= x1 or y2 <= y1:
        raise ValueError("bbox must have positive width and height")
    return bbox


def validate_point_values(values: list[float]) -> list[float]:
    # 校验点坐标：必须是 2 个有限数值
    if len(values) != 2:
        raise ValueError("point must contain exactly 2 numeric values")
    point = [float(value) for value in values]
    if not all(isfinite(value) for value in point):
        raise ValueError("point must contain only finite numeric values")
    return point


class MultiTargetDetection(BaseModel):
    """单帧里的一个检测结果（一个目标）。

    player 使用 bbox（检测框），ball 使用 point（中心点）；
    二者互斥，由 class_name 决定需要的几何字段。
    """

    frame_index: int = Field(ge=0)  # 第几帧
    timestamp_seconds: float = Field(ge=0)  # 该帧对应的时间（秒）
    class_name: TargetClassName  # 类别（"player" / "ball"）
    bbox: list[float] | None = None  # 检测框 [x1, y1, x2, y2]（player 使用）
    point: list[float] | None = None  # 中心点 [x, y]（ball 使用）
    confidence: float = Field(ge=0, le=1)  # 置信度（0~1）
    source_width: int = Field(ge=1)  # 原图宽
    source_height: int = Field(ge=1)  # 原图高
    track_id: str | None = None  # 跟踪 id（跨帧关联同一目标，未跟踪则为空）

    @model_validator(mode="after")
    def validate_geometry(self) -> MultiTargetDetection:
        # 根据类别校验所需几何字段，并做边界检查（不能跑到画面外）
        if self.class_name == "player":
            if self.bbox is None:
                raise ValueError("player detections require bbox")
            self.bbox = validate_bbox_values(self.bbox)
            if self.point is not None:
                raise ValueError("player detections must not include point")
            x1, y1, x2, y2 = self.bbox
            if x2 < 0 or y2 < 0 or x1 > self.source_width or y1 > self.source_height:
                raise ValueError("bbox must intersect the source frame")
        elif self.class_name == "ball":
            if self.point is None:
                raise ValueError("ball detections require point")
            self.point = validate_point_values(self.point)
            if self.bbox is not None:
                raise ValueError("ball detections must not include bbox")
            x, y = self.point
            if x < 0 or y < 0 or x > self.source_width or y > self.source_height:
                raise ValueError("point must lie within the source frame")
        return self


class MultiTargetDetectionFrame(BaseModel):
    """某一帧的全部检测结果集合。"""

    frame_index: int = Field(ge=0)
    timestamp_seconds: float = Field(ge=0)
    detections: list[MultiTargetDetection] = Field(default_factory=list)  # 该帧的目标列表


def bbox_center(bbox: list[float]) -> list[float]:
    # 取检测框中心点坐标 [cx, cy]
    x1, y1, x2, y2 = bbox
    return [(x1 + x2) / 2.0, (y1 + y2) / 2.0]
