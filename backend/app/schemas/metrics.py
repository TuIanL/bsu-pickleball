"""
运动表现指标相关的 Pydantic 数据模型 —— 距离、速度、区域停留、间距、热力图等。

这些模型是分析流水线计算出的"结果数据"：从原始轨迹算出球员移动了多少、
跑多快、在厨房区（非截击区）待多久、双打搭档间距如何、常出现在哪些位置等。
"""

from __future__ import annotations

from typing import Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field


class MetricStatus(BaseModel):
    """单个指标的评估状态——区分"不适用"和"未识别到"。"""
    status: Literal["available", "not_applicable", "insufficient_players"]
    reason: str = ""
    expected_player_count: Optional[int] = None
    observed_player_count: Optional[int] = None


class DistanceMetric(BaseModel):
    """单个轨迹（一名球员）的累计移动距离（英尺）。"""
    track_id: str
    distance_ft: float = Field(ge=0)   # 距离（英尺），ge=0 表示非负


class SpeedSegment(BaseModel):
    """速度曲线上的一小段：在某个时间段内的瞬时速度。"""
    track_id: str
    start_time: float = Field(ge=0)    # 起始时间（秒）
    end_time: float = Field(ge=0)      # 结束时间（秒）
    speed_ft_per_s: float = Field(ge=0)  # 该段速度（英尺/秒）


class SpeedSummary(BaseModel):
    """某球员的速度汇总：平均速度、最大速度，以及逐段明细。"""
    track_id: str
    average_speed_ft_per_s: float = Field(ge=0)
    max_speed_ft_per_s: float = Field(ge=0)
    segments: List[SpeedSegment]


class ZoneDwellMetric(BaseModel):
    """某球员在"厨房区"（非截击区，球场网前 7 英尺区域）的停留情况。"""
    track_id: str
    kitchen_frames: int = Field(ge=0)    # 停留帧数
    kitchen_seconds: float = Field(ge=0)  # 停留秒数


class DoublesSpacingSample(BaseModel):
    """双打搭档间距的一个采样点（某一时刻两人距离）。"""
    timestamp_seconds: float = Field(ge=0)
    track_a: str       # 球员 A 的 track_id
    track_b: str       # 球员 B 的 track_id
    distance_ft: float = Field(ge=0)


class DoublesSpacingSummary(BaseModel):
    """双打搭档间距汇总：平均/最小/最大间距，以及逐采样点明细。"""
    pair: Tuple[str, str]               # 这一对搭档的两个 track_id
    average_spacing_ft: float = Field(ge=0)
    min_spacing_ft: float = Field(ge=0)
    max_spacing_ft: float = Field(ge=0)
    samples: List[DoublesSpacingSample]


class HeatmapCell(BaseModel):
    """热力图的一个格子：第几行第几列、被经过的次数。"""
    row: int = Field(ge=0)
    col: int = Field(ge=0)
    count: int = Field(ge=0)            # 该格命中次数（出现越多越"热"）


class Heatmap(BaseModel):
    """整张位置热力图：行列数与各格数据。"""
    rows: int = Field(gt=0)             # 行数（必须大于 0）
    cols: int = Field(gt=0)             # 列数
    cells: List[HeatmapCell]


class PerformanceMetrics(BaseModel):
    """一次分析汇总的全部运动表现指标。"""
    distances: List[DistanceMetric]                       # 各球员移动距离
    speeds: List[SpeedSummary]                            # 各球员速度
    kitchen_dwell: List[ZoneDwellMetric]                  # 各球员厨房区停留
    doubles_spacing: List[DoublesSpacingSummary]          # 双打间距（单打时为空数组，兼容旧消费者）
    heatmap: Heatmap                                     # 位置热力图
    metric_statuses: Dict[str, MetricStatus] = Field(default_factory=dict)  # 各指标状态（旁路字段）
    # 球轨迹与弹跳点摘要（可选，来自球分析阶段）
    ball_detected_frame_count: int = 0                   # 球检测到的帧数
    ball_detection_rate: float = 0.0                      # 球检测率
    ball_trajectory_sample_count: int = 0                 # 原始球轨迹样本数
    cleaned_ball_trajectory_sample_count: int = 0         # 清洗后轨迹点数
    bounce_event_count: int = 0                           # 弹跳事件候选数
    first_bounce_timestamp_seconds: float | None = None   # 第一次弹跳时间戳
    last_bounce_timestamp_seconds: float | None = None    # 最后一次弹跳时间戳
