"""人体检测器 —— 基于 YOLO 的人员检测，支持懒加载 ultralytics 依赖。"""

from __future__ import annotations

from typing import Any

from app.schemas.tracking import Detection


class PersonDetector:
    """YOLO-backed person detector with lazy optional dependency loading."""

    PERSON_CLASS_ID = 0

    def __init__(
        self,
        model_path: str = "yolov8n.pt",
        conf_threshold: float = 0.25,
        device: str | None = None,
    ) -> None:
        self.model_path = model_path
        self.conf_threshold = conf_threshold
        self.device = device or self._auto_device()
        self._model: Any | None = None

    def detect(self, frame: object) -> list[Detection]:
        model = self._load_model()
        try:
            results = model(frame, verbose=False, conf=self.conf_threshold, device=self.device)
        except TypeError:
            results = model(frame, verbose=False, conf=self.conf_threshold)

        detections: list[Detection] = []
        for result in results:
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue
            for box in boxes:
                class_id = int(self._first_value(getattr(box, "cls", 0)))
                if class_id != self.PERSON_CLASS_ID:
                    continue
                confidence = float(self._first_value(getattr(box, "conf", 0.0)))
                if confidence < self.conf_threshold:
                    continue
                x1, y1, x2, y2 = [float(value) for value in self._xyxy(box)]
                detections.append(
                    Detection(
                        bbox=[x1, y1, x2, y2],
                        confidence=confidence,
                        class_name="person",
                    )
                )
        return detections

    def detect_frame(self, frame: object, frame_index: int | None = None) -> list[Detection]:
        return self.detect(frame)

    def _load_model(self) -> Any:
        if self._model is None:
            try:
                from ultralytics import YOLO  # type: ignore
            except ImportError as exc:
                raise RuntimeError(
                    "ultralytics is not installed; install backend vision extras to run YOLO person detection"
                ) from exc
            self._model = YOLO(self.model_path)
        return self._model

    @staticmethod
    def _auto_device() -> str:
        try:
            import torch  # type: ignore
        except ImportError:
            return "cpu"
        try:
            return "cuda" if bool(torch.cuda.is_available()) else "cpu"
        except Exception:
            return "cpu"

    @staticmethod
    def _first_value(value: Any) -> float:
        try:
            return float(value[0])
        except (TypeError, IndexError, KeyError):
            return float(value)

    @staticmethod
    def _xyxy(box: Any) -> list[float]:
        xyxy = getattr(box, "xyxy", None)
        if xyxy is None:
            raise ValueError("YOLO box is missing xyxy coordinates")
        row = xyxy[0] if hasattr(xyxy, "__getitem__") else xyxy
        return [float(value) for value in row]


class EmptyPersonDetector:
    """Model-free detector used by tests and fallback smoke runs."""

    def detect(self, frame: object) -> list[Detection]:
        return []

    def detect_frame(self, frame: object, frame_index: int | None = None) -> list[Detection]:
        return []


UltralyticsPersonDetector = PersonDetector
