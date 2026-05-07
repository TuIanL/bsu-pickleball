from __future__ import annotations

from typing import Protocol

from app.schemas.tracking import PersonDetection


class PersonDetector(Protocol):
    """Interface for normalized person detection over video frames."""

    def detect_frame(self, frame: object, frame_index: int) -> list[PersonDetection]:
        """Return person detections for one decoded frame."""


class EmptyPersonDetector:
    """Model-free detector used by tests and MVP smoke runs."""

    def detect_frame(self, frame: object, frame_index: int) -> list[PersonDetection]:
        return []


class UltralyticsPersonDetector:
    """Optional YOLO-backed detector placeholder.

    The import is delayed so the backend can run without ultralytics installed.
    """

    def __init__(self, model_path: str = "yolo11n.pt", confidence: float = 0.25) -> None:
        self.model_path = model_path
        self.confidence = confidence
        self._model = None

    def _load(self) -> object:
        if self._model is None:
            try:
                from ultralytics import YOLO  # type: ignore
            except ImportError as exc:
                raise RuntimeError("ultralytics is not installed; install the optional vision extras") from exc
            self._model = YOLO(self.model_path)
        return self._model

    def detect_frame(self, frame: object, frame_index: int) -> list[PersonDetection]:
        model = self._load()
        results = model(frame, verbose=False, conf=self.confidence)
        detections: list[PersonDetection] = []

        for result in results:
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue
            for box in boxes:
                cls = int(box.cls[0])
                if cls != 0:
                    continue
                x1, y1, x2, y2 = [float(value) for value in box.xyxy[0]]
                detections.append(
                    PersonDetection(
                        frame_index=frame_index,
                        confidence=float(box.conf[0]),
                        bbox={"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                    )
                )

        return detections
