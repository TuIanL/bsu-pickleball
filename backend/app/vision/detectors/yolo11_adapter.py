"""YOLO11 检测器适配器（占位） —— 预留 ultralytics 模型集成接口。

预期归一化规范：
- 球员框使用 label `player`
- 球场线/区域检测使用球场特定标签
- 所有框均为球场映射前的原始像素坐标

轻量后端有意不在此处导入 ultralytics，仅在真实视觉阶段再引入该依赖。
"""

from app.vision.detectors.base import Detection


class Yolo11DetectorAdapter:
    def __init__(self, model_path: str) -> None:
        self.model_path = model_path

    def detect(self, frame_path: str) -> list[Detection]:
        raise NotImplementedError(
            "YOLO11 integration is reserved for the real vision phase; "
            f"would run {self.model_path} on {frame_path}."
        )
