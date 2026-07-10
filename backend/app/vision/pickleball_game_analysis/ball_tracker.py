"""Ball candidate filtering and trajectory continuity tracking with state-aware locking and physics gating."""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, field
from math import hypot
from typing import Any

import numpy as np

from app.vision.pickleball_game_analysis.ball_detector_protocol import BallDetectorProtocol
from app.vision.pickleball_game_analysis.court_adapter import BallCourtAdapter
from app.vision.pickleball_game_analysis.schemas import (
    BallCandidate,
    BallCandidateDebug,
    BallFrameDebug,
    BallFrameSample,
    BallTrackState,
    Point2D,
)


@dataclass(frozen=True)
class BallTrackerConfig:
    """
    球跟踪器超参数（全部带默认值，可调）。

    思路：先用"框尺寸/长宽比/ROI"过滤掉明显不是球的候选，
    再用"轨迹连续性"（动态距离门限、预测门限、最大缺失帧）从剩余候选里挑最可信的一个。
    """

    confidence: float = 0.18
    trajectory_length: int = 30
    max_jump_pixels: float = 220.0
    prediction_gate_pixels: float = 260.0
    max_missing_frames: int = 5
    roi_padding_ratio: float = 0.08
    max_box_area_ratio: float = 0.004
    max_aspect_ratio: float = 4.0
    court_bounds_margin_ft: float = 2.0
    stationary_window_frames: int = 30
    stationary_radius_pixels: float = 5.0
    stationary_blacklist_frames: int = 60
    stationary_blacklist_grid_px: int = 5

    # Track lock state machine
    tentative_min_hits: int = 2
    lock_min_hits: int = 4
    max_missing_frames_locked: int = 10

    # Smoothed prediction
    min_prediction_points: int = 3

    # Dynamic physics gate
    base_gate_pixels: float = 60.0
    speed_factor: float = 1.5
    missing_factor: float = 30.0
    min_gate_pixels: float = 50.0
    max_gate_pixels: float = 600.0

    # Player motion context
    player_motion_min_pixels: float = 15.0

    # State-aware scoring weights
    searching_confidence_weight: float = 1000.0
    searching_distance_weight: float = 1.4
    tentative_confidence_weight: float = 700.0
    tentative_distance_weight: float = 2.0
    locked_confidence_weight: float = 300.0
    locked_distance_weight: float = 3.0
    lost_confidence_weight: float = 300.0
    lost_distance_weight: float = 3.0
    lost_gate_multiplier: float = 1.5


