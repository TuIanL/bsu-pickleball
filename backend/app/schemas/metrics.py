"""运动表现指标相关的 Pydantic 数据模型 —— 距离、速度、区域停留、间距、热力图等。"""

from __future__ import annotations

from typing import List, Tuple

from pydantic import BaseModel, Field


class DistanceMetric(BaseModel):
    """单个轨迹的累计移动距离（英尺）。"""
    track_id: str
    distance_ft: float = Field(ge=0)


class SpeedSegment(BaseModel):
    track_id: str
    start_time: float = Field(ge=0)
    end_time: float = Field(ge=0)
    speed_ft_per_s: float = Field(ge=0)


class SpeedSummary(BaseModel):
    track_id: str
    average_speed_ft_per_s: float = Field(ge=0)
    max_speed_ft_per_s: float = Field(ge=0)
    segments: List[SpeedSegment]


class ZoneDwellMetric(BaseModel):
    track_id: str
    kitchen_frames: int = Field(ge=0)
    kitchen_seconds: float = Field(ge=0)


class DoublesSpacingSample(BaseModel):
    timestamp_seconds: float = Field(ge=0)
    track_a: str
    track_b: str
    distance_ft: float = Field(ge=0)


class DoublesSpacingSummary(BaseModel):
    pair: Tuple[str, str]
    average_spacing_ft: float = Field(ge=0)
    min_spacing_ft: float = Field(ge=0)
    max_spacing_ft: float = Field(ge=0)
    samples: List[DoublesSpacingSample]


class HeatmapCell(BaseModel):
    row: int = Field(ge=0)
    col: int = Field(ge=0)
    count: int = Field(ge=0)


class Heatmap(BaseModel):
    rows: int = Field(gt=0)
    cols: int = Field(gt=0)
    cells: List[HeatmapCell]


class PerformanceMetrics(BaseModel):
    distances: List[DistanceMetric]
    speeds: List[SpeedSummary]
    kitchen_dwell: List[ZoneDwellMetric]
    doubles_spacing: List[DoublesSpacingSummary]
    heatmap: Heatmap
