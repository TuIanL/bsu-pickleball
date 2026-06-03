"""主要球员选择器 —— 基于目标球场归属、tracklet 质量和四人组关系选择展示球员。"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from math import hypot, isfinite

from app.schemas.tracking import PlayerFramePosition, PlayerSelectionDiagnostic, PlayerTrackletFeature, Track
from app.vision.courtvision_calibration_engine.court_geometry import StandardPickleballCourt, standard_court


@dataclass(frozen=True)
class PrimaryPlayerSelection:
    track_id: int
    score: float
    confidence: float
    rolling_confidence: float
    appearances: int
    target_court_score: float = 0.0
    tracklet_quality_score: float = 0.0
    group_consistency_score: float = 0.0


@dataclass
class _TrackQuality:
    appearances: int = 0
    confidence_total: float = 0.0

    @property
    def rolling_confidence(self) -> float:
        return self.confidence_total / self.appearances if self.appearances else 0.0


@dataclass(frozen=True)
class _Observation:
    frame_index: int
    timestamp: float
    track_id: int
    bbox: list[float]
    image_footpoint: list[float]
    court_position: list[float] | None
    confidence: float
    area_ratio: float
    valid: bool


@dataclass
class PrimaryPlayerSelectorConfig:
    min_confidence: float = 0.65
    max_subjects: int = 4
    min_box_area_ratio: float = 0.0005
    max_box_area_ratio: float = 0.85
    court_margin_ft: float | None = 12.0
    window_frames: int = 90
    target_court_threshold: float = 0.45
    quality_threshold: float = 0.28
    group_weight: float = 0.18
    attention_enabled: bool = False
    attention_model_path: str | None = None
    attention_confidence_threshold: float = 0.65


@dataclass(frozen=True)
class AttentionSelectionResult:
    selected_track_ids: set[int]
    target_probabilities: dict[int, float]
    non_target_probabilities: dict[int, float]
    confidence: float


class AttentionPlayerSelectorAdapter:
    """Optional adapter boundary for future self-attention inference."""

    def __init__(self, model_path: str | None = None, confidence_threshold: float = 0.65) -> None:
        self.model_path = model_path
        self.confidence_threshold = confidence_threshold
        self.last_fallback_reason: str | None = None

    def select(self, features: list[PlayerTrackletFeature], max_subjects: int) -> AttentionSelectionResult | None:
        if not self.model_path:
            self.last_fallback_reason = "attention model path is not configured"
            return None
        try:
            import torch  # type: ignore  # noqa: F401
        except Exception as exc:  # noqa: BLE001 - optional dependency should not block rule path.
            self.last_fallback_reason = f"attention dependency unavailable: {exc}"
            return None

        self.last_fallback_reason = "attention inference is not implemented for untrained local weights"
        return None


class PrimaryPlayerSelector:
    """Select presentation subjects from tracked people using court-aware tracklet history."""

    def __init__(
        self,
        min_confidence: float = 0.65,
        max_subjects: int = 4,
        min_box_area_ratio: float = 0.0005,
        max_box_area_ratio: float = 0.85,
        court_margin_ft: float | None = 12.0,
        court: StandardPickleballCourt | None = None,
        window_frames: int = 90,
        target_court_threshold: float = 0.45,
        quality_threshold: float = 0.28,
        attention_enabled: bool = False,
        attention_model_path: str | None = None,
        attention_confidence_threshold: float = 0.65,
        attention_adapter: AttentionPlayerSelectorAdapter | None = None,
    ) -> None:
        self.config = PrimaryPlayerSelectorConfig(
            min_confidence=min(max(min_confidence, 0.0), 1.0),
            max_subjects=max(1, int(max_subjects)),
            min_box_area_ratio=max(0.0, min_box_area_ratio),
            max_box_area_ratio=max(max(0.0, min_box_area_ratio), max_box_area_ratio),
            court_margin_ft=court_margin_ft,
            window_frames=max(1, int(window_frames)),
            target_court_threshold=min(max(target_court_threshold, 0.0), 1.0),
            quality_threshold=min(max(quality_threshold, 0.0), 1.0),
            attention_enabled=attention_enabled,
            attention_model_path=attention_model_path,
            attention_confidence_threshold=min(max(attention_confidence_threshold, 0.0), 1.0),
        )
        self.court = court or standard_court()
        self._qualities: dict[int, _TrackQuality] = {}
        self._history: dict[int, deque[_Observation]] = {}
        self.last_diagnostics: list[PlayerSelectionDiagnostic] = []
        self.last_training_samples: list[PlayerTrackletFeature] = []
        self.last_selection_mode: str = "rule"
        self.last_fallback_reason: str | None = None
        self.attention_adapter = attention_adapter or AttentionPlayerSelectorAdapter(
            model_path=attention_model_path,
            confidence_threshold=self.config.attention_confidence_threshold,
        )

    @property
    def min_confidence(self) -> float:
        return self.config.min_confidence

    @property
    def max_subjects(self) -> int:
        return self.config.max_subjects

    @property
    def min_box_area_ratio(self) -> float:
        return self.config.min_box_area_ratio

    @property
    def max_box_area_ratio(self) -> float:
        return self.config.max_box_area_ratio

    @property
    def court_margin_ft(self) -> float | None:
        return self.config.court_margin_ft

    def select(
        self,
        tracks: list[Track],
        positions: list[PlayerFramePosition],
        frame_width: int,
        frame_height: int,
    ) -> list[PrimaryPlayerSelection]:
        active_tracks = [track for track in tracks if not track.lost]
        positions_by_track_id = {position.track_id: position for position in positions}
        for track in active_tracks:
            quality = self._qualities.setdefault(track.track_id, _TrackQuality())
            quality.appearances += 1
            quality.confidence_total += track.confidence
            self._record_observation(track, positions_by_track_id.get(track.track_id), frame_width, frame_height)

        features = [
            feature
            for track in active_tracks
            if (feature := self._tracklet_feature(track.track_id, track, frame_width, frame_height)) is not None
        ]
        group_scores = self._group_consistency_scores(features)
        attention_result = self._attention_select(features)
        selected_by_attention = attention_result.selected_track_ids if attention_result is not None else set()

        candidates: list[PrimaryPlayerSelection] = []
        diagnostics: list[PlayerSelectionDiagnostic] = []
        for feature in features:
            selection = self._score_feature(feature, group_scores.get(feature.track_id, 0.0), attention_result)
            selected_by_rule = selection is not None
            selected = feature.track_id in selected_by_attention if attention_result is not None else selected_by_rule
            if selection is not None:
                candidates.append(selection)
            diagnostics.append(
                self._diagnostic_for_feature(
                    feature,
                    selected=selected,
                    group_score=group_scores.get(feature.track_id, 0.0),
                    final_score=selection.score if selection else self._raw_score(feature, group_scores.get(feature.track_id, 0.0)),
                    attention_result=attention_result,
                )
            )
        candidates.sort(key=lambda selection: (selection.score, selection.rolling_confidence, selection.confidence), reverse=True)
        selected_candidates = candidates[: self.max_subjects]
        selected_ids = {selection.track_id for selection in selected_candidates}
        if attention_result is not None:
            selected_ids = selected_by_attention
            selected_candidates = [selection for selection in candidates if selection.track_id in selected_ids][: self.max_subjects]
        self.last_diagnostics = [
            diagnostic.model_copy(update={"selected": diagnostic.track_id in {selection.track_id for selection in selected_candidates}})
            for diagnostic in diagnostics
        ]
        self.last_training_samples = features
        return selected_candidates

    def _score_feature(
        self,
        feature: PlayerTrackletFeature,
        group_score: float,
        attention_result: AttentionSelectionResult | None,
    ) -> PrimaryPlayerSelection | None:
        if feature.latest_confidence < self.min_confidence:
            return None
        if not (self.min_box_area_ratio <= feature.mean_bbox_area_ratio <= self.max_box_area_ratio):
            return None
        if feature.valid_positions > 0 and feature.target_court_occupancy < self.config.target_court_threshold and group_score < 0.75:
            return None
        if self._tracklet_quality_score(feature) < self.config.quality_threshold:
            return None
        if attention_result is not None and feature.track_id not in attention_result.selected_track_ids:
            return None

        quality = self._qualities.get(feature.track_id, _TrackQuality())
        rolling_confidence = quality.rolling_confidence
        target_score = self._target_court_score(feature)
        quality_score = self._tracklet_quality_score(feature)
        score = self._raw_score(feature, group_score)
        if attention_result is not None:
            score = attention_result.target_probabilities.get(feature.track_id, score)
        return PrimaryPlayerSelection(
            track_id=feature.track_id,
            score=score,
            confidence=feature.latest_confidence,
            rolling_confidence=rolling_confidence,
            appearances=feature.appearances,
            target_court_score=target_score,
            tracklet_quality_score=quality_score,
            group_consistency_score=group_score,
        )

    def _raw_score(self, feature: PlayerTrackletFeature, group_score: float) -> float:
        target_score = self._target_court_score(feature)
        quality_score = self._tracklet_quality_score(feature)
        confidence_score = feature.latest_confidence * 0.45 + feature.mean_confidence * 0.55
        weighted = (
            target_score * 0.42
            + quality_score * 0.28
            + confidence_score * 0.12
            + group_score * self.config.group_weight
        )
        return min(1.0, max(0.0, weighted))

    def _target_court_score(self, feature: PlayerTrackletFeature) -> float:
        if feature.valid_positions == 0:
            return 0.5
        distance_penalty = min(1.0, feature.mean_target_court_distance / max(1.0, float(self.court_margin_ft or 1.0)))
        occupancy_score = feature.target_court_occupancy
        return min(1.0, max(0.0, occupancy_score * 0.72 + (1.0 - distance_penalty) * 0.28))

    def _tracklet_quality_score(self, feature: PlayerTrackletFeature) -> float:
        persistence = min(1.0, feature.appearances / 12.0)
        valid_ratio = feature.valid_positions / max(1, feature.appearances)
        bbox_score = 1.0 if self.min_box_area_ratio <= feature.mean_bbox_area_ratio <= self.max_box_area_ratio else 0.0
        return min(
            1.0,
            max(
                0.0,
                feature.mean_confidence * 0.42
                + persistence * 0.22
                + feature.continuity * 0.18
                + valid_ratio * 0.12
                + bbox_score * 0.06,
            ),
        )

    def _group_consistency_scores(self, features: list[PlayerTrackletFeature]) -> dict[int, float]:
        if not features:
            return {}
        valid = [feature for feature in features if feature.mean_court_position is not None]
        if not valid:
            return {feature.track_id: 0.5 for feature in features}
        near_far_balance: dict[int, float] = {}
        half_length = self.court.length_ft / 2.0
        for feature in valid:
            same_side_count = sum(
                1
                for other in valid
                if other.track_id != feature.track_id
                and other.mean_court_position is not None
                and (other.mean_court_position[1] < half_length) == (feature.mean_court_position[1] < half_length)
            )
            opposite_side_count = sum(
                1
                for other in valid
                if other.track_id != feature.track_id
                and other.mean_court_position is not None
                and (other.mean_court_position[1] < half_length) != (feature.mean_court_position[1] < half_length)
            )
            side_score = min(1.0, same_side_count / 1.0) * 0.45 + min(1.0, opposite_side_count / 2.0) * 0.55
            center_x = feature.mean_court_position[0]
            width_score = 1.0 - min(1.0, abs(center_x - self.court.width_ft / 2.0) / max(1.0, self.court.width_ft))
            near_far_balance[feature.track_id] = min(1.0, max(0.0, side_score * 0.7 + width_score * 0.3))
        return {feature.track_id: near_far_balance.get(feature.track_id, 0.35) for feature in features}

    def _attention_select(self, features: list[PlayerTrackletFeature]) -> AttentionSelectionResult | None:
        self.last_selection_mode = "rule"
        self.last_fallback_reason = None
        if not self.config.attention_enabled:
            return None
        result = self.attention_adapter.select(features, self.max_subjects)
        if result is None:
            self.last_selection_mode = "fallback"
            self.last_fallback_reason = self.attention_adapter.last_fallback_reason or "attention selector returned no result"
            return None
        if result.confidence < self.config.attention_confidence_threshold:
            self.last_selection_mode = "fallback"
            self.last_fallback_reason = "attention confidence below threshold"
            return None
        self.last_selection_mode = "attention"
        return result

    def _diagnostic_for_feature(
        self,
        feature: PlayerTrackletFeature,
        *,
        selected: bool,
        group_score: float,
        final_score: float,
        attention_result: AttentionSelectionResult | None,
    ) -> PlayerSelectionDiagnostic:
        target_score = self._target_court_score(feature)
        quality_score = self._tracklet_quality_score(feature)
        reason = "selected target-court player" if selected else self._rejection_reason(feature, target_score, quality_score, group_score)
        label = (
            "target_player"
            if selected
            else ("neighbor_court_player" if feature.valid_positions > 0 and target_score < self.config.target_court_threshold else "uncertain")
        )
        return PlayerSelectionDiagnostic(
            track_id=feature.track_id,
            selected=selected,
            selection_mode=self.last_selection_mode,  # type: ignore[arg-type]
            fallback_reason=self.last_fallback_reason,
            target_court_score=target_score,
            tracklet_quality_score=quality_score,
            group_consistency_score=group_score,
            attention_target_probability=attention_result.target_probabilities.get(feature.track_id) if attention_result else None,
            attention_non_target_probability=attention_result.non_target_probabilities.get(feature.track_id) if attention_result else None,
            final_score=final_score,
            candidate_label=label,
            reason=reason,
            frame_start=feature.frame_start,
            frame_end=feature.frame_end,
            components={
                "target_court_occupancy": feature.target_court_occupancy,
                "mean_target_court_distance": feature.mean_target_court_distance,
                "mean_confidence": feature.mean_confidence,
                "appearances": feature.appearances,
                "continuity": feature.continuity,
            },
        )

    def _rejection_reason(self, feature: PlayerTrackletFeature, target_score: float, quality_score: float, group_score: float) -> str:
        if feature.latest_confidence < self.min_confidence:
            return "confidence below threshold"
        if feature.valid_positions > 0 and target_score < self.config.target_court_threshold:
            return "low target-court membership"
        if quality_score < self.config.quality_threshold:
            return "low tracklet quality"
        if group_score < 0.35:
            return "weak doubles group consistency"
        return "ranked outside participant limit"

    def _record_observation(
        self,
        track: Track,
        position: PlayerFramePosition | None,
        frame_width: int,
        frame_height: int,
    ) -> None:
        area_ratio = self._bbox_area_ratio(track.bbox, frame_width, frame_height)
        court_position = position.court_position if position and position.court_position is not None else None
        image_footpoint = position.image_footpoint if position is not None else self._bbox_bottom_center(track.bbox)
        frame_index = position.frame_index if position is not None else 0
        timestamp = position.timestamp if position is not None else 0.0
        observation = _Observation(
            frame_index=frame_index,
            timestamp=timestamp,
            track_id=track.track_id,
            bbox=[float(value) for value in track.bbox],
            image_footpoint=[float(value) for value in image_footpoint],
            court_position=[float(value) for value in court_position] if court_position is not None else None,
            confidence=track.confidence,
            area_ratio=area_ratio,
            valid=bool(position.valid and position.court_position is not None) if position is not None else False,
        )
        history = self._history.setdefault(track.track_id, deque(maxlen=self.config.window_frames))
        history.append(observation)

    def _has_reasonable_box(self, track: Track, frame_width: int, frame_height: int) -> bool:
        area_ratio = self._bbox_area_ratio(track.bbox, frame_width, frame_height)
        return self.min_box_area_ratio <= area_ratio <= self.max_box_area_ratio

    def _bbox_area_ratio(self, bbox: list[float], frame_width: int, frame_height: int) -> float:
        source_area = max(1.0, float(frame_width) * float(frame_height))
        x1, y1, x2, y2 = [float(value) for value in bbox]
        if not all(isfinite(value) for value in (x1, y1, x2, y2)):
            return 0.0
        width = max(0.0, x2 - x1)
        height = max(0.0, y2 - y1)
        if width <= 0.0 or height <= 0.0:
            return 0.0
        return (width * height) / source_area

    def _passes_scene_sanity(self, position: PlayerFramePosition | None) -> bool:
        if self.court_margin_ft is None or position is None or position.court_position is None:
            return True
        x, y = position.court_position
        margin = self.court_margin_ft
        return (
            -margin <= x <= self.court.width_ft + margin
            and -margin <= y <= self.court.length_ft + margin
        )

    def _tracklet_feature(
        self,
        track_id: int,
        fallback_track: Track,
        frame_width: int,
        frame_height: int,
    ) -> PlayerTrackletFeature | None:
        history = list(self._history.get(track_id, []))
        if not history:
            return None
        latest = history[-1]
        court_points = [observation.court_position for observation in history if observation.court_position is not None]
        valid_positions = len(court_points)
        distances = [self._distance_from_target_court(point) for point in court_points]
        in_target_count = sum(1 for distance in distances if distance <= float(self.court_margin_ft or 0.0))
        target_occupancy = in_target_count / valid_positions if valid_positions else 0.0
        mean_position = (
            [
                sum(point[0] for point in court_points) / valid_positions,
                sum(point[1] for point in court_points) / valid_positions,
            ]
            if valid_positions
            else None
        )
        speeds = []
        for previous, current in zip(history, history[1:]):
            if previous.court_position is None or current.court_position is None:
                continue
            elapsed = current.timestamp - previous.timestamp
            if elapsed <= 0:
                continue
            speeds.append(_distance(previous.court_position, current.court_position) / elapsed)
        frame_span = max(1, history[-1].frame_index - history[0].frame_index + 1)
        continuity = min(1.0, len(history) / frame_span)
        bbox = latest.bbox or [float(value) for value in fallback_track.bbox]
        image_footpoint = latest.image_footpoint or self._bbox_bottom_center(bbox)
        return PlayerTrackletFeature(
            track_id=track_id,
            frame_start=history[0].frame_index,
            frame_end=history[-1].frame_index,
            first_timestamp_seconds=history[0].timestamp,
            last_timestamp_seconds=history[-1].timestamp,
            appearances=len(history),
            valid_positions=valid_positions,
            mean_confidence=sum(observation.confidence for observation in history) / len(history),
            latest_confidence=latest.confidence,
            mean_bbox_area_ratio=sum(observation.area_ratio for observation in history) / len(history),
            court_position=latest.court_position,
            mean_court_position=mean_position,
            target_court_occupancy=target_occupancy,
            mean_target_court_distance=sum(distances) / len(distances) if distances else float(self.court_margin_ft or 0.0) + 1.0,
            max_target_court_distance=max(distances) if distances else float(self.court_margin_ft or 0.0) + 1.0,
            mean_speed=sum(speeds) / len(speeds) if speeds else 0.0,
            continuity=continuity,
            bbox=bbox,
            image_footpoint=image_footpoint,
        )

    def _distance_from_target_court(self, point: list[float]) -> float:
        x, y = point
        dx = max(0.0, -x, x - self.court.width_ft)
        dy = max(0.0, -y, y - self.court.length_ft)
        return hypot(dx, dy)

    @staticmethod
    def _bbox_bottom_center(bbox: list[float]) -> list[float]:
        x1, _y1, x2, y2 = [float(value) for value in bbox]
        return [(x1 + x2) / 2.0, y2]


def _distance(a: list[float], b: list[float]) -> float:
    return hypot(a[0] - b[0], a[1] - b[1])
