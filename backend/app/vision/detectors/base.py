"""检测器基础接口 —— 定义检测结果数据类和适配器协议。

本文件只放"最基础"的东西：
1. `Detection`：一次检测结果的数据结构（哪帧、什么类别、框在哪、置信度）。
2. `DetectorAdapter`：检测器适配器协议（Protocol），规定所有检测器
   都必须实现 `detect(frame_path) -> list[Detection]` 这个方法。

所谓"协议（Protocol）"：一种静态 duck-typing 约定，只要某个类
实现了约定的方法，就被认为"满足该协议"，无需显式继承。
"""

from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass(frozen=True)
class Detection:
    """单帧中的单个检测结果。

    一个 `Detection` 表示"在这一帧里，发现了一个物体"。

    字段说明：
    - frame_index：该结果来自第几帧（从 0 开始的帧序号）。
    - label：检测到的类别名（如 "player" 表示球员）。
    - confidence：模型对该结果的置信度，0~1 之间的浮点数，越大越可信。
    - x1, y1：检测框左上角的像素坐标。
    - x2, y2：检测框右下角的像素坐标。
      框的宽 = x2 - x1，高 = y2 - y1。
    - track_hint：可选的"跟踪提示"字符串，用于把不同帧里同一物体关联起来
      （比如同一球员在多帧里都检测到，用相同 hint 串起来）。
    """

    frame_index: int
    label: str
    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float
    track_hint: Optional[str] = None


class DetectorAdapter(Protocol):
    """检测器适配器协议 —— 对单帧图像返回归一化检测列表。

    任何"检测器"只要提供下面这个 `detect` 方法，就满足本协议，
    上层代码就能无差别地调用它。
    """

    def detect(self, frame_path: str) -> list[Detection]:
        """对一帧图像（磁盘上的图片路径）做检测，返回 Detection 列表。

        参数：
        - frame_path：待检测帧的图像文件路径。
        返回：
        - 该帧里所有检测到的物体（Detection 列表）。
        """
