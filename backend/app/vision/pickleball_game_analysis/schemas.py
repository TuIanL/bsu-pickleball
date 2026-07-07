"""球轨迹、清洗轨迹和弹跳事件的数据结构。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from math import isfinite
from typing import Any

Point2D = tuple[float, float]


@dataclass(frozen=True)
class BallCandidate:
    image_x: float
    image_y: float
    confidence: float
    width: float | None = None
    height: float | None = None
    area_ratio: float | None = None
    aspect_ratio: float | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def image_xy(self) -> Point2D:
        return (float(self.image_x), float(self.image_y))


@dataclass(frozen=True)
class BallFrameSample:
    frame_index: int
    timestamp_sec: float
    image_xy: Point2D | None
    court_xy: Point2D | None
    confidence: float | None
    visible: bool
    accepted: bool
    interpolated: bool = False
    candidate_count: int = 0
    reject_reason: str | None = None
    source: str = "detector"
    in_bounds: bool | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TrajectoryPoint:
    frame_index: int
    timestamp_sec: float
    image_xy: Point2D | None
    court_xy: Point2D | None
    confidence: float | None = None
    interpolated: bool = False
    source: str = "cleaned"
    in_bounds: bool | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_sample(cls, sample: BallFrameSample) -> "TrajectoryPoint":
        return cls(
            frame_index=sample.frame_index,
            timestamp_sec=sample.timestamp_sec,
            image_xy=sample.image_xy if sample.accepted else None,
            court_xy=sample.court_xy if sample.accepted else None,
            confidence=sample.confidence if sample.accepted else None,
            interpolated=sample.interpolated,
            source=sample.source,
            in_bounds=sample.in_bounds,
            diagnostics=dict(sample.diagnostics),
        )


@dataclass(frozen=True)
class BounceEvent:
    event_id: str
    frame_index: int
    timestamp_sec: float
    image_xy: Point2D
    court_xy: Point2D | None
    confidence: float
    detection_method: str
    diagnostics: dict[str, Any] = field(default_factory=dict)
    rally_id: str | None = None


def coordinate_system_metadata(court_width: float = 20.0, court_length: float = 44.0) -> dict[str, Any]:
    return {
        "image": "pixels",
        "court": "feet",
        "court_width": float(court_width),
        "court_length": float(court_length),
    }


def clean_point(point: Any) -> Point2D | None:
    if point is None:
        return None
    try:
        x, y = point
        x = float(x)
        y = float(y)
    except (TypeError, ValueError):
        return None
    if not isfinite(x) or not isfinite(y):
        return None
    return (x, y)


def to_jsonable(value: Any) -> Any:
    """Convert dataclasses, numpy scalars, tuples, and enums into JSON-safe values."""

    if is_dataclass(value):
        return to_jsonable(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [to_jsonable(item) for item in value]
    if hasattr(value, "item"):
        try:
            return to_jsonable(value.item())
        except (TypeError, ValueError):
            pass
    if hasattr(value, "tolist"):
        try:
            return to_jsonable(value.tolist())
        except (TypeError, ValueError):
            pass
    if isinstance(value, float):
        return value if isfinite(value) else None
    return value


def sample_to_payload(sample: BallFrameSample | TrajectoryPoint) -> dict[str, Any]:
    return to_jsonable(sample)


def event_to_payload(event: BounceEvent) -> dict[str, Any]:
    return to_jsonable(event)
