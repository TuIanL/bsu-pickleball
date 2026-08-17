"""GlobalPlayerState + GlobalMotionEstimator（4-state constant-velocity Kalman）。

Additive P1：本模块是 `joint_tracking_v2` 的新类,不修改 P0 `GlobalTrackFilter`。

- `GlobalPlayerState`：global player 的位置/速度/uncertainty/lifecycle/cross_view_anchored/view_bindings。
- `GlobalMotionEstimator`：4-state constant-velocity Kalman `[x, y, vx, vy]` + covariance;
  `predict(t) → (position, covariance)` 由 covariance 推导 uncertainty radius。
- lifecycle=confirmed 可仅由单摄稳定达成;`cross_view_anchored=true` 仅当历史 ≥N 次
  稳定双视角 canonical 一致观测(design D7)。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

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
    # ---- available-miss fast path（独立于 visibility 的可用性维度）----
    consecutive_available_misses: int = 0
    last_attempted_take_timestamp_ms: float | None = None
    last_attempted_tick: int | None = None
    last_observed_tick: int | None = None

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

    def record_attempt(self, *, observed: bool, take_ms: float, tick: int) -> None:
        """记账一次 attempted available tick（幂等：相同 tick 不重复记账）。

        - `observed=True`（该 global 在该 view 获得 AssociationUpdate）→ 清零 miss；
        - `observed=False`（attempted available tick 但无 AssociationUpdate）
          → available global-view miss，`consecutive_available_misses += 1`。

        调用方保证仅在 `view_id ∈ view_results` 且 frame available 时调用
        （attempt authority = view_results）；frame 不可用 / view 未被成功尝试
        属于 availability/decode/runtime skip，不调用本方法。
        """
        if tick == self.last_attempted_tick:
            return  # 幂等：相同 canonical tick 重复调用不重复记账
        self.last_attempted_tick = tick
        self.last_attempted_take_timestamp_ms = take_ms
        if observed:
            self.consecutive_available_misses = 0
            self.last_observed_tick = tick
        else:
            self.consecutive_available_misses += 1


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
    # ---- roster 语义（stabilize-joint-global-player-roster）----
    roster_status: str | None = None  # None（非 roster）/ provisional / confirmed
    roster_confirm_ticks: int = 0  # provisional occupant 连续有测量的 tick 数（确认窗口依据）
    last_seen_s: float | None = None  # 最近一次真实测量时间（stale 判定依据）
    association_eligible: bool = True  # False = stale，退出普通紧门匹配（仅强恢复路径可回归）


@dataclass
class _KalmanState:
    state: list[float]  # [x, y, vx, vy]
    cov: list[list[float]]
    last_timestamp_s: float | None = None


@dataclass
class GlobalRosterCandidate:
    """Global Roster 候选：unmatched 正式观测在晋升前的暂存（candidate_N，非 global_player_N）。

    - 归属规则见 `GlobalPlayerRegistry.find_or_create_candidate`（强 key → 弱 prior → geometry → 新建）。
    - 不占 roster slot、不参与 `predict_all()`；满足晋升条件后 `promote_candidate` 占 slot。
    """

    candidate_id: str
    first_tick: int
    last_tick: int
    hit_count: int = 0
    dual_view_hit_count: int = 0
    canonical_x_ft: float = 0.0
    canonical_y_ft: float = 0.0
    local_bindings: dict[str, dict[str, object]] = field(default_factory=dict)  # view_id -> {view_player_id, identity_epoch}
    association_eligibility: bool = True
    tick_views: set[str] = field(default_factory=set)  # 最近一个 tick 内涉及的 view 集合（tick 级双视角判定）
    last_views_tick: int = -1
    last_dual_tick: int = -1  # 最近一次发生跨视角一致的 tick（tick 级累积 dual_view_hit_count）


def _candidate_distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


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
    """持有 GlobalPlayerState 集合 + motion estimator + Global Roster 语义。

    roster 化（stabilize-joint-global-player-roster）：
    - 知晓 `expected_player_count`（单打 2 / 双打 4），正式 global 身份由 `_allocate_roster_slot()` 分配，数量受限；
    - unmatched 观测先进 `candidate_N` 候选池，晋升后占 slot（provisional occupant），
      全部 slot 占用且每 occupant 稳定 K tick 或至少一次可靠 cross-view anchoring 后才进入 `ROSTER_ACTIVE`；
    - `predict_all()` 仅返回 roster 内且具备普通关联资格（非 stale）的 global 预测；
    - stale 玩家（uncertainty / last_seen_age 超阈值）退出普通匹配，仅强恢复路径回归。
    """

    def __init__(
        self,
        estimator: GlobalMotionEstimator | None = None,
        anchored_dual_view_count: int = 3,
        confirm_dual_view_count: int = 3,
        expected_player_count: int = 4,
        roster_confirm_ticks: int = 30,
        candidate_expire_ticks: int = 60,
        candidate_promote_dual_ticks: int = 2,
        candidate_promote_single_ticks: int = 5,
        stale_uncertainty_ft: float = 6.0,
        stale_last_seen_s: float = 10.0,
        candidate_association_radius_ft: float = 3.0,
        reference_view_id: str | None = None,
    ) -> None:
        self.estimator = estimator or GlobalMotionEstimator()
        self.players: dict[str, GlobalPlayerState] = {}
        self.anchored_dual_view_count = anchored_dual_view_count
        self.confirm_dual_view_count = confirm_dual_view_count
        self.expected_player_count = max(1, int(expected_player_count))
        self.roster_confirm_ticks = max(1, int(roster_confirm_ticks))
        self.candidate_expire_ticks = max(1, int(candidate_expire_ticks))
        self.candidate_promote_dual_ticks = max(1, int(candidate_promote_dual_ticks))
        self.candidate_promote_single_ticks = max(1, int(candidate_promote_single_ticks))
        self.stale_uncertainty_ft = stale_uncertainty_ft
        self.stale_last_seen_s = stale_last_seen_s
        self.candidate_association_radius_ft = candidate_association_radius_ft
        self.roster_state: str = "BOOTSTRAPPING"  # BOOTSTRAPPING | ROSTER_ACTIVE
        self._next_candidate = 1
        self.candidates: dict[str, GlobalRosterCandidate] = {}
        self._last_tick: int | None = None
        # (view_id, view_player_id) -> global（弱历史绑定，epoch reset 后仍保留为先验）
        self.historical_bindings: dict[tuple[str, str], str] = {}
        # fix-multiview-cam1-bootstrap-4player D3/D4：reference view 槽位唯一性观测。
        # reference_view_id 为参考视角（display anchor）；槽位 (view_id, view_player_id)
        # 在同一 view 内只允许一个 global 绑定，冲突走 reassociation 而非直接覆盖。
        self.reference_view_id = reference_view_id
        # (view_id, view_player_id) -> 冲突次数（tick 级累计，供 display diagnostics）
        self.reference_slot_conflicts: dict[tuple[str, str], int] = {}
        # 最近一次冲突事件（view_id, view_player_id, incumbent, challenger）
        self.last_reference_slot_conflict: tuple[str, str, str, str] | None = None

    def get(self, global_id: str) -> GlobalPlayerState | None:
        return self.players.get(global_id)

    def ensure(self, global_id: str) -> GlobalPlayerState:
        if global_id not in self.players:
            self.players[global_id] = GlobalPlayerState(global_player_id=global_id)
        return self.players[global_id]

    def _allocate_roster_slot(self) -> str | None:
        """分配一个空闲 roster slot（`global_player_1..expected_player_count`）；满返回 None。

        取代公开的 `new_global_id()`：普通 unmatched 观测不可达；仅 candidate 晋升 / roster 重建时使用。
        """
        for index in range(1, self.expected_player_count + 1):
            gid = f"global_player_{index}"
            if gid not in self.players:
                return gid
        return None

    # ---- 候选池（GlobalRosterCandidate）----

    def find_or_create_candidate(
        self,
        *,
        view_id: str,
        view_player_id: str,
        identity_epoch: int,
        canonical_x_ft: float,
        canonical_y_ft: float,
        tick: int,
        local_track_id: int | None = None,
    ) -> str:
        """按归属规则把一次 unmatched 观测归入既有 candidate 或新建 candidate。

        优先级：①同 `(view_id, view_player_id, epoch)` 复用（强 key）；②跨 epoch 的
        `(view_id, view_player_id)` 弱 prior；③canonical geometry 邻域；④否则新建。
        同 tick 同 candidate 每 view 至多接受一个 observation（由调用方在创建后调用
        `note_candidate_observation` 累积，本方法只在创建/复用层面保证归属）。
        """
        strong_key = (view_id, view_player_id, identity_epoch)
        for cid, cand in self.candidates.items():
            if not cand.association_eligibility:
                continue
            binding = cand.local_bindings.get(view_id)
            if binding is not None and binding.get("view_player_id") == view_player_id and int(binding.get("identity_epoch", -1)) == identity_epoch:
                return cid  # ① 强 key
        weak_key = (view_id, view_player_id)
        for cid, cand in self.candidates.items():
            binding = cand.local_bindings.get(view_id)
            if binding is not None and binding.get("view_player_id") == view_player_id:
                return cid  # ② 弱 prior（仅当该 view 历史绑定同 local 身份）
        pos = (canonical_x_ft, canonical_y_ft)
        best_cid: str | None = None
        best_dist = float("inf")
        for cid, cand in self.candidates.items():
            if cand.local_bindings.get(view_id) is not None:
                continue  # 排除同 view 已绑定候选：同 view 两个不同 local players 不得合并（tentative bootstrap view uniqueness）
            dist = _candidate_distance(pos, (cand.canonical_x_ft, cand.canonical_y_ft))
            if dist <= self.candidate_association_radius_ft and dist < best_dist:
                best_cid = cid
                best_dist = dist
        if best_cid is not None:
            return best_cid  # ③ geometry 邻域（仅跨 view）
        cid = f"candidate_{self._next_candidate}"
        self._next_candidate += 1
        self.candidates[cid] = GlobalRosterCandidate(
            candidate_id=cid,
            first_tick=tick,
            last_tick=tick,
            canonical_x_ft=canonical_x_ft,
            canonical_y_ft=canonical_y_ft,
            local_bindings={
                view_id: {"view_player_id": view_player_id, "identity_epoch": identity_epoch, "track_id": local_track_id}
            },
            last_views_tick=tick,
            tick_views={view_id},
        )
        return cid  # ④ 新建

    def note_candidate_observation(
        self,
        candidate_id: str,
        *,
        view_id: str,
        view_player_id: str,
        identity_epoch: int,
        canonical_x_ft: float,
        canonical_y_ft: float,
        tick: int,
        local_track_id: int | None = None,
    ) -> None:
        """累积一次 candidate 观测证据（同 tick 同 view 至多一次，由调用方保证）。"""
        cand = self.candidates.get(candidate_id)
        if cand is None:
            return
        cand.last_tick = tick
        cand.hit_count += 1
        cand.canonical_x_ft = canonical_x_ft
        cand.canonical_y_ft = canonical_y_ft
        if cand.last_views_tick != tick:
            cand.last_views_tick = tick
            cand.tick_views = {view_id}
        else:
            cand.tick_views.add(view_id)
            if len(cand.tick_views) == 2 and cand.last_dual_tick != tick:
                cand.dual_view_hit_count += 1
                cand.last_dual_tick = tick
        cand.local_bindings.setdefault(
            view_id,
            {"view_player_id": view_player_id, "identity_epoch": identity_epoch, "track_id": local_track_id},
        )

    def promote_candidate(self, candidate_id: str, tick: int) -> str | None:
        """晋升 candidate 为 provisional roster occupant（占 slot）；无空闲 slot 返回 None。"""
        cand = self.candidates.get(candidate_id)
        if cand is None:
            return None
        gid = self._allocate_roster_slot()
        if gid is None:
            return None
        state = self.ensure(gid)
        state.x_ft, state.y_ft = cand.canonical_x_ft, cand.canonical_y_ft
        state.lifecycle = "tentative"
        state.roster_status = "provisional"
        state.last_seen_s = None
        state.association_eligible = True
        for view_id, binding in cand.local_bindings.items():
            player_id = binding.get("view_player_id")
            epoch = int(binding.get("identity_epoch") or 0)
            if player_id:
                self.historical_bindings[(view_id, player_id)] = gid
        self.candidates.pop(candidate_id, None)
        return gid

    def expire_candidates(self, tick: int) -> None:
        """过期清理未晋升候选（不影响 roster）。"""
        stale = [cid for cid, cand in self.candidates.items() if tick - cand.last_tick > self.candidate_expire_ticks]
        for cid in stale:
            self.candidates.pop(cid, None)

    def _maybe_confirm_roster(self) -> None:
        """roster 确认：全部 slot 占用且每 occupant 稳定 K tick 或 ≥1 次可靠 cross-view anchoring → ROSTER_ACTIVE。"""
        if self.roster_state != "BOOTSTRAPPING":
            return
        occupants = [s for s in self.players.values() if s.roster_status in ("provisional", "confirmed")]
        if len(occupants) < self.expected_player_count:
            return
        if not all(
            s.roster_confirm_ticks >= self.roster_confirm_ticks or s.cross_view_anchored for s in occupants
        ):
            return
        for state in occupants:
            state.roster_status = "confirmed"
        self.roster_state = "ROSTER_ACTIVE"

    def update_stale_eligibility(self, now_s: float) -> None:
        """stale 判定：uncertainty / last_seen_age 超阈值 → 退出普通关联；确认窗口内 provisional 不受影响。

        单视图活跃豁免（fix-multiview-single-view-fallback）：玩家存在任一 view binding
        为 observed/weak 且 last_seen_s 新鲜（now - last_seen <= stale_last_seen_s）时，
        SHALL 保持 association_eligible=True——跨视图 binding 缺失（如仅 cam_1 观测、
        cam_2 过期）SHALL NOT 使单视图活跃玩家退出普通关联。豁免仅作用于 last_seen 维度；
        position_uncertainty 超阈值 SHALL 仍无条件置 stale（不可靠预测不吸附观测）。
        """
        for state in self.players.values():
            if state.roster_status is None:
                continue
            any_view_fresh = (
                any(binding.visibility in ("observed", "weak") for binding in state.view_bindings.values())
                and state.last_seen_s is not None
                and (now_s - state.last_seen_s <= self.stale_last_seen_s)
            )
            stale = state.position_uncertainty_ft > self.stale_uncertainty_ft or (
                state.last_seen_s is not None
                and now_s - state.last_seen_s > self.stale_last_seen_s
                and not any_view_fresh
            )
            state.association_eligible = not stale

    def reset_roster(self) -> None:
        """销毁并重建 roster（仅 new_match / roster_reset / participant-change 触发）。"""
        self.players.clear()
        self.candidates.clear()
        self.historical_bindings.clear()
        self._next_candidate = 1
        self.roster_state = "BOOTSTRAPPING"
        self._last_tick = None

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
        state.last_seen_s = timestamp_s
        if state.roster_status == "provisional":
            state.roster_confirm_ticks += 1
            self._maybe_confirm_roster()
        return sx, sy

    def predict_all(self, timestamp_s: float) -> dict[str, tuple[float, float, float]]:
        """roster 内且具备普通关联资格（非 stale）的 global 预测（不含候选池）。"""
        out: dict[str, tuple[float, float, float]] = {}
        for gid in list(self.players):
            state = self.players[gid]
            if state.roster_status is None or not state.association_eligible:
                continue
            pred = self.estimator.predict(gid, timestamp_s)
            if pred is not None:
                out[gid] = pred
        return out

    def predict_for(self, global_id: str, timestamp_s: float) -> tuple[float, float, float] | None:
        """任意 roster 玩家（含 stale）的预测，供弱历史绑定 / reacquire 使用。"""
        state = self.players.get(global_id)
        if state is None or state.roster_status is None:
            return None
        return self.estimator.predict(global_id, timestamp_s)

    def record_dual_consistent(self, global_id: str) -> None:
        """记录一次稳定双视角一致观测（cross_view_anchored 依据）。"""
        state = self.ensure(global_id)
        state.stable_dual_view_count += 1
        if state.stable_dual_view_count >= self.anchored_dual_view_count:
            state.cross_view_anchored = True
        if state.stable_dual_view_count >= self.confirm_dual_view_count:
            state.lifecycle = "confirmed"
        if state.roster_status in ("provisional", "confirmed"):
            self._maybe_confirm_roster()

    def set_binding(
        self,
        global_id: str,
        view_id: str,
        binding: ViewBinding,
        now_take_ms: float,
        weak_after_ms: float = 300.0,
        lost_after_ms: float = 1000.0,
    ) -> bool:
        """设置某 view 的绑定；槽位唯一性冲突时返回 False（不覆盖）。

        fix-multiview-cam1-bootstrap-4player D3（扩展至全部 view）：同一 view 内
        (view_id, view_player_id) 槽位只允许一个 global 绑定——每个 view 的 local
        identity 槽位（Player_N）唯一对应一个物理球员。当 binding 的 view_player_id
        非空且该槽位已被其他 roster 玩家占用时，本调用记录 slot_conflict 事件并
        返回 False，MUST NOT 直接覆盖 incumbent（由其走 PendingReassociation 强证据切换）。

        2026-08-16 修复残留：原实现仅保护 reference view，导致非 reference view
        （如 cam_2）的槽位可被第二个 global 抢占 → gid 绑定冲突 → fused overlay
        该 player 证据丢失。现扩展至所有 view。
        """
        state = self.ensure(global_id)
        # 槽位唯一性检查（任意 view + 有 view_player_id 时）
        if binding.view_player_id:
            incumbent = self.reference_slot_occupant(view_id, binding.view_player_id)
            if incumbent is not None and incumbent != global_id:
                key = (view_id, binding.view_player_id)
                self.reference_slot_conflicts[key] = self.reference_slot_conflicts.get(key, 0) + 1
                self.last_reference_slot_conflict = (view_id, binding.view_player_id, incumbent, global_id)
                return False
        binding.update_visibility(now_take_ms, weak_after_ms, lost_after_ms)
        state.view_bindings[view_id] = binding
        return True

    def reference_slot_occupant(self, view_id: str, view_player_id: str) -> str | None:
        """返回 (view_id, view_player_id) 槽位的当前占用 global（无则 None）。

        遍历 roster 玩家（provisional/confirmed）的 view_bindings，找 view_player_id
        匹配的绑定者。仅查询不修改。适用于任意 view（reference 与非 reference，
        见 set_binding 槽位唯一性）。
        """
        if not view_player_id:
            return None
        for gid, state in self.players.items():
            if state.roster_status not in ("provisional", "confirmed"):
                continue
            binding = state.view_bindings.get(view_id)
            if binding is not None and binding.view_player_id == view_player_id:
                return gid
        return None

    def release_view_slot(self, view_id: str, view_player_id: str) -> str | None:
        """解除 (view_id, view_player_id) 槽位的占用（仅解除匹配的 binding 的 view_player_id）。

        供 association 层**强证据 reassociation** 使用：同一 view 内 local 身份经
        连续 N 帧强证据确认切换到另一 global 时，先解除 incumbent 的槽位占用，
        再让 challenger 绑定——否则唯一性保护会错误拦截合法切换。

        返回被解除的 global（槽位本为空返回 None）。
        """
        if not view_player_id:
            return None
        for gid, state in self.players.items():
            binding = state.view_bindings.get(view_id)
            if binding is not None and binding.view_player_id == view_player_id:
                state.view_bindings[view_id] = replace(binding, view_player_id=None)
                return gid
        return None

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
