"""检测器基础接口 —— 定义检测结果数据类和适配器协议。"""

from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass(frozen=True)
class Detection:
    """单帧中的单个检测结果。"""
    frame_index: int
    label: str
    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float
    track_hint: Optional[str] = None


class DetectorAdapter(Protocol):
    """检测器适配器协议 —— 对单帧图像返回归一化检测列表。"""
    def detect(self, frame_path: str) -> list[Detection]:
        """Return normalized detections for one frame."""
