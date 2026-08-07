"""多视角融合共享类型 —— 单视角观测、canonical 观测与融合时间轴 tick。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ViewObservation:
    """某一视角在某个分析帧的真实观测（Spike/raw observation 的层内表示）。

    坐标字段为 **Local Camera Court Frame** 的原始坐标（未平滑、未插值）。
    `view_player_id` 为该视角内部的球员身份（如 render 的 Player_1）；两路之间的
    `view_player_id` 没有任何等价关系，需经 CrossViewPlayerAssociator 关联。
    """

    view_id: str
    source_frame_index: int
    timestamp_seconds: float
    local_x_ft: float
    local_y_ft: float
    view_player_id: str = ""
    projection_status: str | None = None
    projection_confidence: float | None = None
    footpoint_method: str | None = None
    source_track_id: str | None = None
    confidence: float = 0.0


ViewAvailability = Literal["available", "unavailable"]


@dataclass(frozen=True)
class CanonicalObservation:
    """canonical 时间轴上某视角在某时刻的观测（可追踪组成 + intrinsic 特征源）。"""

    view_id: str
    view_status: ViewAvailability
    # 参考视角本身：source == 参考分析帧，误差为 0；副视角：经 sync mapping 配对。
    source_frame_index: int | None
    source_timestamp_ms: float | None
    mapped_take_timestamp_ms: float | None
    selection_error_ms: float | None
    # canonical 坐标（已归一化）；不可用时为 None。
    canonical_x_ft: float | None = None
    canonical_y_ft: float | None = None
    # intrinsic 特征源（来自源 ViewObservation，供观测质量评估）。
    view_player_id: str = ""
    detector_confidence: float | None = None
    projection_confidence: float | None = None
    footpoint_method: str | None = None
    tracking_status: str | None = None
    is_interpolated: bool = False


@dataclass(frozen=True)
class CanonicalTimelineTick:
    """一个融合时刻：以 reference track 的 analysis-frame timeline 为基准。"""

    take_timestamp_ms: float
    reference_frame_index: int
    observations: dict[str, CanonicalObservation]
