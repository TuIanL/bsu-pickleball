from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(frozen=True)
class CourtLineSegmentationResult:
    mask: np.ndarray
    confidence: float
    model_path: str | None = None


class CourtLineSegmentationUnavailable(RuntimeError):
    pass


class CourtLineSegmenter:
    """Lazy Ultralytics segmentation adapter for court-line masks."""

    def __init__(
        self,
        model_path: str | None,
        confidence: float = 0.35,
        device: str | None = None,
    ) -> None:
        self.model_path = model_path
        self.confidence = confidence
        self.device = device
        self._model: Any | None = None

    @property
    def configured(self) -> bool:
        return bool(self.model_path)

    def segment(self, frame: np.ndarray) -> CourtLineSegmentationResult:
        if not self.model_path:
            raise CourtLineSegmentationUnavailable("Court-line model path is not configured")

        path = Path(self.model_path)
        if not path.exists():
            raise CourtLineSegmentationUnavailable(f"Court-line model not found: {self.model_path}")

        model = self._load_model()
        results = model.predict(frame, conf=self.confidence, device=self.device, verbose=False)
        mask, confidence = _result_to_mask(results, frame.shape[:2])
        if mask is None:
            raise CourtLineSegmentationUnavailable("Court-line model produced no usable segmentation mask")
        return CourtLineSegmentationResult(mask=mask, confidence=confidence, model_path=str(path))

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from ultralytics import YOLO  # type: ignore
        except ImportError as exc:
            raise CourtLineSegmentationUnavailable(
                "ultralytics is not installed; install backend vision extras to run court-line segmentation"
            ) from exc

        self._model = YOLO(self.model_path)
        return self._model


def _result_to_mask(results: Any, shape: tuple[int, int]) -> tuple[np.ndarray | None, float]:
    height, width = shape
    combined = np.zeros((height, width), dtype=np.uint8)
    confidences: list[float] = []

    for result in results or []:
        masks = getattr(result, "masks", None)
        boxes = getattr(result, "boxes", None)
        if masks is None or getattr(masks, "data", None) is None:
            continue

        mask_data = masks.data
        try:
            mask_arrays = mask_data.cpu().numpy()
        except AttributeError:
            mask_arrays = np.asarray(mask_data)

        box_conf = getattr(boxes, "conf", None)
        if box_conf is not None:
            try:
                confidences.extend(float(value) for value in box_conf.cpu().numpy())
            except AttributeError:
                confidences.extend(float(value) for value in np.asarray(box_conf))

        for mask in mask_arrays:
            resized = _resize_mask(np.asarray(mask, dtype=float), (height, width))
            combined = np.maximum(combined, (resized > 0.5).astype(np.uint8) * 255)

    if not combined.any():
        return None, 0.0
    confidence = float(np.mean(confidences)) if confidences else 1.0
    return combined, confidence


def _resize_mask(mask: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    height, width = shape
    if mask.shape == (height, width):
        return mask
    try:
        import cv2  # type: ignore
    except ImportError:
        y_index = np.linspace(0, mask.shape[0] - 1, height).astype(int)
        x_index = np.linspace(0, mask.shape[1] - 1, width).astype(int)
        return mask[y_index][:, x_index]
    return cv2.resize(mask, (width, height), interpolation=cv2.INTER_LINEAR)
