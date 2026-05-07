from dataclasses import dataclass


@dataclass(frozen=True)
class TrackPoint:
    frame_index: int
    track_id: str
    label: str
    x: float
    y: float
    confidence: float
