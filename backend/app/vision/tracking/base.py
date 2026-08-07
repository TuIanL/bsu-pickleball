"""跟踪基础数据结构 —— 跟踪点定义。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TrackPoint:
    """单个跟踪点（帧索引、轨迹ID、标签、坐标和置信度）。"""

    frame_index: int
    track_id: str
    label: str
    x: float
    y: float
    confidence: float
