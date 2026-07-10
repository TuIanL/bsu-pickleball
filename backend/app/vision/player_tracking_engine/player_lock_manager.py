"""球员锁定管理器 —— 保持四名主球员的身份稳定性，跨帧锁定与重连。"""

from __future__ import annotations

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

        for idx in range(self.config.target_player_count):
            identity_id = f"player_{idx + 1}"
            self.slots[identity_id] = PlayerSlot(identity_id=identity_id)

    def update(
        self,
        frame_index: int,
        positions: Sequence[PlayerFramePosition],
        suggestions: Sequence | None = None,
        frame=None,
    ) -> PlayerLockUpdate:
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

            elif slot.state in {"searching", "tentative"}:
                if not self._bootstrap_complete:
                    continue
                matched = self._find_new_candidate(slot, positions, locked_track_ids | reconnect_candidates)
                if matched is not None:
                    self._try_lock_slot(slot, matched, frame_index, locked_track_ids, track_hints, diagnostics, newly_locked)

        eligible_track_ids = suggested_ids | locked_track_ids | reconnect_candidates

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
            if not self._is_in_near_court_area(pos.court_position, self.config.bootstrap_court_margin_ft):
                continue
            tl = self._bootstrap_tracklets.setdefault(pos.track_id, _BootstrapTracklet())
            tl.frame_indices.append(frame_index)
            tl.confidences.append(pos.confidence)
            if pos.court_position is not None:
                tl.court_xs.append(pos.court_position[0])
                tl.court_ys.append(pos.court_position[1])

    def _try_early_lock(self, frame_index: int) -> None:
        for track_id, tl in list(self._bootstrap_tracklets.items()):
            if len(tl.frame_indices) < self.config.min_observed_frames:
                continue
            if tl.mean_confidence() < self.config.searching_conf:
                continue
            for slot in self.slots.values():
                if slot.state != "searching":
                    continue
                slot.state = "tentative"
                slot.current_track_id = track_id
                slot.track_id_history = [track_id]
                slot.last_seen_frame = frame_index
                slot.confidence_ema = tl.mean_confidence()
                slot.observed_frames = len(tl.frame_indices)
                if slot.observed_frames >= self.config.lock_min_hits:
                    slot.state = "locked"
                    slot.locked_since_frame = frame_index
                    slot.lost_frames = 0
                self._track_to_slot[track_id] = slot.identity_id
                break

    def _finalize_bootstrap(self, frame_index: int) -> None:
        candidates: list[tuple[int, _BootstrapTracklet]] = []
        for track_id, tl in self._bootstrap_tracklets.items():
            if len(tl.frame_indices) < self.config.min_observed_frames:
                continue
            if tl.mean_confidence() < self.config.searching_conf:
                continue
            candidates.append((track_id, tl))
        candidates.sort(key=lambda item: (item[1].mean_confidence(), len(item[1].frame_indices)), reverse=True)

        assigned: set[int] = set()
        for slot in self.slots.values():
            if slot.state != "searching":
                assigned.add(slot.current_track_id or -1)
                continue
        for track_id, tl in candidates:
            if track_id in assigned:
                continue
            for slot in self.slots.values():
                if slot.state != "searching":
                    continue
                slot.state = "tentative"
                slot.current_track_id = track_id
                slot.track_id_history = [track_id]
                slot.last_seen_frame = frame_index
                slot.confidence_ema = tl.mean_confidence()
                slot.observed_frames = len(tl.frame_indices)
                if slot.observed_frames >= self.config.lock_min_hits:
                    slot.state = "locked"
                    slot.locked_since_frame = frame_index
                    slot.lost_frames = 0
                self._track_to_slot[track_id] = slot.identity_id
                self._assign_side_hint(slot, tl)
                assigned.add(track_id)
                break
        self._bootstrap_complete = True

    def _assign_side_hint(self, slot: PlayerSlot, tl: _BootstrapTracklet) -> None:
        if not tl.court_xs or not tl.court_ys:
            return
        mean_x = sum(tl.court_xs) / len(tl.court_xs)
        mean_y = sum(tl.court_ys) / len(tl.court_ys)
        side = "near" if mean_y < self.court.length_ft / 2.0 else "far"
        left_right = "left" if mean_x < self.court.width_ft / 2.0 else "right"
        slot.side_hint = f"{side}_{left_right}"

    # ---------- spatial gating ----------

    def _is_in_near_court_area(self, court_position: list[float], margin_ft: float) -> bool:
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
            if self._is_in_near_court_area(court_position, margin):
                return "near_court_area"
            if self.court.is_in_tracking_bounds(court_position[0], court_position[1]):
                return "tracking_area"
        else:
            if self._is_in_near_court_area(court_position, margin):
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
        if slot.state == "searching":
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
        slot.lost_frames += 1
        if slot.lost_frames > self.config.lost_max_frames_locked:
            slot.state = "searching"
            slot.current_track_id = None
            slot.lost_frames = 0
            slot.observed_frames = 0
            diagnostics.append(PlayerIdentityDiagnostic(
                frame_index=frame_index,
                event="player_reset_after_prolonged_loss",
                player_id=slot.identity_id,
                reason=f"lost_frames={slot.lost_frames}",
            ))
            return "reset"

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
    frame_indices: list[int] = field(default_factory=list)
    confidences: list[float] = field(default_factory=list)
    court_xs: list[float] = field(default_factory=list)
    court_ys: list[float] = field(default_factory=list)

    def mean_confidence(self) -> float:
        return sum(self.confidences) / len(self.confidences) if self.confidences else 0.0