class BallTracker:
    """逐帧处理：过滤候选、挑选最可信的球位置、维护轨迹连续性，并投影到球场坐标。"""

    def __init__(
        self,
        detector: BallDetectorProtocol,
        config: BallTrackerConfig | None = None,
        court_adapter: BallCourtAdapter | None = None,
    ) -> None:
        self.detector = detector
        self.config = config or BallTrackerConfig()
        self.court_adapter = court_adapter or BallCourtAdapter()
        self.trajectory: deque[Point2D] = deque(maxlen=self.config.trajectory_length)
        self.selected_history: deque[Point2D] = deque(maxlen=max(1, self.config.stationary_window_frames))
        self.last_valid_position: Point2D | None = None
        self.missing_frames = 0
        self._stationary_blacklist: dict[tuple[int, int], int] = {}
        self._stationary_blacklist_positions: set[tuple[int, int]] = set()
        self.track_state: BallTrackState = BallTrackState.SEARCHING
        self._lock_hits: int = 0
        self._cached_frame_height: float = 0.0

    def update(
        self,
        frame: np.ndarray,
        frame_index: int,
        timestamp_sec: float,
        roi_corners: tuple[tuple[int, int], tuple[int, int]] | None = None,
        homography: Sequence[Sequence[float]] | None = None,
        player_motion_pixels: float | None = None,
    ) -> BallFrameSample:
        self._cached_frame_height = float(frame.shape[0])
        raw_candidates = self.detector.detect(frame, conf=self.config.confidence)
        candidates, extract_reasons = self._extract_candidates(raw_candidates, frame.shape, roi_corners)
        self._update_stationary_blacklist(candidates)

        predicted_pos = self._predict_next_position() if self.trajectory else None

        # State-aware candidate selection
        selected, overall_decision, select_reason = self._select_candidate(candidates)

        # Build per-candidate debug info
        candidate_debugs = self._build_candidate_debugs(candidates, selected, predicted_pos)

        # Case A: No candidate selected
        if selected is None:
            self._record_missing_detection()
            self._update_track_state(False)
            reason = select_reason or (extract_reasons[0] if extract_reasons else "no_candidates")
            return self._build_sample(
                frame_index=frame_index,
                timestamp_sec=timestamp_sec,
                image_xy=None,
                court_xy=None,
                confidence=None,
                visible=bool(raw_candidates),
                accepted=False,
                candidate_count=len(candidates),
                reject_reason=reason,
                in_bounds=None,
                predicted_pos=predicted_pos,
                overall_decision=overall_decision,
                candidate_debugs=candidate_debugs,
                accepted_candidate_id=None,
            )

        point = selected.image_xy
        self._record_selected_candidate(point)

        # Stationary blacklist check
        blacklist_reason = self._stationary_blacklist_reject_reason(point)
        if blacklist_reason is not None:
            self._record_missing_detection()
            self._update_track_state(False)
            return self._build_sample(
                frame_index=frame_index,
                timestamp_sec=timestamp_sec,
                image_xy=point,
                court_xy=None,
                confidence=selected.confidence,
                visible=True,
                accepted=False,
                candidate_count=len(candidates),
                reject_reason=blacklist_reason,
                in_bounds=None,
                predicted_pos=predicted_pos,
                overall_decision="rejected",
                candidate_debugs=candidate_debugs,
                accepted_candidate_id=None,
            )

        # Player-motion-aware static false-positive check (runs first to capture context)
        pm_static_reason = self._player_motion_static_reject_reason(point, player_motion_pixels)
        if pm_static_reason is not None:
            self._record_missing_detection()
            self._update_track_state(False)
            return self._build_sample(
                frame_index=frame_index,
                timestamp_sec=timestamp_sec,
                image_xy=point,
                court_xy=None,
                confidence=selected.confidence,
                visible=True,
                accepted=False,
                candidate_count=len(candidates),
                reject_reason=pm_static_reason,
                in_bounds=None,
                predicted_pos=predicted_pos,
                overall_decision="rejected",
                candidate_debugs=candidate_debugs,
                accepted_candidate_id=None,
            )

        # Short-term stationary candidate check (generic, no player context)
        stationary_reason = self._stationary_reject_reason()
        if stationary_reason is not None:
            self._record_missing_detection()
            self._update_track_state(False)
            return self._build_sample(
                frame_index=frame_index,
                timestamp_sec=timestamp_sec,
                image_xy=point,
                court_xy=None,
                confidence=selected.confidence,
                visible=True,
                accepted=False,
                candidate_count=len(candidates),
                reject_reason=stationary_reason,
                in_bounds=None,
                predicted_pos=predicted_pos,
                overall_decision="rejected",
                candidate_debugs=candidate_debugs,
                accepted_candidate_id=None,
            )

        # Continuity check (now uses dynamic gate)
        continuity_reason = self._continuity_reject_reason(point)
        if continuity_reason is not None:
            self._record_missing_detection()
            self._update_track_state(False)
            return self._build_sample(
                frame_index=frame_index,
                timestamp_sec=timestamp_sec,
                image_xy=point,
                court_xy=None,
                confidence=selected.confidence,
                visible=True,
                accepted=False,
                candidate_count=len(candidates),
                reject_reason=continuity_reason,
                in_bounds=None,
                predicted_pos=predicted_pos,
                overall_decision="rejected",
                candidate_debugs=candidate_debugs,
                accepted_candidate_id=None,
            )

        # Court bounds check
        projection = self.court_adapter.project(point, homography)
        bounds_reason = self._court_bounds_reject_reason(projection.court_xy)
        if bounds_reason is not None:
            self._record_missing_detection()
            self._update_track_state(False)
            return self._build_sample(
                frame_index=frame_index,
                timestamp_sec=timestamp_sec,
                image_xy=point,
                court_xy=projection.court_xy,
                confidence=selected.confidence,
                visible=True,
                accepted=False,
                candidate_count=len(candidates),
                reject_reason=bounds_reason,
                in_bounds=projection.in_bounds,
                predicted_pos=predicted_pos,
                overall_decision="rejected",
                candidate_debugs=candidate_debugs,
                accepted_candidate_id=None,
            )

        # Accepted! Record valid point and update track state
        self._append_valid_point(point)
        self._update_track_state(True)
        return self._build_sample(
            frame_index=frame_index,
            timestamp_sec=timestamp_sec,
            image_xy=point,
            court_xy=projection.court_xy,
            confidence=selected.confidence,
            visible=True,
            accepted=True,
            candidate_count=len(candidates),
            reject_reason=None,
            in_bounds=projection.in_bounds,
            predicted_pos=predicted_pos,
            overall_decision="accepted",
            candidate_debugs=candidate_debugs,
            accepted_candidate_id=str(selected.image_xy),
        )

    def clear(self) -> None:
        """重置跟踪状态（换一段新视频/新作业时调用）。"""
        self.trajectory.clear()
        self.selected_history.clear()
        self.last_valid_position = None
        self.missing_frames = 0
        self._lock_hits = 0
        self.track_state = BallTrackState.SEARCHING
        self._stationary_blacklist.clear()
        self._stationary_blacklist_positions.clear()

    # ── candidate extraction ──────────────────────────────────────

    def _extract_candidates(
        self,
        candidates: Sequence[BallCandidate],
        frame_shape: Sequence[int],
        roi_corners: tuple[tuple[int, int], tuple[int, int]] | None,
    ) -> tuple[list[BallCandidate], list[str]]:
        filtered: list[BallCandidate] = []
        reject_reasons: list[str] = []
        frame_area = max(1.0, float(frame_shape[0] * frame_shape[1]))

        for candidate in candidates:
            width = candidate.width
            height = candidate.height
            area_ratio = candidate.area_ratio
            aspect_ratio = candidate.aspect_ratio
            if width is not None and height is not None:
                if width <= 0 or height <= 0:
                    reject_reasons.append("invalid_box")
                    continue
                area_ratio = area_ratio if area_ratio is not None else (float(width) * float(height)) / frame_area
                aspect_ratio = aspect_ratio if aspect_ratio is not None else max(float(width) / float(height), float(height) / float(width))
            if area_ratio is not None and area_ratio > self.config.max_box_area_ratio:
                reject_reasons.append("box_too_large")
                continue
            if aspect_ratio is not None and aspect_ratio > self.config.max_aspect_ratio:
                reject_reasons.append("aspect_ratio")
                continue
            if not self._point_in_roi(candidate.image_xy, roi_corners):
                reject_reasons.append("outside_roi")
                continue
            filtered.append(
                BallCandidate(
                    image_x=float(candidate.image_x),
                    image_y=float(candidate.image_y),
                    confidence=float(candidate.confidence),
                    width=width,
                    height=height,
                    area_ratio=area_ratio,
                    aspect_ratio=aspect_ratio,
                    diagnostics=dict(candidate.diagnostics),
                )
            )
        return filtered, reject_reasons

    # ── candidate selection ───────────────────────────────────────

    def _select_candidate(self, candidates: Sequence[BallCandidate]) -> tuple[BallCandidate | None, str, str]:
        if not candidates:
            return None, "missing_no_candidates", ""

        if self.track_state == BallTrackState.SEARCHING:
            return max(candidates, key=lambda c: c.confidence), "accepted", ""

        predicted = self._predict_next_position()

        if self.track_state in (BallTrackState.LOCKED, BallTrackState.LOST):
            gate = self._compute_dynamic_gate()
            if self.track_state == BallTrackState.LOST:
                gate *= self.config.lost_gate_multiplier
            sorted_candidates = sorted(candidates, key=lambda c: self._score_candidate(c, predicted), reverse=True)
            for c in sorted_candidates:
                if self._distance(c.image_xy, predicted) <= gate:
                    return c, "accepted", ""
            return None, "missing_predicted_only", "no_candidate_passed_physics_gate"

        return max(candidates, key=lambda c: self._score_candidate(c, predicted)), "accepted", ""

    def _score_candidate(self, candidate: BallCandidate, predicted: Point2D) -> float:
        distance = self._distance(candidate.image_xy, predicted)
        size_penalty = float(candidate.area_ratio or 0.0) * 4000.0

        if self.track_state == BallTrackState.LOCKED:
            conf_w = self.config.locked_confidence_weight
            dist_w = self.config.locked_distance_weight
        elif self.track_state == BallTrackState.LOST:
            conf_w = self.config.lost_confidence_weight
            dist_w = self.config.lost_distance_weight
        elif self.track_state == BallTrackState.TENTATIVE:
            conf_w = self.config.tentative_confidence_weight
            dist_w = self.config.tentative_distance_weight
        else:
            conf_w = self.config.searching_confidence_weight
            dist_w = self.config.searching_distance_weight

        return candidate.confidence * conf_w - distance * dist_w - size_penalty

    # ── prediction ────────────────────────────────────────────────

    def _predict_next_position(self) -> Point2D:
        if len(self.trajectory) < 2:
            if self.trajectory:
                return self.trajectory[-1]
            return self.last_valid_position or (0.0, 0.0)

        if len(self.trajectory) < self.config.min_prediction_points:
            return self.trajectory[-1]

        n = min(len(self.trajectory), self.config.min_prediction_points)
        recent = list(self.trajectory)[-n:]

        dx_total = 0.0
        dy_total = 0.0
        count = 0
        for i in range(1, len(recent)):
            dx_total += recent[i][0] - recent[i - 1][0]
            dy_total += recent[i][1] - recent[i - 1][1]
            count += 1

        if count == 0:
            return self.trajectory[-1]

        avg_dx = dx_total / count
        avg_dy = dy_total / count
        multiplier = min(max(1, self.missing_frames + 1), 3)

        last_x, last_y = self.trajectory[-1]
        return (last_x + avg_dx * multiplier, last_y + avg_dy * multiplier)

    # ── dynamic physics gate ──────────────────────────────────────

    def _compute_dynamic_gate(self) -> float:
        recent_speed = self._compute_recent_speed()
        speed_component = (
            self.config.speed_factor * recent_speed
            if len(self.trajectory) >= self.config.min_prediction_points
            else 0.0
        )
        missing_component = self.config.missing_factor * min(self.missing_frames, 5)
        raw_gate = (
            self.config.base_gate_pixels
            + speed_component
            + missing_component
            + self._perspective_adjustment()
        )
        return max(self.config.min_gate_pixels, min(self.config.max_gate_pixels, raw_gate))

    def _compute_recent_speed(self) -> float:
        if len(self.trajectory) < 2:
            return 0.0
        n = min(len(self.trajectory), self.config.min_prediction_points)
        recent = list(self.trajectory)[-n:]
        total_dist = 0.0
        for i in range(1, len(recent)):
            total_dist += self._distance(recent[i], recent[i - 1])
        return total_dist / (len(recent) - 1)

    def _perspective_adjustment(self) -> float:
        if self._cached_frame_height <= 0:
            return 0.0
        predicted = self._predict_next_position()
        y_fraction = predicted[1] / self._cached_frame_height
        if y_fraction > 0.6:
            return 20.0
        if y_fraction < 0.4:
            return -10.0
        return 0.0

    # ── state machine ─────────────────────────────────────────────

    def _update_track_state(self, found: bool) -> None:
        if found:
            self._lock_hits += 1
            if self.track_state == BallTrackState.SEARCHING and self._lock_hits >= self.config.tentative_min_hits:
                self.track_state = BallTrackState.TENTATIVE
            elif self.track_state == BallTrackState.TENTATIVE and self._lock_hits >= self.config.lock_min_hits:
                self.track_state = BallTrackState.LOCKED
            elif self.track_state == BallTrackState.LOST:
                self.track_state = BallTrackState.LOCKED
        else:
            self._lock_hits = 0
            if self.track_state in (BallTrackState.LOCKED, BallTrackState.TENTATIVE):
                self.track_state = BallTrackState.LOST
            elif self.track_state == BallTrackState.LOST:
                if self.missing_frames > self.config.max_missing_frames_locked:
                    self.track_state = BallTrackState.SEARCHING

    # ── missing detection ─────────────────────────────────────────

    def _record_missing_detection(self) -> None:
        self.missing_frames += 1
        max_allowed = (
            self.config.max_missing_frames_locked
            if self.track_state in (BallTrackState.LOCKED, BallTrackState.LOST)
            else self.config.max_missing_frames
        )
        if self.missing_frames > max_allowed:
            self.last_valid_position = None

    def _append_valid_point(self, point: Point2D) -> None:
        self.trajectory.append(point)
        self.last_valid_position = point
        self.missing_frames = 0

    # ── continuity / gate checks ──────────────────────────────────

    def _continuity_reject_reason(self, point: Point2D) -> str | None:
        if not self.trajectory:
            return None
        max_missing = (
            self.config.max_missing_frames_locked
            if self.track_state in (BallTrackState.LOCKED, BallTrackState.LOST, BallTrackState.TENTATIVE)
            else self.config.max_missing_frames
        )
        strict_gate = self.missing_frames <= max_missing
        if not strict_gate:
            return None
        dynamic_gate = self._compute_dynamic_gate()
        jump_distance = self._distance(point, self.trajectory[-1])
        if jump_distance > dynamic_gate:
            return "jump_distance"
        predicted_distance = self._distance(point, self._predict_next_position())
        if predicted_distance > dynamic_gate:
            return "prediction_gate"
        return None

    def _court_bounds_reject_reason(self, court_xy: Point2D | None) -> str | None:
        if court_xy is None:
            return None
        margin = max(0.0, float(self.config.court_bounds_margin_ft))
        x, y = court_xy
        court = self.court_adapter.court
        if -margin <= x <= court.width_ft + margin and -margin <= y <= court.length_ft + margin:
            return None
        return "projected_outside_court"

    # ── stationary suppression ────────────────────────────────────

    def _record_selected_candidate(self, point: Point2D) -> None:
        self.selected_history.append(point)

    def _stationary_reject_reason(self) -> str | None:
        if len(self.selected_history) < max(1, self.config.stationary_window_frames):
            return None
        points = list(self.selected_history)
        center_x = sum(p[0] for p in points) / len(points)
        center_y = sum(p[1] for p in points) / len(points)
        max_radius = max(self._distance(p, (center_x, center_y)) for p in points)
        if max_radius <= self.config.stationary_radius_pixels:
            return "stationary_candidate"
        return None

    def _player_motion_static_reject_reason(self, point: Point2D, player_motion_pixels: float | None) -> str | None:
        if player_motion_pixels is None:
            return None
        if player_motion_pixels < self.config.player_motion_min_pixels:
            return None
        if len(self.selected_history) < max(1, self.config.stationary_window_frames):
            return None
        points = list(self.selected_history)
        center_x = sum(p[0] for p in points) / len(points)
        center_y = sum(p[1] for p in points) / len(points)
        max_radius = max(self._distance(p, (center_x, center_y)) for p in points)
        if max_radius <= self.config.stationary_radius_pixels:
            return "static_false_positive"
        return None

    # ── stationary blacklist ──────────────────────────────────────

    def _update_stationary_blacklist(self, candidates: Sequence[BallCandidate]) -> None:
        grid = self.config.stationary_blacklist_grid_px
        threshold = self.config.stationary_blacklist_frames
        for candidate in candidates:
            grid_x = int(candidate.image_x / grid) * grid
            grid_y = int(candidate.image_y / grid) * grid
            key = (grid_x, grid_y)
            self._stationary_blacklist[key] = self._stationary_blacklist.get(key, 0) + 1
            if self._stationary_blacklist[key] >= threshold:
                self._stationary_blacklist_positions.add(key)

    def _is_blacklisted(self, point: Point2D) -> bool:
        grid = self.config.stationary_blacklist_grid_px
        grid_x = int(point[0] / grid) * grid
        grid_y = int(point[1] / grid) * grid
        return (grid_x, grid_y) in self._stationary_blacklist_positions

    def _stationary_blacklist_reject_reason(self, point: Point2D) -> str | None:
        if not self._is_blacklisted(point):
            return None
        if not self.trajectory:
            return "stationary_blacklisted"
        jump_distance = self._distance(point, self.trajectory[-1])
        if jump_distance < self.config.stationary_radius_pixels * 2:
            return "stationary_blacklisted"
        max_missing = (
            self.config.max_missing_frames_locked
            if self.track_state in (BallTrackState.LOCKED, BallTrackState.LOST, BallTrackState.TENTATIVE)
            else self.config.max_missing_frames
        )
        strict_gate = self.missing_frames <= max_missing
        if not strict_gate:
            return "stationary_blacklisted"
        dynamic_gate = self._compute_dynamic_gate()
        if jump_distance > dynamic_gate:
            return "stationary_blacklisted"
        predicted_distance = self._distance(point, self._predict_next_position())
        if predicted_distance > dynamic_gate:
            return "stationary_blacklisted"
        return None

    # ── ROI ───────────────────────────────────────────────────────

    def _point_in_roi(
        self,
        point: Point2D,
        roi_corners: tuple[tuple[int, int], tuple[int, int]] | None,
    ) -> bool:
        if roi_corners is None:
            return True
        x1, y1 = roi_corners[0]
        x2, y2 = roi_corners[1]
        padding = int(max(abs(x2 - x1), abs(y2 - y1)) * self.config.roi_padding_ratio)
        left, right = sorted((x1, x2))
        top, bottom = sorted((y1, y2))
        return (left - padding) <= point[0] <= (right + padding) and (top - padding) <= point[1] <= (bottom + padding)

    # ── debug metadata ────────────────────────────────────────────

    def _build_candidate_debugs(
        self,
        candidates: Sequence[BallCandidate],
        selected: BallCandidate | None,
        predicted: Point2D | None,
    ) -> list[BallCandidateDebug]:
        result: list[BallCandidateDebug] = []
        predicted = predicted or (0.0, 0.0)
        dynamic_gate = self._compute_dynamic_gate()
        for i, c in enumerate(candidates):
            cid = f"candidate_{i + 1}"
            dist_to_pred = self._distance(c.image_xy, predicted) if predicted else None
            jump_dist = self._distance(c.image_xy, self.trajectory[-1]) if self.trajectory else None
            passed_gate = dist_to_pred is not None and dist_to_pred <= dynamic_gate
            rejection_reason: str | None = None
            if not passed_gate and self.track_state in (BallTrackState.LOCKED, BallTrackState.LOST):
                rejection_reason = "physics_gate_rejected"
            elif selected is not None and c is selected:
                rejection_reason = None
            elif not passed_gate:
                rejection_reason = "too_far_from_prediction"
            result.append(
                BallCandidateDebug(
                    candidate_id=cid,
                    bbox=(c.image_x, c.image_y, float(c.width or 0), float(c.height or 0)),
                    raw_confidence=c.confidence,
                    final_score=self._score_candidate(c, predicted),
                    distance_to_prediction=dist_to_pred,
                    jump_distance=jump_dist,
                    passed_physics_gate=passed_gate,
                    rejection_reason=rejection_reason,
                )
            )
        if selected is not None and result:
            for r in result:
                if str((r.bbox[0], r.bbox[1])) == str(selected.image_xy):
                    pass
        return result

    def _build_debug_dict(
        self,
        predicted_pos: Point2D | None,
        candidate_debugs: list[BallCandidateDebug],
        accepted_candidate_id: str | None,
        overall_decision: str,
    ) -> dict[str, Any]:
        debug = BallFrameDebug(
            track_state=self.track_state.value,
            predicted_position=predicted_pos,
            candidates=candidate_debugs,
            accepted_candidate_id=accepted_candidate_id,
            overall_decision=overall_decision,
        )
        return {"ball_frame_debug": debug}

    # ── helpers ───────────────────────────────────────────────────

    @staticmethod
    def _distance(point_a: Point2D, point_b: Point2D) -> float:
        return float(hypot(point_a[0] - point_b[0], point_a[1] - point_b[1]))

    def _build_sample(
        self,
        *,
        frame_index: int,
        timestamp_sec: float,
        image_xy: Point2D | None,
        court_xy: Point2D | None,
        confidence: float | None,
        visible: bool,
        accepted: bool,
        candidate_count: int,
        reject_reason: str | None,
        in_bounds: bool | None,
        predicted_pos: Point2D | None,
        overall_decision: str,
        candidate_debugs: list[BallCandidateDebug],
        accepted_candidate_id: str | None,
    ) -> BallFrameSample:
        diagnostic_kwargs: dict[str, Any] = {"court_projection": ""}
        debug = self._build_debug_dict(predicted_pos, candidate_debugs, accepted_candidate_id, overall_decision)
        diagnostic_kwargs.update(debug)
        return BallFrameSample(
            frame_index=frame_index,
            timestamp_sec=timestamp_sec,
            image_xy=image_xy,
            court_xy=court_xy,
            confidence=confidence,
            visible=visible,
            accepted=accepted,
            candidate_count=candidate_count,
            reject_reason=reject_reason,
            in_bounds=in_bounds,
            track_state=self.track_state.value,
            predicted_position=predicted_pos,
            overall_decision=overall_decision,
            diagnostics=diagnostic_kwargs,
        )
