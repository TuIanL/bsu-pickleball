from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass(frozen=True)
class Detection:
    frame_index: int
    label: str
    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float
    track_hint: Optional[str] = None


class DetectorAdapter(Protocol):
    def detect(self, frame_path: str) -> list[Detection]:
        """Return normalized detections for one frame."""
