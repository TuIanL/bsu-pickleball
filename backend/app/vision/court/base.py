"""
球场标定基础接口 —— 定义"像素 → 球场坐标"映射的抽象协议。

本文件是"占位式"的基础定义，把"球场标定器应该长什么样"先约定好，
但具体的数学实现（怎么算单应矩阵、怎么投影）留到后面真实球场线检测
可用时再补。这样做的好处是：其它模块现在就能按这个接口写代码，
不会被具体算法卡住。
"""

# dataclass：自动生成 __init__/__repr__ 等样板代码的数据类（详见 schemas.py 注释）。
from dataclasses import dataclass


@dataclass(frozen=True)
class CourtCoordinate:
    """
    球场坐标系中的一个点。

    和"像素坐标"不同，这里的坐标是"球场上的真实位置"（通常是米或归一化单位），
    代表球员/球在真实球场里的位置。

    字段：
    - x：球场横坐标；
    - y：球场纵坐标；
    - confidence：这个坐标的可信程度（0~1），检测/标定越可靠分数越高。
    """

    x: float
    y: float
    confidence: float


class CourtCalibrator:
    """
    球场标定器抽象基类（Abstract Base Class）。

    "抽象基类"是一种约定：它先把"所有球场标定器都必须具备的方法"列出来，
    但不提供具体实现。子类（真正的标定器）必须实现 `map_pixel_to_court`，
    否则调用时会抛 NotImplementedError。

    目前这里只是占个位，提示"真实实现待做"。
    """

    def map_pixel_to_court(self, x: float, y: float) -> CourtCoordinate:
        """
        把图像上的像素点 (x, y) 映射到球场坐标系中的点。

        参数：
        - x, y：图像像素坐标（通常来自检测结果，如球员脚底点）。

        返回：球场坐标 CourtCoordinate。

        注意：当前基类未实现，调用会抛 NotImplementedError，
        并说明"等真实球场线检测可用后再实现"。
        """
        raise NotImplementedError("Court calibration will be implemented after real court-line detection is available.")
