"""姿态估计基础接口 —— 定义关键点和姿态估计适配器协议。"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class PoseKeypoint:
    """单个姿态关键点。"""
    name: str
    x: float
    y: float
    confidence: float


@dataclass(frozen=True)
class PoseResult:
    """单帧中单个主体的姿态估计结果。"""
    frame_index: int
    subject_id: str
    keypoints: list[PoseKeypoint]


class PoseEstimatorAdapter(Protocol):
    """姿态估计器适配器协议 —— 对指定对象框返回归一化关键点。"""
    def estimate(self, frame_path: str, subject_boxes: list[tuple[float, float, float, float]]) -> list[PoseResult]:
        """Return normalized pose keypoints for detected players."""
