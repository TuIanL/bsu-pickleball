"""球员锁定管理器 —— 保持四名主球员的身份稳定性，跨帧锁定与重连。"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from math import hypot
from typing import Sequence

from app.schemas.tracking import (
    PlayerFramePosition,
    PlayerIdentityDiagnostic,
)
from app.vision.courtvision_calibration_engine.court_geometry import standard_court, PickleballCourtGeometry
from app.vision.player_tracking_engine.player_lock_types import (
    PlayerLockConfig,
    PlayerLockUpdate,
    PlayerSlot,
)


def _distance(a: list[float], b: list[float]) -> float:
    return hypot(a[0] - b[0], a[1] - b[1])


class PlayerLockManager:
    def __init__(self, config: PlayerLockConfig | None = None) -> None:
        self.config = config or PlayerLockConfig()
        self.court = standard_court()
        self.slots: dict[str, PlayerSlot] = {}
        self._bootstrap_complete = False
        self._bootstrap_tracklets: dict[int, _BootstrapTracklet] = {}
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

        locked_track_ids: set[int] = set()
        for slot in self.slots.values():
            if slot.state in {"locked", "lost"} and slot.current_track_id is not None:
                locked_track_ids.add(slot.current_track_id)

        if not self._bootstrap_complete and frame_index < self.config.bootstrap_max_frames:
            self._run_bootstrap(frame_index, positions)

        if frame_index >= self.config.bootstrap_max_frames and not self._bootstrap_complete:
            self._finalize_bootstrap(frame_index)

        reconnect_candidates: set[int] = set()
        track_hints: dict[int, str] = {}
        diagnostics: list[PlayerIdentityDiagnostic] = []
        newly_locked: list[str] = []
        newly_lost: list[str] = []

        for slot in self.slots.values():
            if slot.state == "locked":
                matched = self._find_matching_position(slot, positions)
                if matched is not None:
                    self._update_slot_from_position(slot, matched, frame_index)
                    locked_track_ids.add(matched.track_id)
                    self._track_to_slot[matched.track_id] = slot.identity_id
                    track_hints[matched.track_id] = slot.identity_id
                else:
                    prev_state = slot.state
                    slot.lost_frames += 1
                    if slot.lost_frames >= self.config.lost_grace_frames:
                        slot.state = "lost"
                        slot.current_track_id = None
                        if prev_state != "lost":
                            newly_lost.append(slot.identity_id)

            elif slot.state == "lost":
                if self._handle_lost_slot(slot, frame_index, positions, reconnect_candidates, track_hints, diagnostics) == "recovered":
                    newly_locked.append(slot.identity_id)

            elif slot.state in {"searching", "tentative", "fallback_tentative"}:
                if not self._bootstrap_complete:
                    continue
                matched = self._find_new_candidate(slot, positions, locked_track_ids | reconnect_candidates)
                if matched is not None:
                    if slot.state == "fallback_tentative" and self._can_replace_fallback(slot, matched.track_id, matched.confidence):
                        diagnostics.append(PlayerIdentityDiagnostic(
                            frame_index=frame_index,
                            event="side_quota_fallback_replaced",
                            player_id=slot.identity_id,
                            track_id=matched.track_id,
                            reason=f"fallback_replaced; old_track={slot.current_track_id}",
                            court_position_m=list(matched.court_position) if matched.court_position else None,
                        ))
                        slot.state = "searching"
                        slot.current_track_id = None
                    self._try_lock_slot(slot, matched, frame_index, locked_track_ids, track_hints, diagnostics, newly_locked)

        eligible_track_ids = locked_track_ids | reconnect_candidates

        player_states = {
            slot.identity_id: slot.state
            for slot in self.slots.values()
        }

        return PlayerLockUpdate(
            eligible_track_ids=eligible_track_ids,
            track_identity_hints=track_hints,
            player_states=player_states,
            diagnostics=diagnostics,
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
            1 for slot in self.slots.values()
            if slot.assignment_side == "near"
            and slot.state in ("tentative", "locked", "lost", "fallback_tentative")
        )

    @property
    def far_occupancy(self) -> int:
        return sum(
            1 for slot in self.slots.values()
            if slot.assignment_side == "far"
            and slot.state in ("tentative", "locked", "lost", "fallback_tentative")
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
            if not pos.valid or pos.court_position is None:
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
                tl.bbox_centers.append(
                    ((pos.bbox[0] + pos.bbox[2]) / 2.0, (pos.bbox[1] + pos.bbox[3]) / 2.0)
                )

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
                self._track_to_slot[track_id] = slot.identity_id
                assigned.add(track_id)
        self._bootstrap_complete = True

    def _bootstrap_candidate_entries(self) -> list[tuple[int, _BootstrapTracklet]]:
        # 已通过门控/置信度过滤的候选，按"画面中心距离升序、置信度/出现帧数降序"排序（中心优先、向外扩散）。
        entries: list[tuple[int, _BootstrapTracklet]] = []
        for track_id, tl in self._bootstrap_tracklets.items():
            if len(tl.frame_indices) < self.config.min_observed_frames:
                continue
            if tl.mean_confidence() < self.config.searching_conf:
                continue
            entries.append((track_id, tl))
        entries.sort(
            key=lambda item: (
                item[1].mean_center_distance(self._frame_width, self._frame_height),
                -item[1].mean_confidence(),
                -len(item[1].frame_indices),
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
                frame_index=frame_index,
                confidence=tl.mean_confidence(),
                observed_frames=len(tl.frame_indices),
            )
            if slot.current_track_id == track_id:
                assigned.add(track_id)

    def _infer_quadrant(self, tl: _BootstrapTracklet) -> str | None:
        # 由球场中位坐标推断候选归属象限（近左/近右/远左/远右）；单打退化为近/远。
        half_length = self.court.length_ft / 2.0
        half_width = self.court.width_ft / 2.0
        side = tl.inferred_side(half_length)
        if side is None:
            return None
        if self.config.target_player_count <= 2:
            return side
        lateral = tl.inferred_lateral(half_width)
        if lateral is None:
            return None
        return f"{side}_{lateral}"

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

    def _is_in_court_neighborhood(self, court_position: list[float], margin_ft: float) -> bool:
        x, y = court_position[0], court_position[1]
        return (
            -margin_ft <= x <= self.court.width_ft + margin_ft
            and -margin_ft <= y <= self.court.length_ft + margin_ft
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

    def _find_matching_position(self, slot: PlayerSlot, positions: Sequence[PlayerFramePosition]) -> PlayerFramePosition | None:
        if slot.current_track_id is not None:
            for pos in positions:
                if pos.track_id == slot.current_track_id and pos.valid and pos.court_position is not None:
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
            if not pos.valid or pos.court_position is None:
                continue
            if pos.track_id in exclude_track_ids:
                continue
            classification = self._classify_candidate(pos.court_position, slot.state)
            if classification not in {"inside_court", "near_court_area"}:
                continue
            if pos.confidence >= self._conf_threshold_for_state(slot.state) and pos.confidence > best_conf:
                best = pos
                best_conf = pos.confidence
        return best

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

    def _try_lock_slot(
        self, slot: PlayerSlot, pos: PlayerFramePosition, frame_index: int,
        locked_track_ids: set[int], track_hints: dict[int, str],
        diagnostics: list[PlayerIdentityDiagnostic], newly_locked: list[str],
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
                newly_locked.append(slot.identity_id)
                diagnostics.append(PlayerIdentityDiagnostic(
                    frame_index=frame_index,
                    event="player_locked",
                    player_id=slot.identity_id,
                    track_id=pos.track_id,
                    reason=f"consecutive_hits={slot.observed_frames}",
                    court_position_m=list(pos.court_position) if pos.court_position else None,
                ))
        elif slot.state == "fallback_tentative":
            slot.observed_frames += 1
            if slot.observed_frames >= self.config.fallback_promotion_frames:
                slot.state = "tentative"
                diagnostics.append(PlayerIdentityDiagnostic(
                    frame_index=frame_index,
                    event="fallback_tentative_promoted",
                    player_id=slot.identity_id,
                    track_id=pos.track_id,
                    reason=f"fallback_promotion_frames={slot.observed_frames}",
                    court_position_m=list(pos.court_position) if pos.court_position else None,
                ))
        locked_track_ids.add(pos.track_id)
        track_hints[pos.track_id] = slot.identity_id
        self._track_to_slot[pos.track_id] = slot.identity_id
        self._update_slot_from_position(slot, pos, frame_index)

    # ---------- lost / reconnect ----------

    def _handle_lost_slot(
        self, slot: PlayerSlot, frame_index: int, positions: Sequence[PlayerFramePosition],
        reconnect_candidates: set[int], track_hints: dict[int, str],
        diagnostics: list[PlayerIdentityDiagnostic],
    ) -> str:
        # 硬锁到底：LOST 是持久状态，槽位身份永久保留，绝不回退 SEARCHING、绝不让位。
        # lost_frames 仅用于诊断与状态展示；超过 lost_max_frames_locked 也不重置。
        slot.lost_frames += 1

        best_candidate, best_score = self._find_best_reconnect(slot, positions)
        if best_candidate is not None and best_score >= self.config.reconnect_threshold:
            slot.state = "locked"
            slot.current_track_id = best_candidate.track_id
            self._track_to_slot[best_candidate.track_id] = slot.identity_id
            track_hints[best_candidate.track_id] = slot.identity_id
            slot.lost_frames = 0
            details = self._reconnect_score_details(slot, best_candidate)
            diagnostics.append(PlayerIdentityDiagnostic(
                frame_index=frame_index,
                event="player_reconnected_from_lost",
                player_id=slot.identity_id,
                track_id=best_candidate.track_id,
                score=best_score,
                reason=details,
                court_position_m=list(best_candidate.court_position) if best_candidate.court_position else None,
            ))
            self._update_slot_from_position(slot, best_candidate, frame_index)
            return "recovered"

        return "still_lost"

    def _find_best_reconnect(
        self, slot: PlayerSlot, positions: Sequence[PlayerFramePosition]
    ) -> tuple[PlayerFramePosition | None, float]:
        best_candidate: PlayerFramePosition | None = None
        best_score = 0.0
        for pos in positions:
            if not pos.valid or pos.court_position is None:
                continue
            classification = self._classify_candidate(pos.court_position, "lost")
            if classification == "outside":
                continue
            if pos.confidence < self._conf_threshold_for_state("lost"):
                continue
            score = self._compute_reconnect_score(slot, pos)
            if score > best_score:
                best_score = score
                best_candidate = pos
        return best_candidate, best_score

    def _compute_reconnect_score(self, slot: PlayerSlot, position: PlayerFramePosition) -> float:
        if slot.last_confirmed_position_m is None or position.court_position is None:
            return 0.0
        last_pos = slot.last_confirmed_position_m
        curr_pos = [float(position.court_position[0]), float(position.court_position[1])]

        dist = _distance(last_pos, curr_pos)
        position_score = max(0.0, 1.0 - dist / max(1.0, self.config.max_reconnect_distance_ft))

        motion_score = 0.5
        if slot.last_velocity_mps is not None:
            motion_score = _cosine_score(slot.last_velocity_mps, [curr_pos[0] - last_pos[0], curr_pos[1] - last_pos[1]])

        side_score = 0.5
        if slot.side_hint is not None:
            side = "near" if curr_pos[1] < self.court.length_ft / 2.0 else "far"
            expected_side = slot.side_hint.split("_")[0] if "_" in slot.side_hint else ""
            side_score = 1.0 if side == expected_side else 0.2

        bbox_score = 0.5
        if slot.last_bbox is not None and position.bbox is not None:
            last_aspect = (slot.last_bbox[2] - slot.last_bbox[0]) / max(1.0, slot.last_bbox[3] - slot.last_bbox[1])
            curr_aspect = (position.bbox[2] - position.bbox[0]) / max(1.0, position.bbox[3] - position.bbox[1])
            ratio = min(last_aspect, curr_aspect) / max(1e-6, max(last_aspect, curr_aspect))
            bbox_score = max(0.0, min(1.0, ratio))

        return position_score * 0.40 + motion_score * 0.30 + side_score * 0.20 + bbox_score * 0.10

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
        side = "near" if curr_pos[1] < self.court.length_ft / 2.0 else "far"
        expected_side = slot.side_hint.split("_")[0] if slot.side_hint and "_" in slot.side_hint else ""
        side_score = 1.0 if side == expected_side else 0.2
        bbox_score = 0.5
        if slot.last_bbox is not None and position.bbox is not None:
            last_aspect = (slot.last_bbox[2] - slot.last_bbox[0]) / max(1.0, slot.last_bbox[3] - slot.last_bbox[1])
            curr_aspect = (position.bbox[2] - position.bbox[0]) / max(1.0, position.bbox[3] - position.bbox[1])
            ratio = min(last_aspect, curr_aspect) / max(1e-6, max(last_aspect, curr_aspect))
            bbox_score = max(0.0, min(1.0, ratio))
        return f"position={position_score:.2f} motion={motion_score:.2f} side={side_score:.2f} bbox={bbox_score:.2f}"


# ---------- internal helpers ----------

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

    def mean_confidence(self) -> float:
        return sum(self.confidences) / len(self.confidences) if self.confidences else 0.0

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

    def mean_center_distance(self, frame_width: int | None, frame_height: int | None) -> float:
        # bbox 中心到画面中心的平均距离（像素）；缺失画面尺寸时返回 0（退化按置信度排序）。
        if not self.bbox_centers or not frame_width or not frame_height:
            return 0.0
        center_x = frame_width / 2.0
        center_y = frame_height / 2.0
        total = sum(hypot(px - center_x, py - center_y) for px, py in self.bbox_centers)
        return total / len(self.bbox_centers)
