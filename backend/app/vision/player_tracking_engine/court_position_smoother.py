"""球员球场坐标时间平滑 —— 降低帧间抖动和异常跳变。"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class SmoothState:
    track_id: int
    smoothed_x: float = 0.0
    smoothed_y: float = 0.0
    last_frame: int = -1
    last_timestamp: float = 0.0
    gap_frames: int = 0
    outlier_count: int = 0
    active: bool = False


@dataclass
class CourtPositionResult:
    x: float
    y: float
    smoothing_status: str  # smoothed | outlier_clamped | gap_hold | reset_after_gap
    raw_x: float
    raw_y: float


class CourtPositionSmoother:
    def __init__(self, alpha: float = 0.45, max_speed_ft_s: float = 30.0, max_gap_frames: int = 10) -> None:
        self.alpha = alpha
        self.max_speed_ft_s = max_speed_ft_s
        self.max_gap_frames = max_gap_frames
        self._states: dict[int, SmoothState] = {}

    def update(
        self,
        track_id: int,
        frame_index: int,
        x_ft: float,
        y_ft: float,
        timestamp: float,
        confidence: float | None = None,
    ) -> CourtPositionResult:
        _ = confidence
        state = self._states.get(track_id)
        if state is None:
            state = SmoothState(track_id=track_id, smoothed_x=x_ft, smoothed_y=y_ft, last_frame=frame_index, last_timestamp=timestamp, active=True)
            self._states[track_id] = state
            return CourtPositionResult(x=x_ft, y=y_ft, smoothing_status="smoothed", raw_x=x_ft, raw_y=y_ft)

        # Outlier detection
        if self._is_outlier(state, x_ft, y_ft, timestamp):
            state.outlier_count += 1
            state.last_frame = frame_index
            state.last_timestamp = timestamp
            return CourtPositionResult(x=state.smoothed_x, y=state.smoothed_y, smoothing_status="outlier_clamped", raw_x=x_ft, raw_y=y_ft)

        # Gap handling
        gap = frame_index - state.last_frame - 1
        if gap > 0:
            if gap > self.max_gap_frames:
                state.smoothed_x = x_ft
                state.smoothed_y = y_ft
                state.gap_frames = 0
                state.active = True
                state.last_frame = frame_index
                state.last_timestamp = timestamp
                return CourtPositionResult(x=x_ft, y=y_ft, smoothing_status="reset_after_gap", raw_x=x_ft, raw_y=y_ft)
            state.gap_frames = gap
            state.last_frame = frame_index
            state.last_timestamp = timestamp
            return CourtPositionResult(x=state.smoothed_x, y=state.smoothed_y, smoothing_status="gap_hold", raw_x=x_ft, raw_y=y_ft)

        # EMA smoothing
        state.smoothed_x = self.alpha * x_ft + (1.0 - self.alpha) * state.smoothed_x
        state.smoothed_y = self.alpha * y_ft + (1.0 - self.alpha) * state.smoothed_y
        state.last_frame = frame_index
        state.last_timestamp = timestamp
        state.gap_frames = 0
        state.active = True

        return CourtPositionResult(x=state.smoothed_x, y=state.smoothed_y, smoothing_status="smoothed", raw_x=x_ft, raw_y=y_ft)

    def _is_outlier(self, state: SmoothState, x: float, y: float, timestamp: float) -> bool:
        dt = max(timestamp - state.last_timestamp, 0.001)
        dx = x - state.smoothed_x
        dy = y - state.smoothed_y
        speed = math.sqrt(dx * dx + dy * dy) / dt
        return speed > self.max_speed_ft_s

    def reset_track(self, track_id: int) -> None:
        self._states.pop(track_id, None)

    def reset_all(self) -> None:
        self._states.clear()
