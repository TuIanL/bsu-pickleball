"""GlobalPlayerAssociator —— 观测→global 分配（roster 化）。

不修改 P0 `CrossViewPlayerAssociator`(reference-centric,仅 late_fusion_v1 使用)。
本模块在 `joint_tracking_v2` 中做 global-centric 分配，并在
`stabilize-joint-global-player-roster` 中升级为 fixed roster 语义：

    GlobalState.predict(t)
        ├── assign Cam1 observations → roster global states
        ├── assign Cam2 observations → roster global states
        ├── guided expected-global 强约束（guided_roi 观测专用）
        ├── unmatched → continuity（强绑定 → 弱历史绑定）
        ├── unmatched → candidate pool（roster 未满）/ unresolved（roster 已满）
        └── fusion/update GlobalState(t)

关键规则：
- **禁止 unmatched 调用 new_global_id**：roster 建立后不创建 G5；
- uncertainty-aware gate（`gate = min(max_reacquire, base + scale×uncertainty)`），
  换人尝试用更严门；
- PendingReassociation 多帧强证据迟滞（challenger cost 优于 incumbent 超 switch_margin
  且连续一致，累计 reassociation_frames 帧才切换）；
- 两级 continuity：强绑定 `(view,pid,epoch)` + 弱历史绑定 `(view,pid)`（epoch reset 后可
  经 geometry 重新证明回原 global）；
- stale roster 玩家（registry.predict_all 已过滤）不参与普通匹配，弱历史绑定仍可找回。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.vision.multiview.association import min_cost_matching
from app.vision.multiview.court_frame import CourtOrientation, local_to_canonical
from app.vision.multiview.global_state import GlobalPlayerRegistry, ViewBinding
from app.vision.multiview.quality import pair_consistency


@dataclass
class JointObservation:
    """一次 joint 观测（JointViewObservation 的球场分量运行时表示）。"""

    view_id: str
    source_frame_index: int
    take_timestamp_ms: float
    local_x_ft: float
    local_y_ft: float
    canonical_x_ft: float | None = None
    canonical_y_ft: float | None = None
    view_player_id: str = ""
    local_identity_epoch: int = 0
    track_id: int | None = None
    confidence: float = 0.0
    projection_confidence: float | None = None
    detection_origin: str = "base"  # base | guided_roi
    guidance_id: str | None = None
    donor_view: str | None = None
    expected_global_player_id: str | None = None
    pre_gate_residual_ft: float | None = None
    intrinsic_quality: float | None = None
    recovery_episode_id: str | None = None
    source_timestamp_ms: float | None = None
    mapped_take_timestamp_ms: float | None = None
    selection_error_ms: float | None = None
    timing_authority: str = "missing"
    sync_quality: str = "unknown"
    view_status: str = "available"
    tracking_status: str = "detected"
    lock_state: str | None = None
    bbox: list[float] | None = None
    image_footpoint: tuple[float, float] | None = None


@dataclass
class AssociationUpdate:
    """一次关联结果:观测被分配到某 global。"""

    global_id: str
    view_id: str
    observation: JointObservation
    confidence: float
    tentative: bool = False


@dataclass
class AssociationDecision:
    """只读 per-observation 关联决策记录（player-display-diagnostics 消费）。

    仅在既有决策分支附加记录，不改变 `process_tick()` 的算法结果与门限。
    `result` 为 `assigned | rejected | pending | candidate`；`global_id` 仅在
    分配/保持时非空。
    """

    view_id: str
    observation_key: str
    result: str  # assigned | rejected | pending | candidate
    global_id: str | None = None
    reason: str | None = None
    tentative: bool = False


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


class GlobalPlayerAssociator:
    """global-centric 观测分配器（roster 化：unmatched → 候选池 / unresolved，禁止 new_global）。"""

    def __init__(
        self,
        registry: GlobalPlayerRegistry,
        max_association_distance_ft: float = 3.0,
        prediction_bias_ft: float = 0.5,
        local_identity_switch_penalty: float = 0.25,
        guidance_global_mismatch_penalty: float = 0.5,
        # ---- uncertainty-aware gate（D5）----
        base_gate_ft: float = 3.0,
        max_reacquire_gate_ft: float = 8.0,
        uncertainty_scale: float = 1.0,
        switch_gate_ft: float = 2.0,
        # ---- PendingReassociation（D6）----
        switch_margin: float = 0.15,
        reassociation_frames: int = 5,
    ) -> None:
        self.registry = registry
        self.max_association_distance_ft = max_association_distance_ft
        self.prediction_bias_ft = prediction_bias_ft
        self.local_identity_switch_penalty = local_identity_switch_penalty
        self.guidance_global_mismatch_penalty = guidance_global_mismatch_penalty
        self.base_gate_ft = base_gate_ft
        self.max_reacquire_gate_ft = max_reacquire_gate_ft
        self.uncertainty_scale = uncertainty_scale
        self.switch_gate_ft = switch_gate_ft
        self.switch_margin = switch_margin
        self.reassociation_frames = max(1, int(reassociation_frames))
        self.diagnostics: dict[str, int] = {}
        # 只读决策可观测：最近一次 process_tick 的 per-observation 决策记录
        self.last_tick_decisions: list[AssociationDecision] = []
        # (view_id, view_player_id, identity_epoch) -> global_id.
        # Track-only observations remain compatible through a synthetic key.
        self.mapping: dict[tuple[str, str, int], str] = {}
        # mapping_key -> challenger_gid -> 连续强证据帧数（PendingReassociation）
        self._pending_reassoc: dict[tuple[str, str, int], dict[str, int]] = {}

    @staticmethod
    def observation_key(obs: JointObservation) -> str:
        return obs.view_player_id or str(obs.track_id)

    def _record_decision(
        self,
        obs: JointObservation,
        result: str,
        *,
        global_id: str | None = None,
        reason: str | None = None,
        tentative: bool = False,
    ) -> None:
        """附加一条只读 AssociationDecision（不改任何算法行为）。"""
        self.last_tick_decisions.append(
            AssociationDecision(
                view_id=obs.view_id,
                observation_key=self.observation_key(obs),
                result=result,
                global_id=global_id,
                reason=reason,
                tentative=tentative,
            )
        )

    @classmethod
    def mapping_key(cls, obs: JointObservation) -> tuple[str, str, int]:
        return (obs.view_id, cls.observation_key(obs), int(obs.local_identity_epoch))

    # ---- uncertainty-aware gate（D5）----

    def _pair_gate_ft(self, obs: JointObservation, gid: str, predictions) -> float:
        """按关联状态返回门宽：已绑定保持优先（宽门容忍减速漂移）/ 换人尝试严格门 / reacquire 随 uncertainty 扩展。

        fix-multiview-cam1-bootstrap-4player 残留修复（2026-08-16 二次修正）：incumbent
        分支原用固定 base_gate_ft（3.0）——Kalman 常速模型对减速球员预测持续超前
        （tick 115 差 0.8ft 累积到 tick 139 差 3.24ft），一旦略超 base_gate 观测被拒
        → 不 absorb → 预测更超前 → 死锁（P4 fused overlay 消失、gid_1 预测漂出球场）。

        已绑定观测（mapping incumbent）应**保持优先**：门宽放宽到 max_reacquire_gate，
        容忍正常减速/转向导致的预测漂移，让观测持续修正 Kalman；身份正确性由
        challenger 严格 switch_gate + PendingReassociation 强证据切换把关，不受影响。
        """
        incumbent = self.mapping.get(self.mapping_key(obs))
        if incumbent == gid:
            # 已绑定：保持优先（宽门容忍预测漂移；>max_reacquire 的跳变仍触发 reassociation 评估）
            return self.max_reacquire_gate_ft
        if incumbent is not None and incumbent != gid:
            return self.switch_gate_ft
        unc = 1.0
        pred = predictions.get(gid)
        if pred is not None:
            unc = pred[2] if len(pred) >= 3 else 1.0
        return min(self.max_reacquire_gate_ft, self.base_gate_ft + self.uncertainty_scale * unc)

    def process_tick(
        self,
        observations: list[JointObservation],
        timestamp_s: float,
        orientation_by_view: Mapping[str, CourtOrientation],
        tick: int | None = None,
    ) -> list[AssociationUpdate]:
        """把两路观测分配到 roster global states;返回关联更新。

        unmatched 分流（roster 化）：
        - guided 强约束（detection_origin=guided_roi + expected_global_player_id）→ 只尝试 expected；
        - 强绑定 continuity（(view,pid,epoch)）→ 几何可行则复用；
        - 弱历史绑定（(view,pid)）→ 需重新证明（可含 stale 玩家）；
        - roster 未满（BOOTSTRAPPING）→ 候选池（candidate_N）；roster 已满（ROSTER_ACTIVE）→ unresolved。
        """
        tick = tick if tick is not None else (max((o.source_frame_index for o in observations), default=0))
        # 只读决策可观测：每 tick 重置，供 display diagnostics 消费
        self.last_tick_decisions = []
        # 1) canonical 化 + 清理失效强绑定
        for obs in observations:
            identity_key = self.observation_key(obs)
            for old_key in list(self.mapping):
                if old_key[0] == obs.view_id and old_key[1] == identity_key and old_key[2] != obs.local_identity_epoch:
                    self.mapping.pop(old_key, None)
            if obs.canonical_x_ft is None:
                cx, cy = local_to_canonical(
                    obs.local_x_ft, obs.local_y_ft, orientation_by_view.get(obs.view_id)
                )
                obs.canonical_x_ft, obs.canonical_y_ft = cx, cy

        predictions = self.registry.predict_all(timestamp_s)
        updates: list[AssociationUpdate] = []
        assigned_obs: set[int] = set()  # id(obs)

        # 2) guided 强约束：guided_roi + expected_global 的观测只尝试 expected（D7 / tasks 5.2）
        for obs in observations:
            if obs.detection_origin != "guided_roi" or not obs.expected_global_player_id:
                continue
            expected = obs.expected_global_player_id
            if expected not in self.registry.players or expected not in predictions:
                self.diagnostics["guided_expected_missing"] = self.diagnostics.get("guided_expected_missing", 0) + 1
                self._record_decision(obs, "rejected", reason="guided_expected_missing")
                assigned_obs.add(id(obs))
                continue
            px, py = predictions[expected][0], predictions[expected][1]
            geometry = _dist((obs.canonical_x_ft or 0.0, obs.canonical_y_ft or 0.0), (px, py))
            gate = self._pair_gate_ft(obs, expected, predictions)
            if geometry <= gate:
                binding_ok = self.registry.set_binding(
                    expected, obs.view_id,
                    ViewBinding(
                        view_player_id=obs.view_player_id or None,
                        local_identity_epoch=obs.local_identity_epoch,
                        track_id=obs.track_id,
                        last_seen_take_timestamp_ms=obs.take_timestamp_ms,
                        last_source_frame_index=obs.source_frame_index,
                        quality=obs.intrinsic_quality if obs.intrinsic_quality is not None else obs.confidence,
                        visibility="observed",
                        observation_origin=obs.detection_origin,
                        guidance_id=obs.guidance_id,
                        donor_view=obs.donor_view,
                    ),
                    obs.take_timestamp_ms,
                )
                if not binding_ok:
                    # fix-multiview-cam1-bootstrap-4player D3：reference 槽位已被其他
                    # global 占用 → 不覆盖，记录冲突事件；观测落入 unresolved（后续轮次处理）。
                    self._record_decision(
                        obs, "rejected", global_id=expected, reason="reference_slot_conflict"
                    )
                    self.diagnostics["reference_slot_conflict"] = (
                        self.diagnostics.get("reference_slot_conflict", 0) + 1
                    )
                    assigned_obs.add(id(obs))
                    continue
                self.mapping[self.mapping_key(obs)] = expected
                updates.append(AssociationUpdate(expected, obs.view_id, obs, 1.0 / (1.0 + geometry)))
                assigned_obs.add(id(obs))
                self.diagnostics["guided_expected_preserved"] = self.diagnostics.get("guided_expected_preserved", 0) + 1
                self._record_decision(obs, "assigned", global_id=expected, reason="guided_expected_preserved")
            else:
                # 几何不可行 → reject（不转投其他 global）
                self.diagnostics["guided_expected_rejected"] = self.diagnostics.get("guided_expected_rejected", 0) + 1
                self._record_decision(obs, "rejected", reason="guided_expected_rejected")
                assigned_obs.add(id(obs))

        # 3) 逐 view 用 min_cost_matching 把剩余观测分配给预测 global（per-pair uncertainty-aware gate）
        for view_id, _orientation in orientation_by_view.items():
            view_obs = [o for o in observations if id(o) not in assigned_obs and o.view_id == view_id]
            pred_globals = [gid for gid in self.registry.players if gid in predictions]
            if not view_obs or not pred_globals:
                continue
            ranking: dict[str, dict[str, float]] = {}
            feasibility: dict[str, dict[str, float]] = {}
            observations_by_key: dict[str, JointObservation] = {}
            for obs in view_obs:
                key = f"{self.observation_key(obs)}@{obs.local_identity_epoch}"
                observations_by_key[key] = obs
                ranking[key] = {}
                feasibility[key] = {}
                for gid in pred_globals:
                    px, py = predictions[gid][0], predictions[gid][1]
                    geometry = _dist((obs.canonical_x_ft or 0.0, obs.canonical_y_ft or 0.0), (px, py))
                    gate = self._pair_gate_ft(obs, gid, predictions)
                    feasibility[key][gid] = geometry / max(gate, 1e-3)  # 归一化门：<=1 可行
                    cost = geometry + self.prediction_bias_ft * geometry
                    if self.mapping.get(self.mapping_key(obs)) not in (None, gid):
                        cost += self.local_identity_switch_penalty
                    if obs.expected_global_player_id and obs.expected_global_player_id != gid:
                        cost += self.guidance_global_mismatch_penalty
                    ranking[key][gid] = cost
            obs_keys = [f"{self.observation_key(o)}@{o.local_identity_epoch}" for o in view_obs]
            pairs = min_cost_matching(
                obs_keys,
                pred_globals,
                ranking,
                feasibility_cost=feasibility,
                max_feasibility_cost=1.0,
            )
            for key, gid in pairs:
                obs = observations_by_key[key]
                incumbent = self.mapping.get(self.mapping_key(obs))
                if incumbent is not None and incumbent != gid:
                    # PendingReassociation（D6）：challenger 需连续强证据（margin + 连续一致）
                    incumbent_cost = ranking[key].get(incumbent, float("inf"))
                    challenger_cost = ranking[key][gid]
                    pkey = self.mapping_key(obs)
                    pending = self._pending_reassoc.setdefault(pkey, {})
                    prev_challenger = next(iter(pending), None) if pending else None
                    if (
                        challenger_cost + self.switch_margin < incumbent_cost
                        and (prev_challenger is None or prev_challenger == gid)
                    ):
                        pending[gid] = pending.get(gid, 0) + 1
                        if pending[gid] >= self.reassociation_frames:
                            self.diagnostics["reassociated"] = self.diagnostics.get("reassociated", 0) + 1
                            pending.clear()
                            # fix-multiview-cam1-bootstrap-4player：强证据切换允许覆盖
                            # 槽位（先 release incumbent），避免唯一性保护拦截合法 reassociation。
                            if self._accept_pair(
                                obs, gid, feasibility[key][gid], updates, override_slot=True
                            ):
                                assigned_obs.add(id(obs))
                                self._record_decision(obs, "assigned", global_id=gid, reason="reassociated")
                            else:
                                self._record_decision(
                                    obs, "rejected", global_id=gid, reason="reference_slot_conflict"
                                )
                        else:
                            self.diagnostics["reassoc_pending"] = self.diagnostics.get("reassoc_pending", 0) + 1
                            if self._accept_pair(
                                obs, incumbent, feasibility[key].get(incumbent, 1.0), updates, tentative=True
                            ):
                                assigned_obs.add(id(obs))
                                self._record_decision(
                                    obs, "pending", global_id=incumbent, reason="reassoc_pending", tentative=True
                                )
                            else:
                                self._record_decision(
                                    obs, "rejected", global_id=incumbent, reason="reference_slot_conflict"
                                )
                    else:
                        pending.clear()
                        if self._accept_pair(
                            obs, incumbent, feasibility[key].get(incumbent, 1.0), updates, tentative=True
                        ):
                            assigned_obs.add(id(obs))
                            self._record_decision(
                                obs, "assigned", global_id=incumbent, reason="incumbent_kept", tentative=True
                            )
                        else:
                            self._record_decision(
                                obs, "rejected", global_id=incumbent, reason="reference_slot_conflict"
                            )
                else:
                    if incumbent == gid:
                        self._pending_reassoc.pop(self.mapping_key(obs), None)
                    if self._accept_pair(obs, gid, feasibility[key][gid], updates):
                        assigned_obs.add(id(obs))
                        self._record_decision(obs, "assigned", global_id=gid, reason="matched")
                    else:
                        self._record_decision(obs, "rejected", global_id=gid, reason="reference_slot_conflict")

        # 4) 未匹配观测：continuity / 候选池 / unresolved
        unmatched = [o for o in observations if id(o) not in assigned_obs]
        for obs in unmatched:
            key = self.mapping_key(obs)
            # 4a) 强绑定 continuity（保留既有 mapping 的几何门）
            existing = self.mapping.get(key)
            if existing is not None and existing in self.registry.players:
                pred = self.registry.predict_for(existing, timestamp_s)
                if pred is None or _dist(
                    (obs.canonical_x_ft or 0.0, obs.canonical_y_ft or 0.0),
                    (pred[0], pred[1]),
                ) > self._pair_gate_ft(obs, existing, {existing: pred}):
                    self.mapping.pop(key, None)
                    self.diagnostics["continuity_rejected_geometry"] = (
                        self.diagnostics.get("continuity_rejected_geometry", 0) + 1
                    )
                    self._record_decision(obs, "rejected", reason="continuity_rejected_geometry")
                else:
                    binding_ok = self.registry.set_binding(
                        existing, obs.view_id,
                        ViewBinding(
                            view_player_id=obs.view_player_id or None,
                            local_identity_epoch=obs.local_identity_epoch,
                            track_id=obs.track_id,
                            last_seen_take_timestamp_ms=obs.take_timestamp_ms,
                            last_source_frame_index=obs.source_frame_index,
                            quality=obs.intrinsic_quality if obs.intrinsic_quality is not None else obs.confidence,
                            observation_origin=obs.detection_origin,
                            guidance_id=obs.guidance_id,
                            donor_view=obs.donor_view,
                        ),
                        obs.take_timestamp_ms,
                    )
                    if not binding_ok:
                        # D3：reference 槽位已被其他 global 占用 → 不覆盖（continuity 也受限）
                        self._record_decision(
                            obs, "rejected", global_id=existing, reason="reference_slot_conflict"
                        )
                        self.diagnostics["reference_slot_conflict"] = (
                            self.diagnostics.get("reference_slot_conflict", 0) + 1
                        )
                        assigned_obs.add(id(obs))
                        continue
                    updates.append(AssociationUpdate(existing, obs.view_id, obs, 0.0, tentative=True))
                    assigned_obs.add(id(obs))
                    self._record_decision(
                        obs, "assigned", global_id=existing, reason="continuity_preserved", tentative=True
                    )
                    continue
            # 4b) 弱历史绑定（D4）：epoch reset 后经 geometry 重新证明回原 global（可含 stale 玩家）
            historical = self.registry.historical_bindings.get((obs.view_id, self.observation_key(obs)))
            if historical is not None and historical in self.registry.players:
                pred = self.registry.predict_for(historical, timestamp_s)
                if pred is not None and _dist(
                    (obs.canonical_x_ft or 0.0, obs.canonical_y_ft or 0.0),
                    (pred[0], pred[1]),
                ) <= self._pair_gate_ft(obs, historical, {historical: pred}):
                    self.mapping[key] = historical
                    self.diagnostics["historical_reacquired"] = self.diagnostics.get("historical_reacquired", 0) + 1
                    binding_ok = self.registry.set_binding(
                        historical, obs.view_id,
                        ViewBinding(
                            view_player_id=obs.view_player_id or None,
                            local_identity_epoch=obs.local_identity_epoch,
                            track_id=obs.track_id,
                            last_seen_take_timestamp_ms=obs.take_timestamp_ms,
                            last_source_frame_index=obs.source_frame_index,
                            quality=obs.intrinsic_quality if obs.intrinsic_quality is not None else obs.confidence,
                            observation_origin=obs.detection_origin,
                            guidance_id=obs.guidance_id,
                            donor_view=obs.donor_view,
                        ),
                        obs.take_timestamp_ms,
                    )
                    if not binding_ok:
                        # D3：reference 槽位已被其他 global 占用 → 不覆盖（historical 也受限）
                        self.mapping.pop(key, None)
                        self._record_decision(
                            obs, "rejected", global_id=historical, reason="reference_slot_conflict"
                        )
                        self.diagnostics["reference_slot_conflict"] = (
                            self.diagnostics.get("reference_slot_conflict", 0) + 1
                        )
                        assigned_obs.add(id(obs))
                        continue
                    updates.append(AssociationUpdate(historical, obs.view_id, obs, 0.0, tentative=True))
                    assigned_obs.add(id(obs))
                    self._record_decision(
                        obs, "assigned", global_id=historical, reason="historical_reacquired", tentative=True
                    )
                    continue
            # 4c) 候选池（roster 未满） / unresolved（roster 已满）
            if self.registry.roster_state == "ROSTER_ACTIVE" or len(self.registry.players) >= self.registry.expected_player_count:
                self.diagnostics["unresolved_no_slot"] = self.diagnostics.get("unresolved_no_slot", 0) + 1
                self._record_decision(obs, "rejected", reason="unresolved_no_slot")
                continue
            cid = self.registry.find_or_create_candidate(
                view_id=obs.view_id,
                view_player_id=self.observation_key(obs),
                identity_epoch=obs.local_identity_epoch,
                canonical_x_ft=obs.canonical_x_ft or 0.0,
                canonical_y_ft=obs.canonical_y_ft or 0.0,
                tick=tick,
                local_track_id=obs.track_id,
            )
            self.registry.note_candidate_observation(
                cid,
                view_id=obs.view_id,
                view_player_id=self.observation_key(obs),
                identity_epoch=obs.local_identity_epoch,
                canonical_x_ft=obs.canonical_x_ft or 0.0,
                canonical_y_ft=obs.canonical_y_ft or 0.0,
                tick=tick,
                local_track_id=obs.track_id,
            )
            self.diagnostics["candidate_admitted"] = self.diagnostics.get("candidate_admitted", 0) + 1
            self._record_decision(obs, "candidate", reason="candidate_admitted")

        # 5) 候选晋升（D2 / tasks 2.3）+ 候选过期
        for cid in list(self.registry.candidates):
            cand = self.registry.candidates.get(cid)
            if cand is None:
                continue
            if cand.dual_view_hit_count >= self.registry.candidate_promote_dual_ticks or (
                cand.hit_count >= self.registry.candidate_promote_single_ticks
            ):
                gid = self.registry.promote_candidate(cid, tick)
                if gid is not None:
                    self.diagnostics["candidate_promoted"] = self.diagnostics.get("candidate_promoted", 0) + 1
                    for view_id, binding in cand.local_bindings.items():
                        updates.append(
                            AssociationUpdate(
                                gid, view_id,
                                JointObservation(
                                    view_id=view_id,
                                    source_frame_index=tick,
                                    take_timestamp_ms=0.0,
                                    local_x_ft=0.0,
                                    local_y_ft=0.0,
                                    canonical_x_ft=cand.canonical_x_ft,
                                    canonical_y_ft=cand.canonical_y_ft,
                                    view_player_id=str(binding.get("view_player_id") or ""),
                                    local_identity_epoch=int(binding.get("identity_epoch") or 0),
                                    track_id=int(binding.get("track_id") or 0) or None,
                                    confidence=0.5,
                                ),
                                0.0,
                                tentative=True,
                            )
                        )
        self.registry.expire_candidates(tick)

        return updates

    def _accept_pair(
        self,
        obs: JointObservation,
        gid: str,
        feasibility_value: float,
        updates: list[AssociationUpdate],
        *,
        tentative: bool = False,
        override_slot: bool = False,
    ) -> bool:
        """接受一对观测→global 绑定并产出 update。

        fix-multiview-cam1-bootstrap-4player D3：reference 槽位被其他 global 占用时
        返回 False 且不写 mapping/binding（由调用方按冲突处理），不直接覆盖 incumbent。

        ``override_slot``（强证据 reassociation 专用）：连续 N 帧强证据确认同 view
        local 身份应从 incumbent 切换到 challenger 时，先 release 旧槽位再绑定，
        否则唯一性保护会错误拦截合法切换。
        """
        if override_slot and obs.view_player_id:
            self.registry.release_view_slot(obs.view_id, obs.view_player_id)
        binding_ok = self.registry.set_binding(
            gid,
            obs.view_id,
            ViewBinding(
                view_player_id=obs.view_player_id or None,
                local_identity_epoch=obs.local_identity_epoch,
                track_id=obs.track_id,
                last_seen_take_timestamp_ms=obs.take_timestamp_ms,
                last_source_frame_index=obs.source_frame_index,
                quality=obs.intrinsic_quality if obs.intrinsic_quality is not None else obs.confidence,
                visibility="observed",
                observation_origin=obs.detection_origin,
                guidance_id=obs.guidance_id,
                donor_view=obs.donor_view,
            ),
            obs.take_timestamp_ms,
        )
        if not binding_ok:
            self.diagnostics["reference_slot_conflict"] = (
                self.diagnostics.get("reference_slot_conflict", 0) + 1
            )
            return False
        self.mapping[self.mapping_key(obs)] = gid
        dist = max(0.0, feasibility_value) * self.base_gate_ft  # 归一化距离还原（仅诊断）
        updates.append(AssociationUpdate(gid, obs.view_id, obs, 1.0 / (1.0 + dist), tentative=tentative))
        return True

    @staticmethod
    def fuse_assignments(
        updates: list[AssociationUpdate],
        include_tentative: bool = True,
        max_plausible_distance_ft: float = 3.0,
    ) -> dict[str, tuple[float, float, list[str]]]:
        """按 global 聚合分配到的观测,做置信度加权 canonical 均值融合。

        复用 P0 融合数学的 `pair_consistency` 作为冲突门:双视角观测若 inter-view 距离
        超出 `max_plausible_distance_ft` → 视为 conflict,只保留最高置信度视角。
        `include_tentative=True` 时 tentative 单视角也吸收测量(bootstrap 收敛)。
        """
        grouped: dict[str, list[AssociationUpdate]] = {}
        for u in updates:
            if u.tentative and not include_tentative:
                continue
            grouped.setdefault(u.global_id, []).append(u)
        fused: dict[str, tuple[float, float, list[str]]] = {}
        for gid, us in grouped.items():
            # P0 quality 复用:pair_consistency 冲突门
            obs_by_view: dict[str, JointObservation] = {u.view_id: u.observation for u in us}
            if len(obs_by_view) >= 2 and "cam_1" in obs_by_view and "cam_2" in obs_by_view:
                pair = pair_consistency(
                    (obs_by_view["cam_1"].canonical_x_ft, obs_by_view["cam_1"].canonical_y_ft)
                    if obs_by_view["cam_1"].canonical_x_ft is not None else None,
                    (obs_by_view["cam_2"].canonical_x_ft, obs_by_view["cam_2"].canonical_y_ft)
                    if obs_by_view["cam_2"].canonical_x_ft is not None else None,
                    None,
                    max_plausible_distance_ft,
                )
                if (
                    pair.inter_view_distance_ft is not None
                    and pair.inter_view_distance_ft > max_plausible_distance_ft
                ):
                    # conflict:只保留最高置信度视角,避免两路矛盾位置互相平均
                    us = [max(us, key=lambda u: u.observation.confidence)]
            wsum = 0.0
            wx = 0.0
            wy = 0.0
            for u in us:
                w = max(u.observation.confidence, 0.05)
                wsum += w
                wx += w * (u.observation.canonical_x_ft or 0.0)
                wy += w * (u.observation.canonical_y_ft or 0.0)
            if wsum > 0:
                fused[gid] = (wx / wsum, wy / wsum, [u.view_id for u in us])
        return fused
