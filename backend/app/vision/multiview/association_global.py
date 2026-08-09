"""GlobalPlayerAssociator —— 观测→global 分配（Additive P1）。

不修改 P0 `CrossViewPlayerAssociator`(reference-centric,仅 late_fusion_v1 使用)。
本模块在 `joint_tracking_v2` 中做 global-centric 分配:

    GlobalState.predict(t)
        ├── assign Cam1 observations → global states
        ├── assign Cam2 observations → global states
        ├── unmatched observations → tentative global candidates
        └── fusion/update GlobalState(t)

复用 Change 0 的 `min_cost_matching()` 作为共享 primitive。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

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
    track_id: int | None = None
    confidence: float = 0.0
    projection_confidence: float | None = None
    detection_origin: str = "base"  # base | guided_roi
    guidance_id: str | None = None


@dataclass
class AssociationUpdate:
    """一次关联结果:观测被分配到某 global。"""

    global_id: str
    view_id: str
    observation: JointObservation
    confidence: float
    tentative: bool = False


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


class GlobalPlayerAssociator:
    """global-centric 观测分配器。"""

    def __init__(
        self,
        registry: GlobalPlayerRegistry,
        max_association_distance_ft: float = 3.0,
        prediction_bias_ft: float = 0.5,
    ) -> None:
        self.registry = registry
        self.max_association_distance_ft = max_association_distance_ft
        self.prediction_bias_ft = prediction_bias_ft
        # (view_id, obs_key) -> global_id(obs_key = view_player_id 或 str(track_id))
        self.mapping: dict[tuple[str, str], str] = {}

    def process_tick(
        self,
        observations: list[JointObservation],
        timestamp_s: float,
        orientation_by_view: Mapping[str, CourtOrientation],
    ) -> list[AssociationUpdate]:
        """把两路观测分配到 global states;返回关联更新。"""
        # 1) canonical 化
        for obs in observations:
            if obs.canonical_x_ft is None:
                cx, cy = local_to_canonical(
                    obs.local_x_ft, obs.local_y_ft, orientation_by_view.get(obs.view_id)
                )
                obs.canonical_x_ft, obs.canonical_y_ft = cx, cy

        predictions = self.registry.predict_all(timestamp_s)
        updates: list[AssociationUpdate] = []
        assigned_obs: set[int] = set()  # id(obs)

        # 2) 逐 view 用 min_cost_matching 把观测分配给预测 global(最大基数 + 最小 ranking)
        for view_id, _orientation in orientation_by_view.items():
            view_obs = [o for o in observations if o.view_id == view_id]
            pred_globals = [gid for gid in self.registry.players if gid in predictions]
            if not view_obs or not pred_globals:
                continue
            ranking: dict[str, dict[str, float]] = {}
            feasibility: dict[str, dict[str, float]] = {}
            for obs in view_obs:
                key = obs.view_player_id or str(obs.track_id)
                ranking[key] = {}
                feasibility[key] = {}
                for gid in pred_globals:
                    px, py = predictions[gid][0], predictions[gid][1]
                    geometry = _dist((obs.canonical_x_ft, obs.canonical_y_ft), (px, py))
                    feasibility[key][gid] = geometry
                    # per-candidate prediction residual(ranking 项)
                    ranking[key][gid] = geometry + self.prediction_bias_ft * geometry
            obs_keys = [o.view_player_id or str(o.track_id) for o in view_obs]
            pairs = min_cost_matching(
                obs_keys,
                pred_globals,
                ranking,
                feasibility_cost=feasibility,
                max_feasibility_cost=self.max_association_distance_ft,
            )
            for key, gid in pairs:
                obs = next(o for o in view_obs if (o.view_player_id or str(o.track_id)) == key)
                assigned_obs.add(id(obs))
                self.mapping[(view_id, key)] = gid
                dist = feasibility[key][gid]
                self.registry.set_binding(
                    gid,
                    view_id,
                    ViewBinding(
                        view_player_id=obs.view_player_id or None,
                        track_id=obs.track_id,
                        last_seen_take_timestamp_ms=obs.take_timestamp_ms,
                        quality=obs.confidence,
                        visibility="observed",
                    ),
                    obs.take_timestamp_ms,
                )
                updates.append(AssociationUpdate(gid, view_id, obs, 1.0 / (1.0 + dist)))

        # 3) 未匹配观测 → 先遵循既有 mapping(连续性),再同 tick 跨视角就近成组 → tentative
        unmatched = [o for o in observations if id(o) not in assigned_obs]
        groups: list[tuple[str, tuple[float, float], list[JointObservation]]] = []
        for obs in unmatched:
            key = obs.view_player_id or str(obs.track_id)
            existing = self.mapping.get((obs.view_id, key))
            if existing is not None and existing in self.registry.players:
                # 既有映射连续性:直接复用该 global(更新 binding)
                self.registry.set_binding(
                    existing, obs.view_id,
                    ViewBinding(
                        view_player_id=obs.view_player_id or None, track_id=obs.track_id,
                        last_seen_take_timestamp_ms=obs.take_timestamp_ms, quality=obs.confidence,
                    ),
                    obs.take_timestamp_ms,
                )
                updates.append(AssociationUpdate(existing, obs.view_id, obs, 0.0, tentative=True))
                continue
            pos = (obs.canonical_x_ft or 0.0, obs.canonical_y_ft or 0.0)
            placed = False
            for gi, (gid, centroid, members) in enumerate(groups):
                if _dist(pos, centroid) <= self.max_association_distance_ft:
                    members.append(obs)
                    n = len(members)
                    groups[gi] = (gid, ((centroid[0] * (n - 1) + pos[0]) / n, (centroid[1] * (n - 1) + pos[1]) / n), members)
                    placed = True
                    break
            if not placed:
                groups.append((self.registry.new_global_id(), pos, [obs]))
        for gid, _centroid, members in groups:
            state = self.registry.ensure(gid)
            state.lifecycle = "tentative"
            for obs in members:
                key = obs.view_player_id or str(obs.track_id)
                self.mapping[(obs.view_id, key)] = gid
                self.registry.set_binding(
                    gid,
                    obs.view_id,
                    ViewBinding(
                        view_player_id=obs.view_player_id or None,
                        track_id=obs.track_id,
                        last_seen_take_timestamp_ms=obs.take_timestamp_ms,
                        quality=obs.confidence,
                    ),
                    obs.take_timestamp_ms,
                )
                updates.append(AssociationUpdate(gid, obs.view_id, obs, 0.0, tentative=True))

        return updates

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
