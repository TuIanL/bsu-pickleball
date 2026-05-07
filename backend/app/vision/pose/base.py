from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class PoseKeypoint:
    name: str
    x: float
    y: float
    confidence: float


@dataclass(frozen=True)
class PoseResult:
    frame_index: int
    subject_id: str
    keypoints: list[PoseKeypoint]


class PoseEstimatorAdapter(Protocol):
    def estimate(self, frame_path: str, subject_boxes: list[tuple[float, float, float, float]]) -> list[PoseResult]:
        """Return normalized pose keypoints for detected players."""
