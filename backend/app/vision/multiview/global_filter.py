"""全局时间滤波（global_filter）—— GlobalTrackFilter：predict/update 单一状态源。

复用 `CourtPositionSmoother` 的模式（EWMA + raw 帧间位移 outlier 判定 + gap 感知），
按 `global_player_id` 维护状态，显式提供 `predict(t)` / `update(measurement)`。

预测职责归属本组件；`PlayerPositionFusion` 不含 `predicted` 状态。关联与融合引用的
global prediction 统一来自 `predict(t)`，避免双重状态估计。
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass
class _GlobalFilterState:
    x: float
    y: float
    last_timestamp_s: float
    last_raw_x: float
    last_raw_y: float
    active: bool = True


class GlobalTrackFilter:
    """按 global player 维护的 EWMA 位置滤波 + 预测。"""

    def __init__(
        self,
        *,
        alpha: float = 0.45,
        max_speed_ft_s: float = 30.0,
        max_hold_s: float = 1.0,
    ) -> None:
        self.alpha = alpha
        self.max_speed_ft_s = max_speed_ft_s
        self.max_hold_s = max_hold_s
        self._states: dict[str, _GlobalFilterState] = {}

    def predict(self, timestamp_s: float) -> dict[str, tuple[float, float]]:
        """返回 active 且在 hold 窗口内的 global player 预测位置（canonical）。"""
        result: dict[str, tuple[float, float]] = {}
        for global_id, state in self._states.items():
            if state.active and (timestamp_s - state.last_timestamp_s) <= self.max_hold_s:
                result[global_id] = (state.x, state.y)
        return result

    def update(
        self,
        global_id: str,
        x_ft: float,
        y_ft: float,
        timestamp_s: float,
    ) -> tuple[float, float]:
        """吸收一次融合测量，返回平滑后的 canonical 位置。

        - 首次出现：直接采用；
        - raw 帧间位移超速（outlier）→ 钳制到当前平滑位置，不吸收异常跳变；
        - 否则 EWMA 平滑。
        """
        state = self._states.get(global_id)
        if state is None:
            state = _GlobalFilterState(
                x=x_ft,
                y=y_ft,
                last_timestamp_s=timestamp_s,
                last_raw_x=x_ft,
                last_raw_y=y_ft,
            )
            self._states[global_id] = state
            return (x_ft, y_ft)

        dt = max(timestamp_s - state.last_timestamp_s, 1e-3)
        speed = math.hypot(x_ft - state.last_raw_x, y_ft - state.last_raw_y) / dt
        state.last_raw_x = x_ft
        state.last_raw_y = y_ft
        state.last_timestamp_s = timestamp_s
        if speed > self.max_speed_ft_s:
            return (state.x, state.y)  # outlier clamped

        state.x = self.alpha * x_ft + (1.0 - self.alpha) * state.x
        state.y = self.alpha * y_ft + (1.0 - self.alpha) * state.y
        return (state.x, state.y)

    def state_for(self, global_id: str) -> tuple[float, float] | None:
        state = self._states.get(global_id)
        if state is None or not state.active:
            return None
        return (state.x, state.y)

    def reset(self, global_id: str | None = None) -> None:
        if global_id is not None:
            self._states.pop(global_id, None)
        else:
            self._states.clear()


def predictions_for(
    filter_: GlobalTrackFilter,
    timestamp_s: float,
    global_ids: Mapping[str, object],
) -> dict[str, tuple[float, float]]:
    """从 filter 取指定 global players 的预测（供关联/融合引用）。"""
    all_predictions = filter_.predict(timestamp_s)
    return {gid: all_predictions[gid] for gid in global_ids if gid in all_predictions}
