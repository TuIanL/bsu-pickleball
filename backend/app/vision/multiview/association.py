"""跨视角关联（association）—— CrossViewPlayerAssociator。

把 `(view_id, view_player_id)` 映射到 `global_player_id`，在 canonical 空间基于
`canonical 距离 + global prediction 残差 + 时间连续 + 历史关联` 做小规模二分图匹配。

规则：
- `cam_1/Player_1` 与 `cam_2/Player_1` 不默认等价；
- 存在 association hysteresis：已有关联不被单帧略优候选立即替换，仅连续
  `hysteresis_frames` 强证据才 reassociate；
- **不使用**现有 artifact 的 `side` 字段（摄像机相对且物理反转）。

P0 使用几何 + 时序，不引入 Appearance ReID 模型。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import permutations

from app.vision.multiview.court_frame import CourtOrientation, local_to_canonical
from app.vision.multiview.types import ViewObservation


@dataclass(frozen=True)
class PlayerAssociation:
    """一次跨视角关联结果：一个 global player 对应的两路 view player。"""

    global_player_id: str
    reference_view_player_id: str | None = None
    secondary_view_player_id: str | None = None
    confidence: float = 0.0
    stable_frames: int = 0


def min_cost_matching(
    reference_keys: Sequence[str],
    secondary_keys: Sequence[str],
    cost: Mapping[str, Mapping[str, float]],
    max_cost: float = float("inf"),
) -> list[tuple[str, str]]:
    """小规模二分图最小代价完美匹配（≤6 元素暴力枚举）。

    返回 `[(ref_key, sec_key), ...]`，只包含代价 <= max_cost 的配对；
    超配的元素不配对（保持单视角）。
    """
    if not reference_keys or not secondary_keys:
        return []
    shorter, longer = reference_keys, secondary_keys
    flip = len(longer) < len(shorter)
    if flip:
        shorter, longer = longer, shorter

    best: list[tuple[str, str]] = []
    best_cost = float("inf")
    for perm in permutations(longer, len(shorter)):
        total = 0.0
        feasible = True
        pairs: list[tuple[str, str]] = []
        for a, b in zip(shorter, perm, strict=False):
            value = cost[a][b] if flip else cost[a][b]
            if value > max_cost:
                feasible = False
                break
            total += value
            pairs.append((a, b))
        if feasible and total < best_cost:
            best_cost = total
            best = pairs

    if flip:
        return [(b, a) for (a, b) in best]
    return best


class CrossViewPlayerAssociator:
    """跨视角身份关联器（几何 + 时序 + 迟滞）。"""

    def __init__(
        self,
        *,
        max_association_distance_ft: float = 3.0,
        hysteresis_frames: int = 5,
        prediction_bias_ft: float = 0.5,
    ) -> None:
        self.max_association_distance_ft = max_association_distance_ft
        self.hysteresis_frames = max(1, hysteresis_frames)
        self.prediction_bias_ft = prediction_bias_ft
        # (view_id, view_player_id) -> global_player_id
        self.mapping: dict[tuple[str, str], str] = {}
        # global_player_id -> PlayerAssociation（最近一次）
        self.associations: dict[str, PlayerAssociation] = {}
        # (ref_pid, sec_pid) -> 连续强证据帧数
        self._evidence: dict[tuple[str, str], int] = {}
        self._next_global = 1

    # ---- 主入口 -------------------------------------------------------------

    def process_tick(
        self,
        *,
        reference_view_id: str,
        reference_observations: Sequence[ViewObservation],
        secondary_view_id: str,
        secondary_observations: Sequence[ViewObservation],
        reference_orientation: CourtOrientation | None,
        secondary_orientation: CourtOrientation | None,
        predicted_positions: Mapping[str, tuple[float, float]] | None = None,
    ) -> list[PlayerAssociation]:
        """处理一个 canonical tick 的关联。

        观测为 local 坐标；本方法内部 canonical 化后匹配。返回当帧 global players。
        """
        if reference_orientation is None or secondary_orientation is None:
            raise ValueError("association requires both view orientations declared")
        predicted_positions = predicted_positions or {}

        ref_pos = _canonical_positions(reference_observations, reference_orientation)
        sec_pos = _canonical_positions(secondary_observations, secondary_orientation)
        if not ref_pos and not sec_pos:
            return list(self.associations.values())

        # 1) 保持既有关联（若两路仍同帧出现且距离可接受）。
        retained: list[tuple[str, str]] = []
        for assoc in self.associations.values():
            if assoc.reference_view_player_id is None or assoc.secondary_view_player_id is None:
                continue
            rp, sp = assoc.reference_view_player_id, assoc.secondary_view_player_id
            if rp in ref_pos and sp in sec_pos:
                dist = _distance(ref_pos[rp], sec_pos[sp])
                if dist <= self.max_association_distance_ft:
                    retained.append((rp, sp))

        # 2) 剩余未匹配 player 之间做最小代价匹配。
        used_ref = {rp for rp, _ in retained}
        used_sec = {sp for _, sp in retained}
        avail_ref = [rp for rp in ref_pos if rp not in used_ref]
        avail_sec = [sp for sp in sec_pos if sp not in used_sec]
        cost: dict[str, dict[str, float]] = {
            rp: {
                sp: self._pair_cost(
                    ref_pos[rp],
                    sec_pos[sp],
                    rp,
                    reference_view_id,
                    predicted_positions,
                )
                for sp in avail_sec
            }
            for rp in avail_ref
        }
        new_pairs = min_cost_matching(
            avail_ref,
            avail_sec,
            cost,
            max_cost=self.max_association_distance_ft,
        )

        # 3) 采纳/保持配对：
        #    - 该 ref player 无既有 global（prev_sec None）→ 全新关联，立即采纳；
        #    - 与既有 global 同一 secondary → 保持；
        #    - 变更既有 secondary → 需 hysteresis 连续强证据（防单帧略优换人）。
        pairs = list(retained)
        for rp, sp in new_pairs:
            evidence_key = (rp, sp)
            self._evidence[evidence_key] = self._evidence.get(evidence_key, 0) + 1
            existing_global = self.mapping.get((reference_view_id, rp))
            prev_assoc = self.associations.get(existing_global) if existing_global is not None else None
            prev_sec = prev_assoc.secondary_view_player_id if prev_assoc is not None else None
            if prev_sec is None or prev_sec == sp:
                pairs.append((rp, sp))
            elif self._evidence[evidence_key] >= self.hysteresis_frames:
                pairs.append((rp, sp))

        # 4) 生成/更新 dual-view global players。
        matched_ref = {rp for rp, _ in pairs}
        results: list[PlayerAssociation] = []
        new_associations: dict[str, PlayerAssociation] = {}
        for rp, sp in pairs:
            global_id = self.mapping.get((reference_view_id, rp))
            if global_id is None:
                global_id = self._next_global_id()
            stable = self.associations.get(global_id, PlayerAssociation(global_id)).stable_frames + 1
            confidence = _match_confidence(ref_pos[rp], sec_pos[sp])
            assoc = PlayerAssociation(
                global_player_id=global_id,
                reference_view_player_id=rp,
                secondary_view_player_id=sp,
                confidence=confidence,
                stable_frames=stable,
            )
            self.mapping[(reference_view_id, rp)] = global_id
            self.mapping[(secondary_view_id, sp)] = global_id
            new_associations[global_id] = assoc
            results.append(assoc)

        # 5) reference 侧未匹配球员 → 单视角 global（sample-level single_view_fallback 的基础）。
        for rp in ref_pos:
            if rp in matched_ref:
                continue
            global_id = self.mapping.get((reference_view_id, rp))
            if global_id is None:
                global_id = self._next_global_id()
            stable = self.associations.get(global_id, PlayerAssociation(global_id)).stable_frames + 1
            assoc = PlayerAssociation(
                global_player_id=global_id,
                reference_view_player_id=rp,
                secondary_view_player_id=None,
                confidence=0.0,
                stable_frames=stable,
            )
            self.mapping[(reference_view_id, rp)] = global_id
            new_associations[global_id] = assoc
            results.append(assoc)

        self.associations = new_associations
        self._prune_evidence(avail_ref, avail_sec)
        return results

    def snapshot_global_players(
        self,
        reference_view_id: str,
        secondary_view_id: str,
    ) -> list[PlayerAssociation]:
        """从持久 mapping 提取最终 global players（供融合管线使用）。

        遍历 reference 侧 player，找到其 global_id 及其关联的 secondary player。
        """
        result: list[PlayerAssociation] = []
        seen: set[str] = set()
        for (view_id, player_id), global_id in self.mapping.items():
            if view_id != reference_view_id:
                continue
            if global_id in seen:
                continue
            seen.add(global_id)
            sec_player = None
            for (s_view, s_player), s_global in self.mapping.items():
                if s_view == secondary_view_id and s_global == global_id:
                    sec_player = s_player
                    break
            prev = self.associations.get(global_id)
            result.append(
                PlayerAssociation(
                    global_player_id=global_id,
                    reference_view_player_id=player_id,
                    secondary_view_player_id=sec_player,
                    confidence=prev.confidence if prev else 0.0,
                    stable_frames=prev.stable_frames if prev else 0,
                )
            )
        return result

    # ---- 内部 ---------------------------------------------------------------

    def _pair_cost(
        self,
        ref_pos: tuple[float, float],
        sec_pos: tuple[float, float],
        ref_pid: str,
        reference_view_id: str,
        predicted_positions: Mapping[str, tuple[float, float]],
    ) -> float:
        base = _distance(ref_pos, sec_pos)
        # 该 ref player 已属于某 global player 时，用其预测位置残差作偏置：
        # 把它匹配到远离预测位置的 secondary 会被惩罚（利于既有 global 的连续性）。
        existing_global = self.mapping.get((reference_view_id, ref_pid))
        if existing_global is not None:
            pred = predicted_positions.get(existing_global)
            if pred is not None:
                base += self.prediction_bias_ft * _distance(ref_pos, pred)
        return base

    def _next_global_id(self) -> str:
        global_id = f"global_player_{self._next_global}"
        self._next_global += 1
        return global_id

    def _prune_evidence(self, avail_ref: Sequence[str], avail_sec: Sequence[str]) -> None:
        """清掉当前 tick 未出现的候选证据，避免陈旧证据长期作祟。"""
        active = set(avail_ref) | set(avail_sec)
        stale = [key for key in self._evidence if key[0] not in active and key[1] not in active]
        for key in stale:
            self._evidence.pop(key, None)


def _canonical_positions(
    observations: Sequence[ViewObservation],
    orientation: CourtOrientation,
) -> dict[str, tuple[float, float]]:
    positions: dict[str, tuple[float, float]] = {}
    for obs in observations:
        if not obs.view_player_id:
            continue
        positions[obs.view_player_id] = local_to_canonical(
            obs.local_x_ft, obs.local_y_ft, orientation
        )
    return positions


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def _match_confidence(a: tuple[float, float], b: tuple[float, float]) -> float:
    # 距离越小越可信；线性映射到 (0,1]。
    dist = _distance(a, b)
    return 1.0 / (1.0 + dist)
