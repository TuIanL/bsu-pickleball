"""检测器适配器 —— YOLO11 等目标检测模型集成。

本子包负责把"目标检测模型"（如 YOLO11）封装成统一的接口，
让上层的分析流水线只关心"检测一帧里有什么框"，而不用关心
具体用的是哪个模型、怎么推理。

包含的子模块：
- `base.py`：定义检测结果数据类 `Detection` 与适配器协议 `DetectorAdapter`。
- `multitarget.py`：多目标检测（球员/球场元素等）的统一检测与归一化工具。
- `yolo11_adapter.py`：YOLO11 检测器的适配器（当前为占位实现）。
- `ball_adapter.py`：球检测适配器（YOLO / ultralytics），实现 `BallDetectorProtocol`，
  供 `AnalysisPipeline` 在启用球分析时按需接入；缺失模型/依赖时返回清晰不可用错误。
"""
