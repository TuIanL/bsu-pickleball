"""球员锁定管理器 —— 保持四名主球员的身份稳定性，跨帧锁定与重连。"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass, field
from math import hypot

from app.schemas.tracking import (
    PlayerFramePosition,
    PlayerIdentityDiagnostic,
)
from app.vision.courtvision_calibration_engine.court_geometry import standard_court
from app.vision.courtvision_calibration_engine.court_units import meters_to_feet
from app.vision.player_tracking_engine.player_lock_types import (
    PlayerLockConfig,
    PlayerLockUpdate,
    PlayerSlot,
)


def _distance(a: list[float], b: list[float]) -> float:
    return hypot(a[0] - b[0], a[1] - b[1])


@dataclass
class InitialLockAssignment:
    """首次 lock 映射（仅记录一次，永不覆盖）。

    用于 bootstrap 展示回填：离线任务结束后，用「Player_N 最终锁定的 track_id」
    反查其在 lock 之前已真实存在的原始观测。该映射与 `lock_diagnostics.player_locked`
    不同——bootstrap 首次锁定走 `_assign_candidate_to_slot`（不写 diagnostic），而这里
    在任意 slot 第一次进入 `locked` 时可靠记录，作为回填 authoritative source。
    """

    player_id: str
    track_id: int
    locked_frame_index: int


class PlayerLockManager:
    def __init__(self, config: PlayerLockConfig | None = None) -> None:
        self.config = config or PlayerLockConfig()
        self.court = standard_court()
        self.slots: dict[str, PlayerSlot] = {}
        self._bootstrap_complete = False
        self._bootstrap_tracklets: dict[int, _BootstrapTracklet] = {}
        self._bootstrap_diagnostics: list[PlayerIdentityDiagnostic] = []
        # fix-joint-bootstrap-visual-gap：首次 lock 映射（仅在第一次进入 locked 时记录）
        self._initial_lock_assignments: dict[str, InitialLockAssignment] = {}
        self._track_to_slot: dict[int, str] = {}
        self._frame_width: int | None = None
        self._frame_height: int | None = None

        for idx in range(self.config.target_player_count):
            identity_id = f"Player_{idx + 1}"
            self.slots[identity_id] = PlayerSlot(identity_id=identity_id)

    def update(
        self,
        frame_index: int,
        positions: Sequence[PlayerFramePosition],
        suggestions: Sequence | None = None,
        frame=None,
        frame_width: int | None = None,
        frame_height: int | None = None,
    ) -> PlayerLockUpdate:
        # 记录画面尺寸（用于 bootstrap 中心优先排序；缺失时退化为按置信度排序）
        self._frame_width = frame_width
        self._frame_height = frame_height
        suggested_ids: set[int] = set()
        if suggestions is not None:
            for s in suggestions:
                try:
                    suggested_ids.add(s.track_id)
                except AttributeError:
                    pass

        if not self._bootstrap_complete and frame_index < self.config.bootstrap_max_frames:
            self._run_bootstrap(frame_index, positions)

        if frame_index >= self.config.bootstrap_max_frames and not self._bootstrap_complete:
            self._finalize_bootstrap(frame_index)

        reconnect_candidates: set[int] = set()
        track_hints: dict[int, str] = {}
        diagnostics: list[PlayerIdentityDiagnostic] = []
        newly_locked: list[str] = []
        newly_lost: list[str] = []

        # Phase 1: consume each still-visible locked track once.  A stale or
        # duplicated slot mapping must not make one observation update two P IDs.
        locked_track_ids: set[int] = set()
        recovery_slots: list[PlayerSlot] = []
        for slot in self.slots.values():
            if slot.state == "locked":
                matched = self._find_matching_position(slot, positions)
                owner = self._track_to_slot.get(matched.track_id) if matched is not None else None
                if (
                    matched is not None
                    and matched.track_id not in locked_track_ids
                    and (owner is None or owner == slot.identity_id)
                ):
                    self._update_slot_from_position(slot, matched, frame_index)
                    locked_track_ids.add(matched.track_id)
                    self._track_to_slot[matched.track_id] = slot.identity_id
                    track_hints[matched.track_id] = slot.identity_id
                else:
                    recovery_slots.append(slot)
            elif slot.state == "lost":
                recovery_slots.append(slot)

        # Phase 2: assign unclaimed observations globally.  Sorting all viable
        # pairs by score makes the result deterministic and prevents duplicate
        # reconnects when two LOST slots prefer the same detector track.
        recovery_assignments = self._assign_recovery_candidates(
            recovery_slots,
            positions,
            locked_track_ids,
        )
        for slot, candidate, score in recovery_assignments:
            previous_state = slot.state
            score_details = self._reconnect_score_details(slot, candidate)
            # fix-multiview-player-identity D5：身份互换观测（owner 抢注 / 跨侧兜底）
            swap_reason = self._suspected_identity_swap_reason(slot, candidate)
            slot.state = "locked"
            slot.current_track_id = candidate.track_id
            slot.lost_frames = 0
            self._record_initial_lock(slot.identity_id, candidate.track_id, frame_index)
            locked_track_ids.add(candidate.track_id)
            reconnect_candidates.add(candidate.track_id)
            self._track_to_slot[candidate.track_id] = slot.identity_id
            track_hints[candidate.track_id] = slot.identity_id
            self._update_slot_from_position(slot, candidate, frame_index)
            if swap_reason:
                diagnostics.append(
                    PlayerIdentityDiagnostic(
                        frame_index=frame_index,
                        event="identity_swap_suspected",
                        player_id=slot.identity_id,
                        track_id=candidate.track_id,
                        score=score,
                        reason=swap_reason,
                        court_position_m=list(candidate.court_position) if candidate.court_position else None,
                    )
                )
            diagnostics.append(
                PlayerIdentityDiagnostic(
                    frame_index=frame_index,
                    event=(
                        "player_reconnected_from_lost"
                        if previous_state == "lost"
                        else "player_reconnected_after_track_change"
                    ),
                    player_id=slot.identity_id,
                    track_id=candidate.track_id,
                    score=score,
                    reason=score_details,
                    court_position_m=list(candidate.court_position) if candidate.court_position else None,
                )
            )
            if previous_state == "lost":
                newly_locked.append(slot.identity_id)

        # Unassigned locked/lost slots advance their loss clock only after the
        # same-frame recovery pass has had a chance to rescue them.
        recovered_slot_ids = {slot.identity_id for slot, _candidate, _score in recovery_assignments}
        for slot in recovery_slots:
            if slot.identity_id in recovered_slot_ids:
                continue
            slot.lost_frames += 1
            if slot.state == "locked" and slot.lost_frames >= self.config.lost_grace_frames:
                slot.state = "lost"
                slot.current_track_id = None
                newly_lost.append(slot.identity_id)

        # Phase 3: fill only slots that are not hard-locked.  All tracks
        # already consumed by locked/reconnected slots remain excluded.
        for slot in self.slots.values():
            if slot.state not in {"searching", "tentative", "fallback_tentative"}:
                continue
            if not self._bootstrap_complete:
                continue
            matched = self._find_new_candidate(slot, positions, locked_track_ids | reconnect_candidates)
            if matched is not None:
                if slot.state == "fallback_tentative" and self._can_replace_fallback(
                    slot, matched.track_id, matched.confidence
                ):
                    diagnostics.append(
                        PlayerIdentityDiagnostic(
                            frame_index=frame_index,
                            event="side_quota_fallback_replaced",
                            player_id=slot.identity_id,
                            track_id=matched.track_id,
                            reason=f"fallback_replaced; old_track={slot.current_track_id}",
                            court_position_m=list(matched.court_position) if matched.court_position else None,
                        )
                    )
                    slot.state = "searching"
                    slot.current_track_id = None
                self._try_lock_slot(
                    slot, matched, frame_index, locked_track_ids, track_hints, diagnostics, newly_locked
                )

        eligible_track_ids = locked_track_ids | reconnect_candidates

        player_states = {slot.identity_id: slot.state for slot in self.slots.values()}

        # fix-multiview-cam1-bootstrap-4player D5：合并 bootstrap 完整性诊断
        # （slot_unfilled），仅在 bootstrap 刚完成的那一帧携带（之后清空）。
        merged_diagnostics = diagnostics
        if self._bootstrap_diagnostics:
            merged_diagnostics = list(diagnostics) + list(self._bootstrap_diagnostics)
            self._bootstrap_diagnostics = []

        return PlayerLockUpdate(
            eligible_track_ids=eligible_track_ids,
            track_identity_hints=track_hints,
            player_states=player_states,
            diagnostics=merged_diagnostics,
            newly_locked=newly_locked,
            newly_lost=newly_lost,
        )

    def get_active_track_ids(self) -> set[int]:
        result: set[int] = set()
        for slot in self.slots.values():
            if slot.state in {"locked", "lost"} and slot.current_track_id is not None:
                result.add(slot.current_track_id)
        return result

    @property
    def near_occupancy(self) -> int:
        return sum(
            1
            for slot in self.slots.values()
            if slot.assignment_side == "near" and slot.state in ("tentative", "locked", "lost", "fallback_tentative")
        )

    @property
    def far_occupancy(self) -> int:
        return sum(
            1
            for slot in self.slots.values()
            if slot.assignment_side == "far" and slot.state in ("tentative", "locked", "lost", "fallback_tentative")
        )

    def _record_initial_lock(self, player_id: str, track_id: int, frame_index: int) -> None:
        """记录某 slot 第一次进入 locked 的 (track_id, locked_frame_index)。

        仅在 player_id 尚未记录时写入，永不覆盖——即使后续 reconnect / tentative 切换
        也不会改变首次锁定映射。这是 bootstrap 展示回填的 authoritative source。
        """
        if player_id in self._initial_lock_assignments:
            return
        self._initial_lock_assignments[player_id] = InitialLockAssignment(
            player_id=player_id,
            track_id=track_id,
            locked_frame_index=frame_index,
        )

    def _side_has_capacity(self, side: str | None) -> bool:
        if side == "near":
            return self.near_occupancy < self.config.near_side_quota
        if side == "far":
            return self.far_occupancy < self.config.far_side_quota
        return False

    def _assign_candidate_to_slot(
        self,
        slot: PlayerSlot,
        track_id: int,
        side: str | None,
        quadrant: str | None,
        frame_index: int,
        confidence: float,
        observed_frames: int,
    ) -> None:
        if side and not self._side_has_capacity(side):
            self._track_to_slot.pop(track_id, None)
            return
        slot.current_track_id = track_id
        if track_id not in slot.track_id_history:
            slot.track_id_history.append(track_id)
        slot.assignment_side = side
        if quadrant is not None:
            slot.home_quadrant = quadrant
        if slot.side_hint is None:
            slot.side_hint = quadrant or side
        slot.last_seen_frame = frame_index
        slot.confidence_ema = 0.7 * slot.confidence_ema + 0.3 * confidence
        slot.observed_frames = observed_frames
        self._track_to_slot[track_id] = slot.identity_id
        if slot.state in ("searching", "fallback_tentative"):
            slot.state = "tentative"
            if slot.observed_frames >= self.config.lock_min_hits:
                slot.state = "locked"
                slot.locked_since_frame = frame_index
                slot.lost_frames = 0
                self._record_initial_lock(slot.identity_id, track_id, frame_index)

    def _can_replace_fallback(
        self,
        fallback_slot: PlayerSlot,
        new_track_id: int,
        new_confidence: float,
    ) -> bool:
        if fallback_slot.state != "fallback_tentative":
            return False
        return new_confidence > fallback_slot.confidence_ema * self.config.fallback_replacement_margin

    # ---------- bootstrap ----------

    def _run_bootstrap(self, frame_index: int, positions: Sequence[PlayerFramePosition]) -> None:
        if frame_index < self.config.bootstrap_min_frames:
            self._collect_bootstrap_observations(frame_index, positions)
            return
        self._collect_bootstrap_observations(frame_index, positions)
        self._try_early_lock(frame_index)

    def _collect_bootstrap_observations(self, frame_index: int, positions: Sequence[PlayerFramePosition]) -> None:
        for pos in positions:
            # fix-multiview-cam1-bootstrap-4player D1：bootstrap 收集用"纵向可判"
            # 门槛（stage="bootstrap"），x 出界（outside_tracking_area）不拒绝。
            if not self._is_identity_candidate(pos, stage="bootstrap"):
                continue
            if not self._is_in_court_neighborhood(pos.court_position, self.config.bootstrap_court_margin_ft):
                continue
            tl = self._bootstrap_tracklets.setdefault(pos.track_id, _BootstrapTracklet())
            tl.frame_indices.append(frame_index)
            tl.confidences.append(pos.confidence)
            if pos.court_position is not None:
                tl.court_xs.append(pos.court_position[0])
                tl.court_ys.append(pos.court_position[1])
            if pos.bbox is not None and len(pos.bbox) >= 4:
                tl.bbox_centers.append(((pos.bbox[0] + pos.bbox[2]) / 2.0, (pos.bbox[1] + pos.bbox[3]) / 2.0))
                # fix-multiview-player-identity D3：记录 bbox 面积，供近端大尺寸优先排序
                tl.bbox_areas.append(max(0.0, (pos.bbox[2] - pos.bbox[0]) * (pos.bbox[3] - pos.bbox[1])))

    def _try_early_lock(self, frame_index: int) -> None:
        self._assign_bootstrap_candidates(frame_index)

    def _finalize_bootstrap(self, frame_index: int) -> None:
        self._assign_bootstrap_candidates(frame_index)
        # 剩余 searching 槽位：降级候选（fallback_tentative，锁定前可被更优候选替换）
        remaining_searching = sum(1 for s in self.slots.values() if s.state == "searching")
        if remaining_searching > 0 and self.config.allow_quota_fallback:
            assigned: set[int] = set()
            for slot in self.slots.values():
                assigned.update(slot.track_id_history)
            half_length = self.court.length_ft / 2.0
            for track_id, tl in self._bootstrap_candidate_entries():
                if track_id in assigned:
                    continue
                slot = self._first_searching_slot()
                if slot is None:
                    break
                slot.state = "fallback_tentative"
                slot.current_track_id = track_id
                slot.track_id_history = [track_id]
                slot.last_seen_frame = frame_index
                slot.confidence_ema = tl.mean_confidence()
                slot.observed_frames = len(tl.frame_indices)
                slot.assignment_side = tl.inferred_side(half_length)
                slot.home_quadrant = self._infer_quadrant(tl)
                slot.side_hint = slot.home_quadrant or slot.assignment_side
                self._track_to_slot[track_id] = slot.identity_id
                assigned.add(track_id)
        # fix-multiview-cam1-bootstrap-4player D5：bootstrap 结束后仍 searching 的
        # 槽位输出 slot_unfilled 诊断（只观测、不伪造锁定、不替换已锁定槽位）。
        for slot in self.slots.values():
            if slot.state != "searching":
                continue
            self._bootstrap_diagnostics.append(
                PlayerIdentityDiagnostic(
                    frame_index=frame_index,
                    event="slot_unfilled",
                    player_id=slot.identity_id,
                    track_id=None,
                    reason=f"home_quadrant={self._slot_home_quadrant(slot)}",
                )
            )
        self._bootstrap_complete = True

    def _bootstrap_candidate_entries(self) -> list[tuple[int, _BootstrapTracklet]]:
        # 已通过门控/置信度过滤的候选排序。
        # fix-multiview-player-identity D3：近端大尺寸候选（画面近端、bbox 大、清晰）
        # 优先于"距画面中心最近"，避免近端球员因 bbox 中心偏离画面中心而被远端候选抢占。
        # fix-multiview-cam1-bootstrap-4player D1 修正：持续性（出现帧数）优先于中心距离——
        # 短暂 track（如观众/裁判或检测抖动产生的短 track）不得靠"更靠画面中心"抢占
        # 稳定球员的槽位（root cause：track 16 短 track 抢 near_right，track 4 稳定 90 帧被跳过）。
        # 排序键：near_large(0=是,1=否) → 出现帧数降序 → 中心距离 → 置信度降序。
        entries: list[tuple[int, _BootstrapTracklet]] = []
        frame_area = (
            (self._frame_width or 0) * (self._frame_height or 0)
            if self._frame_width and self._frame_height
            else 0.0
        )
        half_length = self.court.length_ft / 2.0
        for track_id, tl in self._bootstrap_tracklets.items():
            if len(tl.frame_indices) < self.config.min_observed_frames:
                continue
            if tl.mean_confidence() < self.config.searching_conf:
                continue
            entries.append((track_id, tl))
        entries.sort(
            key=lambda item: (
                0 if item[1].is_near_large(half_length, frame_area, self.config.near_large_bbox_ratio) else 1,
                -len(item[1].frame_indices),
                item[1].mean_center_distance(self._frame_width, self._frame_height),
                -item[1].mean_confidence(),
            )
        )
        return entries

    def _assign_bootstrap_candidates(self, frame_index: int) -> None:
        # 第一遍：象限匹配优先——每个象限取"中心最近"的候选锁定到对应槽位。
        assigned: set[int] = set()
        for slot in self.slots.values():
            assigned.update(slot.track_id_history)
        for track_id, tl in self._bootstrap_candidate_entries():
            if track_id in assigned:
                continue
            quadrant = self._infer_quadrant(tl)
            slot = self._pick_quadrant_slot(quadrant)
            if slot is None:
                continue
            self._assign_candidate_to_slot(
                slot=slot,
                track_id=track_id,
                side=self._side_from_quadrant(quadrant),
                quadrant=quadrant,
                frame_index=frame_index,
                confidence=tl.mean_confidence(),
                observed_frames=len(tl.frame_indices),
            )
            if slot.current_track_id == track_id:
                assigned.add(track_id)
        # 第二遍：象限未知（中心线附近）的候选填任意 searching 槽，避免没家。
        for track_id, tl in self._bootstrap_candidate_entries():
            if track_id in assigned:
                continue
            if self._infer_quadrant(tl) is not None:
                continue
            slot = self._first_searching_slot()
            if slot is None:
                break
            self._assign_candidate_to_slot(
                slot=slot,
                track_id=track_id,
                side=None,
                quadrant=None,
                frame_index=frame_index,
                confidence=tl.mean_confidence(),
                observed_frames=len(tl.frame_indices),
            )
            if slot.current_track_id == track_id:
                assigned.add(track_id)

    def _infer_quadrant(self, tl: _BootstrapTracklet) -> str | None:
        # 由球场中位坐标推断候选归属象限（近左/近右/远左/远右）；单打退化为近/远。
        # fix-multiview-cam1-bootstrap-4player D2：court 投影 x 无法判 left/right
        # （x 落在半场死区或超出 tracking bounds）时，用图像 bbox 中心 x 相对画面
        # 宽度 50% 分界推断横向，完成象限归属（仅 x 出界/死区分支触发，正常投影优先）。
        half_length = self.court.length_ft / 2.0
        half_width = self.court.width_ft / 2.0
        side = tl.inferred_side(half_length)
        if side is None:
            return None
        if self.config.target_player_count <= 2:
            return side
        lateral = tl.inferred_lateral(half_width)
        if lateral is not None:
            return f"{side}_{lateral}"
        # D2 松弛映射：court x 不可判时用图像横向位置推断 left/right
        lateral_from_image = tl.inferred_image_lateral(self._frame_width)
        if lateral_from_image is None:
            return None
        return f"{side}_{lateral_from_image}"

    def _slot_home_quadrant(self, slot: PlayerSlot) -> str:
        # 槽位位置语义：Player_1..4 = 近左/近右/远左/远右；单打 = 近/远。
        index = int(slot.identity_id.rsplit("_", 1)[-1]) - 1
        if self.config.target_player_count == 4:
            return ("near_left", "near_right", "far_left", "far_right")[index]
        return ("near", "far")[index]

    def _side_from_quadrant(self, quadrant: str | None) -> str | None:
        if not quadrant:
            return None
        return quadrant.split("_")[0]

    def _pick_quadrant_slot(self, quadrant: str | None) -> PlayerSlot | None:
        # 返回 home 象限与候选一致的 searching 槽位；象限未知时返回 None（由第二遍处理）。
        if quadrant is None:
            return None
        for slot in self.slots.values():
            if slot.state != "searching":
                continue
            if self._slot_home_quadrant(slot) == quadrant:
                return slot
        return None

    def _first_searching_slot(self) -> PlayerSlot | None:
        for slot in self.slots.values():
            if slot.state == "searching":
                return slot
        return None

    # ---------- spatial gating ----------

    def _is_identity_candidate(
        self, position: PlayerFramePosition, *, stage: str = "general"
    ) -> bool:
        """Keep visible boundary observations eligible for player identity.

        ``valid`` describes the strict court rectangle, while a player can be
        visibly standing just beyond a baseline and still be inside the broad
        tracking area used by the primary-player selector.

        ``stage`` 语义：
        - ``general``（默认）：保持既有语义——tracking area 硬门 + D3 近端大尺寸放宽，
          用于 reconnect/lost/find-new-candidate 等阶段；
        - ``bootstrap``：fix-multiview-cam1-bootstrap-4player D1 —— 候选接纳以
          "纵向可判"为门槛（court y 可判 near/far + bbox 非空），x 超出 tracking
          bounds（outside_tracking_area）不单独拒绝。象限归属由 D2 松弛映射兜底。
        """
        if position.court_position is None:
            return False
        if stage == "bootstrap":
            if position.bbox is None or len(position.bbox) < 4:
                return False
            return is_court_side_decidable(position.court_position, self.court)
        if not position.is_inside_tracking_area:
            if not self._is_near_large_high_conf(position):
                return False
        return position.valid or position.projection_status == "outside_court_visible"

    def _is_near_large_high_conf(self, position: PlayerFramePosition) -> bool:
        """fix-multiview-player-identity D3：近端 + 大尺寸 + 高清晰 三重条件判定。"""
        if position.confidence < self.config.searching_conf:
            return False
        if position.court_position is None:
            return False
        half_length = self.court.length_ft / 2.0
        if position.court_position[1] >= half_length:
            return False  # 仅放宽近端（court y < 网线 22ft）
        if position.bbox is None or len(position.bbox) < 4:
            return False
        if not self._frame_width or not self._frame_height:
            return False
        frame_area = float(self._frame_width) * float(self._frame_height)
        bbox_area = max(0.0, (position.bbox[2] - position.bbox[0]) * (position.bbox[3] - position.bbox[1]))
        return bbox_area / frame_area >= self.config.near_large_bbox_ratio

    def _is_in_court_neighborhood(self, court_position: list[float], margin_ft: float) -> bool:
        x, y = court_position[0], court_position[1]
        return (
            -margin_ft <= x <= self.court.width_ft + margin_ft and -margin_ft <= y <= self.court.length_ft + margin_ft
        )

    def _classify_candidate(self, court_position: list[float], slot_state: str) -> str:
        if self.court.is_in_court_bounds(court_position[0], court_position[1]):
            return "inside_court"
        margin = self.config.court_margin_ft
        if slot_state in {"locked", "lost"}:
            if self._is_in_court_neighborhood(court_position, margin):
                return "near_court_area"
            if self.court.is_in_tracking_bounds(court_position[0], court_position[1]):
                return "tracking_area"
        else:
            if self._is_in_court_neighborhood(court_position, margin):
                return "near_court_area"
        return "outside"

    # ---------- position matching ----------

    def _find_matching_position(
        self, slot: PlayerSlot, positions: Sequence[PlayerFramePosition]
    ) -> PlayerFramePosition | None:
        if slot.current_track_id is not None:
            for pos in positions:
                if pos.track_id != slot.current_track_id:
                    continue
                # fix-multiview-cam1-bootstrap-4player D1：已绑定本槽位的 track
                # 用"纵向可判"门槛持续匹配（bootstrap 已接纳的 x 出界候选不得因
                # x 超界丢失跟踪），而非 general 硬门。
                if not self._is_identity_candidate(pos, stage="bootstrap"):
                    continue
                classification = self._classify_candidate(pos.court_position, slot.state)
                if classification != "outside":
                    if pos.confidence >= self._conf_threshold_for_state(slot.state):
                        return pos
        return None

    def _find_new_candidate(
        self, slot: PlayerSlot, positions: Sequence[PlayerFramePosition], exclude_track_ids: set[int]
    ) -> PlayerFramePosition | None:
        best: PlayerFramePosition | None = None
        best_conf = 0.0
        for pos in positions:
            if not self._is_identity_candidate(pos):
                continue
            if pos.track_id in exclude_track_ids:
                continue
            owner = self._track_to_slot.get(pos.track_id)
            if owner is not None and owner != slot.identity_id:
                continue
            classification = self._classify_candidate(pos.court_position, slot.state)
            if classification not in {"inside_court", "near_court_area"}:
                continue
            if pos.confidence >= self._conf_threshold_for_state(slot.state) and pos.confidence > best_conf:
                best = pos
                best_conf = pos.confidence
        return best

    def _assign_recovery_candidates(
        self,
        slots: Sequence[PlayerSlot],
        positions: Sequence[PlayerFramePosition],
        occupied_track_ids: set[int],
    ) -> list[tuple[PlayerSlot, PlayerFramePosition, float]]:
        """Greedily make a deterministic one-to-one reconnect assignment.

        A global candidate list is used instead of letting each LOST slot pick
        independently.  This keeps a single detector track from producing two
        canonical identity hints in the same frame while preserving the
        existing score threshold and spatial gates.
        """
        pairs: list[tuple[float, str, int, PlayerSlot, PlayerFramePosition]] = []
        seen_track_ids: set[int] = set()
        for slot in slots:
            for position in positions:
                if position.track_id in occupied_track_ids or position.track_id in seen_track_ids:
                    continue
                owner = self._track_to_slot.get(position.track_id)
                if owner is not None and owner != slot.identity_id:
                    continue
                if not self._is_identity_candidate(position):
                    continue
                if self._classify_candidate(position.court_position, slot.state) == "outside":
                    continue
                if position.confidence < self._conf_threshold_for_state(slot.state):
                    continue
                # fix-multiview-player-identity D4：跨侧候选直接不可选（防止 P1↔P2 互换）
                if self._candidate_side_conflicts(slot, position):
                    continue
                score = self._compute_reconnect_score(slot, position)
                if score < self.config.reconnect_threshold:
                    continue
                pairs.append((score, slot.identity_id, position.track_id, slot, position))
            # Do not suppress a track globally while building the pair list:
            # it may be a valid candidate for more than one slot and is then
            # resolved by the deterministic reservation pass below.
            seen_track_ids.clear()

        pairs.sort(key=lambda item: (-item[0], item[1], item[2]))
        assigned_slots: set[str] = set()
        assigned_tracks = set(occupied_track_ids)
        assignments: list[tuple[PlayerSlot, PlayerFramePosition, float]] = []
        for score, _identity_id, _track_id, slot, position in pairs:
            if slot.identity_id in assigned_slots or position.track_id in assigned_tracks:
                continue
            assigned_slots.add(slot.identity_id)
            assigned_tracks.add(position.track_id)
            assignments.append((slot, position, score))
        return assignments

    def _conf_threshold_for_state(self, state: str) -> float:
        thresholds = {
            "searching": self.config.searching_conf,
            "tentative": self.config.tentative_conf,
            "locked": self.config.locked_conf,
            "lost": self.config.locked_conf,
            "inactive": 1.0,
            "fallback_tentative": self.config.searching_conf,
        }
        return thresholds.get(state, self.config.searching_conf)

    # ---------- slot management ----------

    def _update_slot_from_position(self, slot: PlayerSlot, pos: PlayerFramePosition, frame_index: int) -> None:
        prev_pos = slot.last_confirmed_position_m
        previous_seen_frame = slot.last_seen_frame
        slot.current_track_id = pos.track_id
        if pos.track_id not in slot.track_id_history:
            slot.track_id_history.append(pos.track_id)
        slot.last_seen_frame = frame_index
        slot.last_bbox = list(pos.bbox) if pos.bbox else None
        slot.last_image_footpoint = list(pos.image_footpoint) if pos.image_footpoint else None
        if pos.court_position is not None:
            new_pos = [float(pos.court_position[0]), float(pos.court_position[1])]
            if prev_pos is not None:
                fps = max(float(self.config.fps), 1.0)
                previous_timestamp = previous_seen_frame / fps if previous_seen_frame >= 0 else pos.timestamp
                dt = max(pos.timestamp - previous_timestamp, 0.001)
                slot.last_velocity_mps = [
                    (new_pos[0] - prev_pos[0]) / dt,
                    (new_pos[1] - prev_pos[1]) / dt,
                ]
            slot.last_confirmed_position_m = new_pos
        slot.confidence_ema = 0.7 * slot.confidence_ema + 0.3 * pos.confidence
        slot.observed_frames += 1
        slot.lost_frames = 0
        if slot.state == "lost":
            slot.state = "locked"
            self._record_initial_lock(slot.identity_id, pos.track_id, frame_index)

    def _try_lock_slot(
        self,
        slot: PlayerSlot,
        pos: PlayerFramePosition,
        frame_index: int,
        locked_track_ids: set[int],
        track_hints: dict[int, str],
        diagnostics: list[PlayerIdentityDiagnostic],
        newly_locked: list[str],
    ) -> None:
        half_length = self.court.length_ft / 2.0
        if pos.court_position is not None:
            side = "near" if pos.court_position[1] < half_length else "far"
            if slot.assignment_side is None:
                slot.assignment_side = side
        if slot.state == "searching":
            if slot.assignment_side and not self._side_has_capacity(slot.assignment_side):
                return
            slot.observed_frames = 1
            if slot.observed_frames >= self.config.plausible_min_hits:
                slot.state = "tentative"
        elif slot.state == "tentative":
            slot.observed_frames += 1
            if slot.observed_frames >= self.config.lock_min_hits:
                slot.state = "locked"
                slot.locked_since_frame = frame_index
                slot.lost_frames = 0
                self._record_initial_lock(slot.identity_id, pos.track_id, frame_index)
                newly_locked.append(slot.identity_id)
                diagnostics.append(
                    PlayerIdentityDiagnostic(
                        frame_index=frame_index,
                        event="player_locked",
                        player_id=slot.identity_id,
                        track_id=pos.track_id,
                        reason=f"consecutive_hits={slot.observed_frames}",
                        court_position_m=list(pos.court_position) if pos.court_position else None,
                    )
                )
        elif slot.state == "fallback_tentative":
            slot.observed_frames += 1
            if slot.observed_frames >= self.config.fallback_promotion_frames:
                slot.state = "tentative"
                diagnostics.append(
                    PlayerIdentityDiagnostic(
                        frame_index=frame_index,
                        event="fallback_tentative_promoted",
                        player_id=slot.identity_id,
                        track_id=pos.track_id,
                        reason=f"fallback_promotion_frames={slot.observed_frames}",
                        court_position_m=list(pos.court_position) if pos.court_position else None,
                    )
                )
        locked_track_ids.add(pos.track_id)
        track_hints[pos.track_id] = slot.identity_id
        self._track_to_slot[pos.track_id] = slot.identity_id
        self._update_slot_from_position(slot, pos, frame_index)

    # ---------- lost / reconnect ----------

    def _handle_lost_slot(
        self,
        slot: PlayerSlot,
        frame_index: int,
        positions: Sequence[PlayerFramePosition],
        reconnect_candidates: set[int],
        track_hints: dict[int, str],
        diagnostics: list[PlayerIdentityDiagnostic],
    ) -> str:
        # 硬锁到底：LOST 是持久状态，槽位身份永久保留，绝不回退 SEARCHING、绝不让位。
        # lost_frames 仅用于诊断与状态展示；超过 lost_max_frames_locked 也不重置。
        slot.lost_frames += 1

        best_candidate, best_score = self._find_best_reconnect(slot, positions)
        if best_candidate is not None and best_score >= self.config.reconnect_threshold:
            # fix-multiview-player-identity D4/D5：重连前检查候选是否疑似来自他侧
            # （跨侧互换的兜底观测——正常路径已被 _candidate_side_conflicts 拦截，
            # 但若强证据绕过后仍要记录 identity_swap_suspected 供归因）。
            swap_reason = self._suspected_identity_swap_reason(slot, best_candidate)
            slot.state = "locked"
            slot.current_track_id = best_candidate.track_id
            self._record_initial_lock(slot.identity_id, best_candidate.track_id, frame_index)
            self._track_to_slot[best_candidate.track_id] = slot.identity_id
            track_hints[best_candidate.track_id] = slot.identity_id
            slot.lost_frames = 0
            details = self._reconnect_score_details(slot, best_candidate)
            if swap_reason:
                diagnostics.append(
                    PlayerIdentityDiagnostic(
                        frame_index=frame_index,
                        event="identity_swap_suspected",
                        player_id=slot.identity_id,
                        track_id=best_candidate.track_id,
                        score=best_score,
                        reason=swap_reason,
                        court_position_m=(
                            list(best_candidate.court_position) if best_candidate.court_position else None
                        ),
                    )
                )
            diagnostics.append(
                PlayerIdentityDiagnostic(
                    frame_index=frame_index,
                    event="player_reconnected_from_lost",
                    player_id=slot.identity_id,
                    track_id=best_candidate.track_id,
                    score=best_score,
                    reason=details,
                    court_position_m=list(best_candidate.court_position) if best_candidate.court_position else None,
                )
            )
            self._update_slot_from_position(slot, best_candidate, frame_index)
            return "recovered"

        return "still_lost"

    def _suspected_identity_swap_reason(self, slot: PlayerSlot, position: PlayerFramePosition) -> str | None:
        """fix-multiview-player-identity D5：判定重连是否疑似身份互换。

        返回 None（无嫌疑）或结构化 reason 字符串。两种嫌疑：
        1. 候选 track 当前属于其他槽位（_track_to_slot 指向别的 identity）→ 直接互换；
        2. 候选 court side 与槽位 home/side 语义冲突（跨侧兜底，正常路径被拦截）。
        """
        prev_owner = self._track_to_slot.get(position.track_id)
        if prev_owner is not None and prev_owner != slot.identity_id:
            return (
                f"track_owner_swap owner={prev_owner} slot={slot.identity_id} "
                f"home_quadrant={slot.home_quadrant or '?'} from_track={slot.current_track_id} "
                f"to_track={position.track_id}"
            )
        expected = slot.home_quadrant or slot.side_hint or slot.assignment_side
        if expected is None or position.court_position is None:
            return None
        expected_side = expected.split("_", 1)[0]
        if expected_side not in {"near", "far"}:
            return None
        actual_side = "near" if position.court_position[1] < self.court.length_ft / 2.0 else "far"
        if actual_side == expected_side:
            return None
        return (
            f"cross_side_reconnect home_quadrant={slot.home_quadrant or '?'} "
            f"candidate_side={actual_side} from_track={slot.current_track_id} to_track={position.track_id}"
        )

    def _find_best_reconnect(
        self, slot: PlayerSlot, positions: Sequence[PlayerFramePosition]
    ) -> tuple[PlayerFramePosition | None, float]:
        best_candidate: PlayerFramePosition | None = None
        best_score = 0.0
        for pos in positions:
            if not self._is_identity_candidate(pos):
                continue
            classification = self._classify_candidate(pos.court_position, "lost")
            if classification == "outside":
                continue
            if pos.confidence < self._conf_threshold_for_state("lost"):
                continue
            # fix-multiview-player-identity D4：跨侧候选直接不可选（防止 P1↔P2 互换）
            if self._candidate_side_conflicts(slot, pos):
                continue
            score = self._compute_reconnect_score(slot, pos)
            if score > best_score:
                best_score = score
                best_candidate = pos
        return best_candidate, best_score

    def _candidate_side_conflicts(self, slot: PlayerSlot, position: PlayerFramePosition) -> bool:
        """fix-multiview-player-identity D4：候选 side 与槽位 home/side 语义冲突判定。

        槽位有可用的 side 语义（home_quadrant / side_hint / assignment_side）且候选
        court_position 可判 side 时，若 side（near/far）不符 → 返回 True（拒绝重连）。
        槽位无 side 语义或候选无法判 side → 返回 False（不拦截，交既有评分门控）。
        """
        expected = slot.home_quadrant or slot.side_hint or slot.assignment_side
        if expected is None or position.court_position is None:
            return False
        expected_side = expected.split("_", 1)[0]
        if expected_side not in {"near", "far"}:
            return False
        actual_side = "near" if position.court_position[1] < self.court.length_ft / 2.0 else "far"
        return actual_side != expected_side

    def _compute_reconnect_score(self, slot: PlayerSlot, position: PlayerFramePosition) -> float:
        if slot.last_confirmed_position_m is None or position.court_position is None:
            return 0.0
        last_pos = slot.last_confirmed_position_m
        curr_pos = [float(position.court_position[0]), float(position.court_position[1])]

        dist = _distance(last_pos, curr_pos)

        # 硬距离门：候选超过"允许距离"（基础距离 + 估计速度 × 流逝时间）时直接拒绝，
        # 避免 position=0 的远距离错误候选靠 motion/side/bbox 分数补足阈值完成重连（P1 被错接到 P2 分身 track 的根因）。
        allowed_dist_ft = self.config.max_reconnect_distance_ft
        if self.config.reconnect_gate_enabled:
            elapsed_s = max(0.0, float(position.frame_index - slot.last_seen_frame)) / max(1.0, self.config.fps)
            speed_ft_s = 0.0
            if slot.last_velocity_mps is not None:
                speed_ft_s = meters_to_feet(hypot(slot.last_velocity_mps[0], slot.last_velocity_mps[1]))
            allowed_dist_ft = self.config.max_reconnect_distance_ft + speed_ft_s * elapsed_s
            if dist > allowed_dist_ft:
                return -1.0

        position_score = max(0.0, 1.0 - dist / max(1.0, allowed_dist_ft))

        motion_score = 0.5
        if slot.last_velocity_mps is not None:
            motion_score = _cosine_score(slot.last_velocity_mps, [curr_pos[0] - last_pos[0], curr_pos[1] - last_pos[1]])

        side_score = self._reconnect_side_score(slot, curr_pos)

        bbox_score = 0.5
        if slot.last_bbox is not None and position.bbox is not None:
            last_aspect = (slot.last_bbox[2] - slot.last_bbox[0]) / max(1.0, slot.last_bbox[3] - slot.last_bbox[1])
            curr_aspect = (position.bbox[2] - position.bbox[0]) / max(1.0, position.bbox[3] - position.bbox[1])
            ratio = min(last_aspect, curr_aspect) / max(1e-6, max(last_aspect, curr_aspect))
            bbox_score = max(0.0, min(1.0, ratio))

        score = position_score * 0.40 + motion_score * 0.30 + side_score * 0.20 + bbox_score * 0.10
        # fix-multiview-player-identity D4：同侧但横向错配（near_left 槽位接 near_right 候选）
        # 时对总分施加强乘法惩罚，使 position/motion 高分无法单独凑够 reconnect_threshold。
        if slot.home_quadrant is not None and position.court_position is not None and "_" in slot.home_quadrant:
            expected_side, expected_lateral = slot.home_quadrant.split("_", 1)
            actual_side = "near" if position.court_position[1] < self.court.length_ft / 2.0 else "far"
            if actual_side == expected_side:
                actual_lateral = "left" if position.court_position[0] < self.court.width_ft / 2.0 else "right"
                if actual_lateral != expected_lateral:
                    score *= self.config.reconnect_lateral_mismatch_penalty
        return score

    def _reconnect_score_details(self, slot: PlayerSlot, position: PlayerFramePosition) -> str:
        if slot.last_confirmed_position_m is None or position.court_position is None:
            return "no_last_position"
        last_pos = slot.last_confirmed_position_m
        curr_pos = [float(position.court_position[0]), float(position.court_position[1])]
        dist = _distance(last_pos, curr_pos)
        position_score = max(0.0, 1.0 - dist / max(1.0, self.config.max_reconnect_distance_ft))
        motion_score = 0.5
        if slot.last_velocity_mps is not None:
            motion_score = _cosine_score(slot.last_velocity_mps, [curr_pos[0] - last_pos[0], curr_pos[1] - last_pos[1]])
        side_score = self._reconnect_side_score(slot, curr_pos)
        bbox_score = 0.5
        if slot.last_bbox is not None and position.bbox is not None:
            last_aspect = (slot.last_bbox[2] - slot.last_bbox[0]) / max(1.0, slot.last_bbox[3] - slot.last_bbox[1])
            curr_aspect = (position.bbox[2] - position.bbox[0]) / max(1.0, position.bbox[3] - position.bbox[1])
            ratio = min(last_aspect, curr_aspect) / max(1e-6, max(last_aspect, curr_aspect))
            bbox_score = max(0.0, min(1.0, ratio))
        return f"position={position_score:.2f} motion={motion_score:.2f} side={side_score:.2f} bbox={bbox_score:.2f}"

    def _reconnect_side_score(self, slot: PlayerSlot, position: list[float]) -> float:
        """Score current side and home quadrant without making either an ID."""
        expected = slot.side_hint or slot.home_quadrant or slot.assignment_side
        if expected is None:
            return 0.5
        actual_side = "near" if position[1] < self.court.length_ft / 2.0 else "far"
        expected_side = expected.split("_", 1)[0]
        if actual_side != expected_side:
            return 0.2
        if "_" not in expected or self.config.target_player_count <= 2:
            return 1.0
        actual_lateral = "left" if position[0] < self.court.width_ft / 2.0 else "right"
        expected_lateral = expected.split("_", 1)[1]
        return 1.0 if actual_lateral == expected_lateral else self.config.reconnect_lateral_mismatch_score


# ---------- internal helpers ----------


def is_court_side_decidable(court_position: Sequence[float] | None, court, dead_zone_ft: float = 2.0) -> bool:
    """fix-multiview-cam1-bootstrap-4player D1：court 纵向（y）是否可判 near/far。

    判定条件：court_position 非 None、长度 >= 2、且 court y 不在 SIDE_DEAD_ZONE
    （|y - half_length| >= dead_zone）。横向（x）不参与判定——x 超出 tracking
    bounds 不影响"该候选属于球场纵深内"的事实，可由图像位置松弛映射兜底象限。
    """
    if court_position is None or len(court_position) < 2:
        return False
    half_length = court.length_ft / 2.0
    return abs(float(court_position[1]) - half_length) >= dead_zone_ft


def _cosine_score(a: list[float], b: list[float]) -> float:
    norm_a = hypot(a[0], a[1])
    norm_b = hypot(b[0], b[1])
    if norm_a < 1e-6 or norm_b < 1e-6:
        return 0.5
    cosine = (a[0] * b[0] + a[1] * b[1]) / (norm_a * norm_b)
    return max(0.0, min(1.0, (cosine + 1.0) / 2.0))


def _norm(vector: list[float]) -> float:
    return hypot(vector[0], vector[1])


@dataclass
class _BootstrapTracklet:
    SIDE_DEAD_ZONE_FT = 2.0

    frame_indices: list[int] = field(default_factory=list)
    confidences: list[float] = field(default_factory=list)
    court_xs: list[float] = field(default_factory=list)
    court_ys: list[float] = field(default_factory=list)
    bbox_centers: list[tuple[float, float]] = field(default_factory=list)
    # fix-multiview-player-identity D3：bbox 面积记录（近端大尺寸优先排序用）
    bbox_areas: list[float] = field(default_factory=list)

    def mean_confidence(self) -> float:
        return sum(self.confidences) / len(self.confidences) if self.confidences else 0.0

    def mean_bbox_area(self) -> float:
        return sum(self.bbox_areas) / len(self.bbox_areas) if self.bbox_areas else 0.0

    def is_near_large(self, half_length: float, frame_area: float, ratio: float) -> bool:
        """fix-multiview-player-identity D3：近端 + 大尺寸候选判定。

        近端 = 球场坐标 y 中位 < 半场（22ft，网线以内）；大尺寸 = 平均 bbox 面积
        占画面面积比例 >= 阈值。两条件同时满足才为 true（配合置信度门控防误锁）。
        """
        if not self.court_ys or frame_area <= 0 or ratio <= 0:
            return False
        median_y = statistics.median(self.court_ys)
        if median_y >= half_length:
            return False
        return self.mean_bbox_area() / frame_area >= ratio

    def inferred_side(self, half_length: float) -> str | None:
        if not self.court_ys:
            return None
        median_y = statistics.median(self.court_ys)
        if abs(median_y - half_length) < self.SIDE_DEAD_ZONE_FT:
            return None
        return "near" if median_y < half_length else "far"

    def inferred_lateral(self, half_width: float) -> str | None:
        if not self.court_xs:
            return None
        median_x = statistics.median(self.court_xs)
        if abs(median_x - half_width) < self.SIDE_DEAD_ZONE_FT:
            return None
        return "left" if median_x < half_width else "right"

    def inferred_image_lateral(self, frame_width: int | None) -> str | None:
        """fix-multiview-cam1-bootstrap-4player D2：图像 bbox 中心 x 推断 left/right。

        court 投影 x 无法判横向（半场死区或超出 tracking bounds）时，用平均 bbox
        中心 x 与画面宽度 50% 分界比较。缺失画面尺寸或 bbox 记录时返回 None。
        """
        if not self.bbox_centers or not frame_width or frame_width <= 0:
            return None
        median_center_x = statistics.median(center_x for center_x, _center_y in self.bbox_centers)
        return "left" if median_center_x < frame_width / 2.0 else "right"

    def mean_center_distance(self, frame_width: int | None, frame_height: int | None) -> float:
        # bbox 中心到画面中心的平均距离（像素）；缺失画面尺寸时返回 0（退化按置信度排序）。
        if not self.bbox_centers or not frame_width or not frame_height:
            return 0.0
        center_x = frame_width / 2.0
        center_y = frame_height / 2.0
        total = sum(hypot(px - center_x, py - center_y) for px, py in self.bbox_centers)
        return total / len(self.bbox_centers)
