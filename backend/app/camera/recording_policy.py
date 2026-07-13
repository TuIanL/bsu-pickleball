"""RecordingPolicy —— 可配置故障策略"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol


class CoordinatorActionType(str, Enum):
    """协调器动作类型枚举：停止全部 / 重启全部 / 仅重启失败轨道"""
    STOP_ALL = "stop_all"
    RESTART_ALL = "restart_all"
    RESTART_FAILED_TRACK = "restart_failed_track"


@dataclass
class CoordinatorAction:
    """协调器执行的一次动作：类型、影响的轨道列表、执行前延迟"""
    type: CoordinatorActionType
    track_ids: list[str] = field(default_factory=list)
    delay_seconds: float = 0


@dataclass
class TrackRuntimeEvent:
    """运行时事件：轨道某分段退出时触发"""
    track_id: str
    fragment_id: str
    is_primary: bool       # 是否为主分析轨道
    unexpected: bool       # 是否非预期退出
    return_code: int       # FFmpeg 返回码
    restart_count: int     # 该轨道已重启次数


@dataclass
class CaptureRuntimeSnapshot:
    """当前录制快照：主轨道 ID 及各轨道状态"""
    primary_track_id: str
    track_states: dict[str, "TrackRuntimeState"] = field(default_factory=dict)

    @property
    def track_count(self) -> int:
        return len(self.track_states)


@dataclass
class TrackRuntimeState:
    """单条轨道的运行时状态快照"""
    track_id: str
    is_primary: bool        # 是否为主分析轨道
    is_running: bool        # 当前是否正在运行
    restart_count: int      # 累计重启次数
    fragment_index: int     # 当前分段序号


class RecordingPolicy(Protocol):
    """录制故障恢复策略协议：根据事件和快照决定动作列表"""
    def decide(self, event: TrackRuntimeEvent,
               snapshot: CaptureRuntimeSnapshot) -> list[CoordinatorAction]: ...


RESTART_BUDGET = 5
RESTART_BACKOFF = [1, 2, 4, 8, 15]


def _build_restart_action(track_id: str, restart_count: int) -> CoordinatorAction | None:
    """根据重启次数生成带指数退避延迟的重启动作，超过预算则返回 None"""
    if restart_count >= RESTART_BUDGET:
        return None
    delay = RESTART_BACKOFF[min(restart_count, len(RESTART_BACKOFF) - 1)]
    return CoordinatorAction(type=CoordinatorActionType.RESTART_FAILED_TRACK,
                             track_ids=[track_id], delay_seconds=delay)


class StrictSyncPolicy:
    """严格同步策略：任一路失败则停止所有并一起重启"""
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
    """优先保主策略：主轨道失败则全部重启，辅轨道失败仅重启自身"""
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
    """独立策略：各路独立重启，互不影响"""
    def decide(self, event: TrackRuntimeEvent,
               snapshot: CaptureRuntimeSnapshot) -> list[CoordinatorAction]:
        action = _build_restart_action(event.track_id, event.restart_count)
        if action is None:
            return []
        return [action]


class SingleTrackRestartPolicy:
    """单轨重启策略：仅重启失败的轨道（与 IndependentPolicy 相同行为）"""
    def decide(self, event: TrackRuntimeEvent,
               snapshot: CaptureRuntimeSnapshot) -> list[CoordinatorAction]:
        action = _build_restart_action(event.track_id, event.restart_count)
        if action is None:
            return []
        return [action]
