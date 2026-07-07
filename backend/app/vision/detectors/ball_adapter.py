"""Configurable ball detector adapter.

把"球检测模型"（默认 YOLO / ultralytics 权重）封装成
`BallDetectorProtocol`，让上层 `AnalysisPipeline` 只依赖协议、不直接耦合
具体模型。缺失模型路径、权重文件或运行时依赖时，抛出清晰的不可用错误，
由 pipeline 捕获并标记为 `unavailable` / `skipped`，而不是中断整个任务。

为了让轻量导入（测试、无 CUDA 环境）不触发重模型依赖，ultralytics / torch
只在首次 `detect` 调用时按需加载。
"""

from __future__ import annotations

from typing import Any

from app.vision.pickleball_game_analysis.ball_detector_protocol import BallDetectorProtocol
from app.vision.pickleball_game_analysis.schemas import BallCandidate


class BallDetectionError(Exception):
    """球检测适配器的基础错误。"""


class BallDetectionModelMissingError(BallDetectionError):
    """配置了球检测但未提供模型路径 / 权重文件。"""


class BallDetectionUnavailableError(BallDetectionError):
    """球检测依赖（ultralytics / torch / 权重）不可用。"""


class YoloBallDetectorAdapter(BallDetectorProtocol):
    """基于 YOLO（ultralytics）的球检测适配器。

    仅在 `detect` 调用时懒加载模型，因此模块导入本身不需要 torch / ultralytics。
    若 `model_path` 为 None 或文件不存在，抛出 `BallDetectionModelMissingError`；
    若运行时依赖缺失，抛出 `BallDetectionUnavailableError`。
    """

    def __init__(
        self,
        model_path: str | None = None,
        confidence_threshold: float = 0.18,
        device: str | None = None,
        class_index: int = 0,
    ) -> None:
        self.model_path = model_path
        self.confidence_threshold = float(confidence_threshold)
        self.device = device
        self.class_index = int(class_index)
        self._model: Any | None = None

    def _ensure_model(self) -> Any:
        # 懒加载：第一次检测时才真正 import 并加载权重
        if self._model is not None:
            return self._model
        if not self.model_path:
            raise BallDetectionModelMissingError(
                "未配置球检测模型路径（PICKLEBALL_BALL_MODEL_PATH），球检测不可用"
            )
        from pathlib import Path

        if not Path(self.model_path).exists():
            raise BallDetectionModelMissingError(f"球检测模型权重不存在：{self.model_path}")
        try:
            from ultralytics import YOLO  # type: ignore
        except Exception as exc:  # 可能是 ImportError / ModuleNotFoundError
            raise BallDetectionUnavailableError(f"球检测依赖 ultralytics 不可用：{exc}") from exc
        try:
            self._model = YOLO(self.model_path)
        except Exception as exc:
            raise BallDetectionUnavailableError(f"加载球检测模型失败：{exc}") from exc
        return self._model

    def detect(self, frame: Any, conf: float = 0.18) -> list[BallCandidate]:
        model = self._ensure_model()
        threshold = conf if conf and conf > 0 else self.confidence_threshold
        results = model.predict(frame, conf=threshold, verbose=False)
        candidates: list[BallCandidate] = []
        for result in results:
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue
            for box in boxes:
                classes = getattr(box, "cls", None)
                if classes is None:
                    continue
                try:
                    class_id = int(classes[0])
                except (TypeError, ValueError, IndexError):
                    continue
                if class_id != self.class_index:
                    continue
                try:
                    xyxy = box.xyxy[0].tolist()
                    confidence = float(box.conf[0])
                except (TypeError, ValueError, IndexError, AttributeError):
                    continue
                x1, y1, x2, y2 = (float(value) for value in xyxy)
                width = max(0.0, x2 - x1)
                height = max(0.0, y2 - y1)
                candidates.append(
                    BallCandidate(
                        image_x=(x1 + x2) / 2.0,
                        image_y=(y1 + y2) / 2.0,
                        confidence=confidence,
                        width=width,
                        height=height,
                        area_ratio=None,
                        aspect_ratio=(width / height) if height > 0 else None,
                    )
                )
        return candidates
