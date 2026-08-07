"""球员球场坐标时间平滑 —— 降低帧间抖动和异常跳变。"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class SmoothState:
    key: str = ""
    smoothed_x: float = 0.0
    smoothed_y: float = 0.0
    last_frame: int = -1
    last_timestamp: float = 0.0
    # 上一帧的原始观测（用于 outlier 判定的真实帧间位移）
    last_raw_x: float | None = None
    last_raw_y: float | None = None
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
    def __init__(
        self,
        alpha: float = 0.45,
        max_speed_ft_s: float = 30.0,
        max_gap_frames: int = 10,
        frame_stride: int = 1,
    ) -> None:
        self.alpha = alpha
        self.max_speed_ft_s = max_speed_ft_s
        self.max_gap_frames = max_gap_frames
        # 抽帧间隔：相邻处理帧的原始帧号差。gap 判断以"额外缺失帧数"为语义，
        # 否则 stride>1 时相邻处理帧会被误判为断帧（gap 恒为 1 → 永远 gap_hold，位置冻结）。
        self.frame_stride = max(1, int(frame_stride))
        self._states: dict[str, SmoothState] = {}

    def update(
        self,
        track_id: int,
        frame_index: int,
        x_ft: float,
        y_ft: float,
        timestamp: float,
        confidence: float | None = None,
        identity_id: str | None = None,
    ) -> CourtPositionResult:
        _ = confidence
        key = identity_id if identity_id else f"track_{track_id}"

        state = self._states.get(key)
        if state is None:
            state = SmoothState(
                key=key,
                smoothed_x=x_ft,
                smoothed_y=y_ft,
                last_frame=frame_index,
                last_timestamp=timestamp,
                last_raw_x=x_ft,
                last_raw_y=y_ft,
                active=True,
            )
            self._states[key] = state
            return CourtPositionResult(x=x_ft, y=y_ft, smoothing_status="smoothed", raw_x=x_ft, raw_y=y_ft)

        if self._is_outlier(state, x_ft, y_ft, timestamp):
            state.outlier_count += 1
            state.last_frame = frame_index
            state.last_timestamp = timestamp
            # 异常帧仍更新"原始观测基线"，避免追赶 smoothed 时被连续误判
            state.last_raw_x = x_ft
            state.last_raw_y = y_ft
            return CourtPositionResult(
                x=state.smoothed_x, y=state.smoothed_y, smoothing_status="outlier_clamped", raw_x=x_ft, raw_y=y_ft
            )

        gap = frame_index - state.last_frame - self.frame_stride
        if gap > 0:
            if gap > self.max_gap_frames:
                state.smoothed_x = x_ft
                state.smoothed_y = y_ft
                state.gap_frames = 0
                state.active = True
                state.last_frame = frame_index
                state.last_timestamp = timestamp
                state.last_raw_x = x_ft
                state.last_raw_y = y_ft
                return CourtPositionResult(x=x_ft, y=y_ft, smoothing_status="reset_after_gap", raw_x=x_ft, raw_y=y_ft)
            state.gap_frames = gap
            state.last_frame = frame_index
            state.last_timestamp = timestamp
            state.last_raw_x = x_ft
            state.last_raw_y = y_ft
            return CourtPositionResult(
                x=state.smoothed_x, y=state.smoothed_y, smoothing_status="gap_hold", raw_x=x_ft, raw_y=y_ft
            )

        state.smoothed_x = self.alpha * x_ft + (1.0 - self.alpha) * state.smoothed_x
        state.smoothed_y = self.alpha * y_ft + (1.0 - self.alpha) * state.smoothed_y
        state.last_frame = frame_index
        state.last_timestamp = timestamp
        state.gap_frames = 0
        state.active = True
        state.last_raw_x = x_ft
        state.last_raw_y = y_ft

        return CourtPositionResult(
            x=state.smoothed_x, y=state.smoothed_y, smoothing_status="smoothed", raw_x=x_ft, raw_y=y_ft
        )

    def _is_outlier(self, state: SmoothState, x: float, y: float, timestamp: float) -> bool:
        # 用相邻两帧的原始观测位移判定异常（真实运动速度），
        # 而不是 raw 与 smoothed 的差：smoothed 滞后时差值会累积，
        # 除以小帧间隔后被误判为超速 → 连续 clamp → 位置冻结。
        dt = max(timestamp - state.last_timestamp, 0.001)
        if state.last_raw_x is None or state.last_raw_y is None:
            return False
        dx = x - state.last_raw_x
        dy = y - state.last_raw_y
        speed = math.sqrt(dx * dx + dy * dy) / dt
        return speed > self.max_speed_ft_s

    def reset_track(self, track_id: int | None = None) -> None:
        if track_id is not None:
            key = f"track_{track_id}"
            self._states.pop(key, None)
        else:
            self.reset_all()

    def reset_identity(self, identity_id: str) -> None:
        self._states.pop(identity_id, None)

    def reset_all(self) -> None:
        self._states.clear()
