"""GlobalPlayerState + GlobalMotionEstimator（4-state constant-velocity Kalman）。

Additive P1：本模块是 `joint_tracking_v2` 的新类,不修改 P0 `GlobalTrackFilter`。

- `GlobalPlayerState`：global player 的位置/速度/uncertainty/lifecycle/cross_view_anchored/view_bindings。
- `GlobalMotionEstimator`：4-state constant-velocity Kalman `[x, y, vx, vy]` + covariance;
  `predict(t) → (position, covariance)` 由 covariance 推导 uncertainty radius。
- lifecycle=confirmed 可仅由单摄稳定达成;`cross_view_anchored=true` 仅当历史 ≥N 次
  稳定双视角 canonical 一致观测(design D7)。
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---- 纯 Python 4x4 矩阵辅助（无外部依赖，手写 Kalman）----


def _mat4_add(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    return [[a[i][j] + b[i][j] for j in range(4)] for i in range(4)]


def _mat4_scale(a: list[list[float]], s: float) -> list[list[float]]:
    return [[a[i][j] * s for j in range(4)] for i in range(4)]


def _mat4_mul(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    return [
        [sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)]
        for i in range(4)
    ]


def _mat4_transpose(a: list[list[float]]) -> list[list[float]]:
    return [[a[j][i] for j in range(4)] for i in range(4)]


def _mat4_vec4(a: list[list[float]], v: list[float]) -> list[float]:
    return [sum(a[i][j] * v[j] for j in range(4)) for i in range(4)]


def _kalman_predict(
    state: list[float],
    cov: list[list[float]],
    dt: float,
    q_scale: float,
) -> tuple[list[float], list[list[float]]]:
    f = [
        [1.0, 0.0, dt, 0.0],
        [0.0, 1.0, 0.0, dt],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]
    new_state = _mat4_vec4(f, state)
    new_cov = _mat4_add(
        _mat4_mul(_mat4_mul(f, cov), _mat4_transpose(f)),
        _constant_velocity_q(dt, q_scale),
    )
    return new_state, new_cov


def _constant_velocity_q(dt: float, q_scale: float) -> list[list[float]]:
    dt2 = dt * dt
    dt3 = dt2 * dt
    dt4 = dt2 * dt2
    q = q_scale * 1.0
    return [
        [q * dt4 / 4.0, 0.0, q * dt3 / 2.0, 0.0],
        [0.0, q * dt4 / 4.0, 0.0, q * dt3 / 2.0],
        [q * dt3 / 2.0, 0.0, q * dt2, 0.0],
        [0.0, q * dt3 / 2.0, 0.0, q * dt2],
    ]


def _kalman_update(
    state: list[float],
    cov: list[list[float]],
    x: float,
    y: float,
    r_scale: float,
) -> tuple[list[float], list[list[float]]]:
    """标准 Kalman 位置测量更新：H = [[1,0,0,0],[0,1,0,0]], R = r_scale * I2。"""
    h = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]]
    r = [[r_scale, 0.0], [0.0, r_scale]]
    innovation = [x - state[0], y - state[1]]
    # S = H P H^T + R
    hp = [[sum(h[i][k] * cov[k][j] for k in range(4)) for j in range(4)] for i in range(2)]
    s = [[sum(hp[i][k] * h[j][k] for k in range(4)) + r[i][j] for j in range(2)] for i in range(2)]
    det = s[0][0] * s[1][1] - s[0][1] * s[1][0]
    s_inv = [[s[1][1] / det, -s[0][1] / det], [-s[1][0] / det, s[0][0] / det]]
    # P H^T (4x2)
    ph_t = [[sum(cov[i][k] * h[j][k] for k in range(4)) for j in range(2)] for i in range(4)]
    # K = (P H^T) S^-1 (4x2)
    k = [[sum(ph_t[i][m] * s_inv[m][j] for m in range(2)) for j in range(2)] for i in range(4)]
    new_state = [state[i] + sum(k[i][j] * innovation[j] for j in range(2)) for i in range(4)]
    # K H (4x4)
    kh = [[k[i][0] * h[0][j] + k[i][1] * h[1][j] for j in range(4)] for i in range(4)]
    # P' = (I - K H) P
    new_cov = [[cov[i][j] - sum(kh[i][m] * cov[m][j] for m in range(4)) for j in range(4)] for i in range(4)]
    return new_state, new_cov


# ---- 数据类型 -------------------------------------------------------------


@dataclass
class ViewBinding:
    """某 global player 在某视角的绑定。"""

    view_player_id: str | None = None
    local_identity_epoch: int = 0
    track_id: int | None = None
    last_seen_take_timestamp_ms: float | None = None
    last_source_frame_index: int | None = None
    quality: float = 0.0
    visibility: str = "missing"  # observed | weak | missing | lost
    lock_state: str | None = None
    tracking_status: str | None = None
    observation_origin: str = "base"
    guidance_id: str | None = None
    donor_view: str | None = None

    def update_visibility(self, now_take_ms: float, weak_after_ms: float, lost_after_ms: float) -> None:
        if self.last_seen_take_timestamp_ms is None:
            self.visibility = "missing"
            return
        gap = now_take_ms - self.last_seen_take_timestamp_ms
        if gap <= weak_after_ms:
            self.visibility = "observed"
        elif gap <= lost_after_ms:
            self.visibility = "weak"
        else:
            self.visibility = "lost"


@dataclass
class GlobalPlayerState:
    """一个 global player 的运行时状态。"""

    global_player_id: str
    x_ft: float = 0.0
    y_ft: float = 0.0
    vx_ft_s: float = 0.0
    vy_ft_s: float = 0.0
    position_uncertainty_ft: float = 1.0
    lifecycle: str = "tentative"  # tentative | confirmed | lost
    cross_view_anchored: bool = False
    view_bindings: dict[str, ViewBinding] = field(default_factory=dict)
    stable_dual_view_count: int = 0  # 历史双视角一致观测次数（anchored 依据）


@dataclass
class _KalmanState:
    state: list[float]  # [x, y, vx, vy]
    cov: list[list[float]]
    last_timestamp_s: float | None = None


class GlobalMotionEstimator:
    """4-state constant-velocity Kalman,按 global player 维护。"""

    def __init__(
        self,
        process_noise: float = 1.0,
        measurement_noise: float = 1.0,
    ) -> None:
        self.process_noise = process_noise
        self.measurement_noise = measurement_noise
        self._states: dict[str, _KalmanState] = {}

    def predict(self, global_id: str, timestamp_s: float) -> tuple[float, float, float] | None:
        """返回 (x, y, uncertainty_radius);无状态返回 None。"""
        ks = self._states.get(global_id)
        if ks is None:
            return None
        dt = max(timestamp_s - (ks.last_timestamp_s or timestamp_s), 0.0)
        state, cov = _kalman_predict(ks.state, ks.cov, dt, self.process_noise)
        return state[0], state[1], _uncertainty_radius(cov)

    def update(self, global_id: str, x_ft: float, y_ft: float, timestamp_s: float) -> tuple[float, float]:
        """吸收一次真实融合测量,返回平滑后位置。"""
        ks = self._states.get(global_id)
        if ks is None:
            ks = _KalmanState(
                state=[x_ft, y_ft, 0.0, 0.0],
                cov=[[1.0, 0, 0, 0], [0, 1.0, 0, 0], [0, 0, 1.0, 0], [0, 0, 0, 1.0]],
                last_timestamp_s=timestamp_s,
            )
            self._states[global_id] = ks
            return x_ft, y_ft
        dt = max(timestamp_s - (ks.last_timestamp_s or timestamp_s), 0.0)
        state, cov = _kalman_predict(ks.state, ks.cov, dt, self.process_noise)
        state, cov = _kalman_update(state, cov, x_ft, y_ft, self.measurement_noise)
        ks.state = state
        ks.cov = cov
        ks.last_timestamp_s = timestamp_s
        return state[0], state[1]

    def reset(self, global_id: str | None = None) -> None:
        if global_id is not None:
            self._states.pop(global_id, None)
        else:
            self._states.clear()


def _uncertainty_radius(cov: list[list[float]]) -> float:
    """由位置协方差（前 2x2）推导 uncertainty radius。"""
    a = cov[0][0]
    b = cov[0][1]
    c = cov[1][1]
    # 2x2 协方差最大特征值平方根
    trace = a + c
    det = a * c - b * b
    lam = max((trace + (trace * trace - 4 * det) ** 0.5) / 2.0, 1e-6)
    return lam ** 0.5


class GlobalPlayerRegistry:
    """持有 GlobalPlayerState 集合 + motion estimator。"""

    def __init__(
        self,
        estimator: GlobalMotionEstimator | None = None,
        anchored_dual_view_count: int = 3,
        confirm_dual_view_count: int = 3,
    ) -> None:
        self.estimator = estimator or GlobalMotionEstimator()
        self.players: dict[str, GlobalPlayerState] = {}
        self.anchored_dual_view_count = anchored_dual_view_count
        self.confirm_dual_view_count = confirm_dual_view_count
        self._next_global = 1

    def get(self, global_id: str) -> GlobalPlayerState | None:
        return self.players.get(global_id)

    def ensure(self, global_id: str) -> GlobalPlayerState:
        if global_id not in self.players:
            self.players[global_id] = GlobalPlayerState(global_player_id=global_id)
        return self.players[global_id]

    def new_global_id(self) -> str:
        gid = f"global_player_{self._next_global}"
        self._next_global += 1
        return gid

    def absorb_measurement(
        self,
        global_id: str,
        x_ft: float,
        y_ft: float,
        timestamp_s: float,
    ) -> tuple[float, float]:
        """吸收融合测量并更新状态、uncertainty。"""
        state = self.ensure(global_id)
        sx, sy = self.estimator.update(global_id, x_ft, y_ft, timestamp_s)
        state.x_ft, state.y_ft = sx, sy
        state.vx_ft_s, state.vy_ft_s = _velocity_from_estimator(self.estimator, global_id)
        pred = self.estimator.predict(global_id, timestamp_s)
        if pred is not None:
            state.position_uncertainty_ft = pred[2]
        return sx, sy

    def predict_all(self, timestamp_s: float) -> dict[str, tuple[float, float, float]]:
        """全部 global player 的 (x, y, uncertainty)。"""
        out: dict[str, tuple[float, float, float]] = {}
        for gid in list(self.players):
            pred = self.estimator.predict(gid, timestamp_s)
            if pred is not None:
                out[gid] = pred
        return out

    def record_dual_consistent(self, global_id: str) -> None:
        """记录一次稳定双视角一致观测（cross_view_anchored 依据）。"""
        state = self.ensure(global_id)
        state.stable_dual_view_count += 1
        if state.stable_dual_view_count >= self.anchored_dual_view_count:
            state.cross_view_anchored = True
        if state.stable_dual_view_count >= self.confirm_dual_view_count:
            state.lifecycle = "confirmed"

    def set_binding(
        self,
        global_id: str,
        view_id: str,
        binding: ViewBinding,
        now_take_ms: float,
        weak_after_ms: float = 300.0,
        lost_after_ms: float = 1000.0,
    ) -> None:
        state = self.ensure(global_id)
        binding.update_visibility(now_take_ms, weak_after_ms, lost_after_ms)
        state.view_bindings[view_id] = binding

    def age_bindings(
        self,
        now_take_ms: float,
        *,
        weak_after_ms: float = 300.0,
        lost_after_ms: float = 1000.0,
    ) -> None:
        """Age every view binding before the current tick's perception.

        Aging is deliberately independent of observation arrival. Callers can
        still distinguish a stale binding from an unavailable target frame via
        the canonical clock status.
        """
        for state in self.players.values():
            for binding in state.view_bindings.values():
                binding.update_visibility(now_take_ms, weak_after_ms, lost_after_ms)


def _velocity_from_estimator(estimator: GlobalMotionEstimator, global_id: str) -> tuple[float, float]:
    ks = estimator._states.get(global_id)  # noqa: SLF001
    if ks is None:
        return 0.0, 0.0
    return ks.state[2], ks.state[3]
