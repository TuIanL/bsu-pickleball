from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

MAX_RENDER_SLOTS = 4

RenderSlot = Literal["slot_1", "slot_2", "slot_3", "slot_4"]

SegmentBreakReason = Literal[
    "start",
    "identity_reset",
    "identity_reassigned",
    "visible_gap",
    "distance_jump",
    "projection_gap",
]


def canonical_player_id(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return text
    if text.lower().startswith("player_"):
        suffix = text.split("_", 1)[1]
        return f"Player_{suffix}"
    return text


@dataclass(frozen=True)
class CourtTrackObservation:
    frame_index: int
    timestamp_seconds: float
    player_id: str
    identity_epoch: int
    track_id: int | None
    raw_x_ft: float
    raw_y_ft: float
    confidence: float
    projection_status: str
    projection_confidence: float | None
    footpoint_method: str | None
    lock_state: str | None
    tracking_status: str


RenderSource = Literal["observed", "interpolated"]


@dataclass(frozen=True)
class RenderFrame:
    frame_index: int
    timestamp_seconds: float
    x_ft: float
    y_ft: float
    source: RenderSource
    confidence: float
    player_id: str
    sequence_index: int = 0
    render_slot: str = ""
    side: str = "unknown"
    segment_id: str = ""
    identity_epoch: int = 0
    source_track_id: int | None = None
    projection_status: str | None = None
    projection_confidence: float | None = None
    footpoint_method: str | None = None


@dataclass(frozen=True)
class RenderPlayerMetadata:
    player_id: str
    render_slot: str
    initial_side: str = "unknown"
    dominant_side: str = "unknown"
    first_frame_index: int = 0
    source_track_ids: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class RenderSegmentMetadata:
    segment_id: str
    player_id: str
    identity_epoch: int
    start_frame_index: int
    end_frame_index: int
    start_timestamp_seconds: float
    end_timestamp_seconds: float
    break_before: SegmentBreakReason
    sample_count: int


class RenderSlotOverflowError(Exception):
    """渲染槽位不足异常——observed_player_count > MAX_RENDER_SLOTS 时抛出。"""

    def __init__(self, observed: int, maximum: int) -> None:
        super().__init__(
            f"观测到 {observed} 名球员，超出最大渲染槽位 {maximum}。"
            f"仅将 player_render_trajectory artifact 标记为 failed。"
        )
        self.observed = observed
        self.maximum = maximum


@dataclass(frozen=True)
class CourtTrackPostProcessResult:
    players: list[RenderPlayerMetadata] = field(default_factory=list)
    segments: list[RenderSegmentMetadata] = field(default_factory=list)
    samples: list[RenderFrame] = field(default_factory=list)


@dataclass(frozen=True)
class ProcessedCourtTracks:
    render_tracks: list[RenderFrame]


@dataclass(frozen=True)
class CourtTrackEvent:
    frame_index: int
    timestamp_seconds: float
    player_id: str
    event_type: str
    previous_track_id: int | None = None
    current_track_id: int | None = None
    reason: str | None = None


@dataclass
class CourtTrackSegment:
    player_id: str
    epoch: int
    observations: list[CourtTrackObservation] = field(default_factory=list)
