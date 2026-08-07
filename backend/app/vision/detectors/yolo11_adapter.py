"""YOLO11 检测器适配器（占位） —— 预留 ultralytics 模型集成接口。

预期归一化规范：
- 球员框使用 label `player`
- 球场线/区域检测使用球场特定标签
- 所有框均为球场映射前的原始像素坐标

轻量后端有意不在此处导入 ultralytics，仅在真实视觉阶段再引入该依赖。
"""

from app.vision.detectors.base import Detection


class Yolo11DetectorAdapter:
    """ "YOLO11 检测器"适配器（当前为占位实现）。

    设计意图：先把接口骨架立好，让上层代码能按 `DetectorAdapter` 协议
    调用它；真正的模型推理（加载 ultralytics 的 YOLO11 权重、跑前向）
    留到"真实视觉阶段"再实现，因此现在 `detect` 直接抛 NotImplementedError。
    """

    def __init__(self, model_path: str) -> None:
        # 记下模型权重路径（如 best.pt），真实实现时用来加载模型
        self.model_path = model_path

    def detect(self, frame_path: str) -> list[Detection]:
        # 占位：目前尚未集成 YOLO11，调用即报错并提示预期行为。
        # 真实实现会：用 self.model_path 加载模型，对 frame_path 这张图推理，
        # 把结果整理成 Detection 列表返回。
        raise NotImplementedError(
            f"YOLO11 integration is reserved for the real vision phase; would run {self.model_path} on {frame_path}."
        )
