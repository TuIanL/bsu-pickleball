from __future__ import annotations

from collections import defaultdict
from typing import Protocol

from app.schemas.calibration import ImagePoint
from app.schemas.tracking import ImageTrackPoint, PersonDetection
from app.vision.player_tracking_engine.footpoint_estimator import estimate_footpoint


class MultiObjectTracker(Protocol):
    """Interface for associating detections into stable player tracks."""

    def update(self, detections: list[PersonDetection], timestamp_seconds: float) -> list[ImageTrackPoint]:
        """Return image-space track points for the current frame."""


class SimpleDetectionTracker:
    """Deterministic MVP tracker.

    This intentionally avoids solving full re-identification. It assigns stable
    track ids by detection order within each frame, which is enough for schema,
    projection, and metrics integration tests.
    """

    def __init__(self) -> None:
        self._counts: dict[str, int] = defaultdict(int)

    def update(self, detections: list[PersonDetection], timestamp_seconds: float) -> list[ImageTrackPoint]:
        points: list[ImageTrackPoint] = []
        for index, detection in enumerate(detections, start=1):
            track_id = detection.track_hint or f"player-{index}"
            self._counts[track_id] += 1
            footpoint = estimate_footpoint(detection.bbox)
            points.append(
                ImageTrackPoint(
                    frame_index=detection.frame_index,
                    timestamp_seconds=timestamp_seconds,
                    track_id=track_id,
                    image_point=ImagePoint(x=footpoint[0], y=footpoint[1]),
                    confidence=detection.confidence,
                    side="unknown",
                )
            )
        return points


class EmptyTracker:
    def update(self, detections: list[PersonDetection], timestamp_seconds: float) -> list[ImageTrackPoint]:
        return []
