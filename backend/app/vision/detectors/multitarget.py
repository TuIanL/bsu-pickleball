from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from app.schemas.multitarget import MultiTargetDetection, TargetClassName
from app.schemas.tracking import Detection as PlayerDetection


class MultiTargetDetector(Protocol):
    def detect_frame(
        self,
        frame: object,
        frame_index: int,
        timestamp_seconds: float,
        frame_width: int,
        frame_height: int,
    ) -> list[MultiTargetDetection]:
        """Return normalized detections for one decoded video frame."""


class EmptyMultiTargetDetector:
    detail = "多目标检测未配置，跳过球和球拍检测"

    def detect_frame(
        self,
        frame: object,
        frame_index: int,
        timestamp_seconds: float,
        frame_width: int,
        frame_height: int,
    ) -> list[MultiTargetDetection]:
        return []


class FixtureMultiTargetDetector:
    def __init__(
        self,
        detections_by_frame: Mapping[int, Sequence[MultiTargetDetection | Mapping[str, Any]]],
    ) -> None:
        self.detections_by_frame = detections_by_frame

    def detect_frame(
        self,
        frame: object,
        frame_index: int,
        timestamp_seconds: float,
        frame_width: int,
        frame_height: int,
    ) -> list[MultiTargetDetection]:
        detections = self.detections_by_frame.get(frame_index, [])
        normalized: list[MultiTargetDetection] = []
        for detection in detections:
            if isinstance(detection, MultiTargetDetection):
                normalized.append(detection)
            else:
                payload = {
                    "frame_index": frame_index,
                    "timestamp_seconds": timestamp_seconds,
                    "source_width": max(1, int(frame_width)),
                    "source_height": max(1, int(frame_height)),
                    **dict(detection),
                }
                normalized.append(MultiTargetDetection.model_validate(payload))
        return normalized


def normalize_raw_multitarget_detections(
    raw_detections: Sequence[Mapping[str, Any]],
    *,
    frame_index: int,
    timestamp_seconds: float,
    frame_width: int,
    frame_height: int,
    class_map: Mapping[str | int, TargetClassName],
    confidence_thresholds: Mapping[TargetClassName, float],
) -> list[MultiTargetDetection]:
    normalized: list[MultiTargetDetection] = []
    for raw in raw_detections:
        raw_class = raw.get("class_name", raw.get("label", raw.get("class_id")))
        class_name = class_map.get(raw_class)
        if class_name is None and raw_class is not None:
            class_name = class_map.get(str(raw_class))
        if class_name is None:
            continue

        confidence = float(raw.get("confidence", 0.0))
        if confidence < confidence_thresholds.get(class_name, 0.0):
            continue

        try:
            detection = MultiTargetDetection(
                frame_index=int(raw.get("frame_index", frame_index)),
                timestamp_seconds=float(raw.get("timestamp_seconds", timestamp_seconds)),
                class_name=class_name,
                bbox=[float(value) for value in raw["bbox"]],
                confidence=confidence,
                source_width=max(1, int(raw.get("source_width", frame_width))),
                source_height=max(1, int(raw.get("source_height", frame_height))),
                track_id=str(raw["track_id"]) if raw.get("track_id") is not None else None,
            )
        except (KeyError, TypeError, ValueError):
            continue
        normalized.append(detection)
    return normalized


def player_detections_from_multitarget(detections: Sequence[MultiTargetDetection]) -> list[PlayerDetection]:
    return [
        PlayerDetection(
            bbox=detection.bbox,
            confidence=detection.confidence,
            class_name="person",
        )
        for detection in detections
        if detection.class_name == "player"
    ]
