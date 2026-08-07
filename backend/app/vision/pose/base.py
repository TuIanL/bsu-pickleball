"""姿态估计基础接口 —— 定义关键点和姿态估计适配器协议。"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class PoseKeypoint:
    """单个姿态关键点。"""

    name: str  # 关键点名称，例如 "nose"、"left_shoulder"
    x: float  # 关键点在图像中的横向坐标（像素，未归一化）
    y: float  # 关键点在图像中的纵向坐标（像素，未归一化）
    confidence: float  # 该关键点的检测置信度，取值范围通常 [0, 1]

    # 说明：这是「协议层」的轻量关键点结构，仅含 name/x/y/confidence。
    # 实际生产适配器（rtmpose26_adapter.py）使用的是 app.schemas.pose 中功能更丰富的
    # PoseKeypoint（额外带有 visible 可见性标记），二者字段不完全相同，按需取用。


@dataclass(frozen=True)
class PoseResult:
    """单帧中单个主体的姿态估计结果。"""

    frame_index: int  # 所属帧序号（从 0 开始）
    subject_id: str  # 主体（球员）标识，对应跟踪引擎赋予的 track_id
    keypoints: list[PoseKeypoint]  # 该主体在本帧的全部关键点列表


class PoseEstimatorAdapter(Protocol):
    """姿态估计器适配器协议 —— 对指定对象框返回归一化关键点。"""

    def estimate(self, frame_path: str, subject_boxes: list[tuple[float, float, float, float]]) -> list[PoseResult]:
        """Return normalized pose keypoints for detected players.

        约定：给定一个帧的路径、以及若干待估计人体的边界框（每个框为 (x1, y1, x2, y2)），
        返回这些人在该帧的姿态估计结果列表。
        """
