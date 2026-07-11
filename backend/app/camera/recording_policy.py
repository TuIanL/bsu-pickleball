"""RecordingPolicy —— 可配置故障策略"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol


class CoordinatorActionType(str, Enum):
    STOP_ALL = "stop_all"
    RESTART_ALL = "restart_all"
    RESTART_FAILED_TRACK = "restart_failed_track"


@dataclass
class CoordinatorAction:
    type: CoordinatorActionType
    track_ids: list[str] = field(default_factory=list)
    delay_seconds: float = 0


@dataclass
class TrackRuntimeEvent:
    track_id: str
    fragment_id: str
    is_primary: bool
    unexpected: bool
    return_code: int
    restart_count: int


@dataclass
class CaptureRuntimeSnapshot:
    primary_track_id: str
    track_states: dict[str, "TrackRuntimeState"] = field(default_factory=dict)

    @property
    def track_count(self) -> int:
        return len(self.track_states)


@dataclass
class TrackRuntimeState:
    track_id: str
    is_primary: bool
    is_running: bool
    restart_count: int
    fragment_index: int


class RecordingPolicy(Protocol):
    def decide(self, event: TrackRuntimeEvent,
               snapshot: CaptureRuntimeSnapshot) -> list[CoordinatorAction]: ...


RESTART_BUDGET = 5
RESTART_BACKOFF = [1, 2, 4, 8, 15]


def _build_restart_action(track_id: str, restart_count: int) -> CoordinatorAction | None:
    if restart_count >= RESTART_BUDGET:
        return None
    delay = RESTART_BACKOFF[min(restart_count, len(RESTART_BACKOFF) - 1)]
    return CoordinatorAction(type=CoordinatorActionType.RESTART_FAILED_TRACK,
                             track_ids=[track_id], delay_seconds=delay)


class StrictSyncPolicy:
    def decide(self, event: TrackRuntimeEvent,
               snapshot: CaptureRuntimeSnapshot) -> list[CoordinatorAction]:
        all_ids = [s.track_id for s in snapshot.track_states.values()]
        max_restarts = max(s.restart_count for s in snapshot.track_states.values())
        action = _build_restart_action(event.track_id, max_restarts)
        if action is None:
            return []
        return [
            CoordinatorAction(type=CoordinatorActionType.STOP_ALL),
            CoordinatorAction(type=CoordinatorActionType.RESTART_ALL,
                              track_ids=all_ids, delay_seconds=action.delay_seconds),
        ]


class PreservePrimaryPolicy:
    def decide(self, event: TrackRuntimeEvent,
               snapshot: CaptureRuntimeSnapshot) -> list[CoordinatorAction]:
        if event.is_primary:
            all_ids = [s.track_id for s in snapshot.track_states.values()]
            action = _build_restart_action(event.track_id, event.restart_count)
            if action is None:
                return []
            return [
                CoordinatorAction(type=CoordinatorActionType.STOP_ALL),
                CoordinatorAction(type=CoordinatorActionType.RESTART_ALL,
                                  track_ids=all_ids, delay_seconds=action.delay_seconds),
            ]
        action = _build_restart_action(event.track_id, event.restart_count)
        if action is None:
            return []
        return [action]


class IndependentPolicy:
    def decide(self, event: TrackRuntimeEvent,
               snapshot: CaptureRuntimeSnapshot) -> list[CoordinatorAction]:
        action = _build_restart_action(event.track_id, event.restart_count)
        if action is None:
            return []
        return [action]


class SingleTrackRestartPolicy:
    def decide(self, event: TrackRuntimeEvent,
               snapshot: CaptureRuntimeSnapshot) -> list[CoordinatorAction]:
        action = _build_restart_action(event.track_id, event.restart_count)
        if action is None:
            return []
        return [action]
