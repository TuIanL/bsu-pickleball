"""One-to-one motion-aware tracker with a compatible legacy IoU rollback."""

from __future__ import annotations

# dataclass：定义内部轨迹状态；Detection / Track 为检测与轨迹的数据模型。
from dataclasses import dataclass, field
from functools import lru_cache
from hashlib import sha256
from math import hypot, log
import json
import os
from typing import Literal

from app.schemas.tracking import Detection, Track
from app.vision.player_tracking_engine.player_appearance import (
    AppearanceTemplateGallery,
    PlayerAppearanceDescriptor,
    discriminative_margin,
)


@dataclass
class _TrackState:
    # 内部维护的某条轨迹状态：track_id、当前 bbox、置信度、连续未匹配帧计数（lost_count）。
    track_id: int
    bbox: list[float]
    confidence: float
    lost_count: int = 0
    previous_bbox: list[float] | None = None
    bbox_velocity: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])
    footpoint_velocity: list[float] = field(default_factory=lambda: [0.0, 0.0])
    area_velocity: float = 0.0
    aspect_velocity: float = 0.0
    last_tick: int = 0
    uncertainty: float = 0.0
    appearance_gallery: AppearanceTemplateGallery = field(default_factory=AppearanceTemplateGallery)


@dataclass(frozen=True)
class TrackingUpdate:
    """Tracks plus exact input-detection to track assignments."""

    tracks: list[Track]
    detection_to_track: dict[int, int]


class MultiObjectTracker:
    """Motion/scale tracker preserving the historical detection-in/tracks-out API."""

    def __init__(
        self,
        iou_threshold: float = 0.3,
        max_lost: int = 15,
        *,
        algorithm: Literal["motion", "legacy"] | None = None,
        appearance_enabled: bool = False,
        appearance_weight: float = 0.18,
        min_appearance_margin: float = 0.08,
        shadow_legacy: bool = False,
    ) -> None:
        # iou_threshold：匹配所需的最小 IOU；max_lost：超过此未匹配帧数则删除轨迹。
        self.iou_threshold = iou_threshold
        self.max_lost = max_lost
        self.algorithm = algorithm or os.getenv("PICKLEBALL_TRACKER_ALGORITHM", "motion")
        if self.algorithm not in {"motion", "legacy"}:
            raise ValueError(f"unsupported tracker algorithm: {self.algorithm}")
        self.appearance_enabled = appearance_enabled
        self.appearance_weight = max(0.0, float(appearance_weight))
        self.min_appearance_margin = max(0.0, float(min_appearance_margin))
        self._next_track_id = 1  # 自增分配新 track_id
        self._tracks: dict[int, _TrackState] = {}
        self._tick = 0
        self._legacy_shadow = (
            MultiObjectTracker(iou_threshold, max_lost, algorithm="legacy")
            if shadow_legacy and self.algorithm == "motion"
            else None
        )
        self.last_shadow_comparison: dict[str, object] | None = None
        self._shadow_ticks = 0
        self._shadow_changed_assignments = 0

    @property
    def config_signature(self) -> str:
        payload = {
            "algorithm": self.algorithm,
            "iou_threshold": self.iou_threshold,
            "max_lost": self.max_lost,
            "appearance_enabled": self.appearance_enabled,
            "appearance_weight": self.appearance_weight,
            "min_appearance_margin": self.min_appearance_margin,
        }
        return sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def update(
        self,
        detections: list[Detection],
        appearance_descriptors: dict[int, PlayerAppearanceDescriptor] | None = None,
    ) -> list[Track]:
        return self.update_with_assignments(detections, appearance_descriptors).tracks

    def update_with_assignments(
        self,
        detections: list[Detection],
        appearance_descriptors: dict[int, PlayerAppearanceDescriptor] | None = None,
    ) -> TrackingUpdate:
        self._tick += 1
        if self.algorithm == "legacy":
            return self._legacy_update(detections)
        if self._legacy_shadow is not None:
            legacy = self._legacy_shadow.update_with_assignments(detections)
        else:
            legacy = None
        result = self._motion_update(detections, appearance_descriptors or {})
        if legacy is not None:
            changed_assignments = sum(
                legacy.detection_to_track.get(index) != result.detection_to_track.get(index)
                for index in range(len(detections))
            )
            self._shadow_ticks += 1
            self._shadow_changed_assignments += changed_assignments
            self.last_shadow_comparison = {
                "tick": self._tick,
                "legacy_detection_to_track": legacy.detection_to_track,
                "motion_detection_to_track": result.detection_to_track,
                "changed_assignments": changed_assignments,
            }
        return result

    def shadow_summary(self) -> dict[str, object]:
        legacy = self._legacy_shadow
        return {
            "enabled": legacy is not None,
            "ticks": self._shadow_ticks,
            "changed_assignments": self._shadow_changed_assignments,
            "motion_track_ids_created": self._next_track_id - 1,
            "legacy_track_ids_created": (legacy._next_track_id - 1) if legacy is not None else 0,
            "last_tick": self.last_shadow_comparison,
        }

    def _motion_update(
        self,
        detections: list[Detection],
        descriptors: dict[int, PlayerAppearanceDescriptor],
    ) -> TrackingUpdate:
        matched_tracks: set[int] = set()
        matched_detections: set[int] = set()
        active: list[Track] = []
        detection_to_track: dict[int, int] = {}
        app_margin = discriminative_margin([descriptors.get(index) for index in range(len(detections))])
        use_appearance = self.appearance_enabled and app_margin >= self.min_appearance_margin
        edges: dict[int, list[tuple[int, float]]] = {}
        track_ids = sorted(self._tracks)
        for track_index, track_id in enumerate(track_ids):
            state = self._tracks[track_id]
            predicted = _predict_bbox(state)
            viable: list[tuple[int, float]] = []
            for detection_index, detection in enumerate(detections):
                features = _association_features(state, predicted, detection)
                if not _passes_hard_gate(features, self.iou_threshold, state.uncertainty):
                    continue
                cost = _association_cost(features, incumbent=state.lost_count == 0)
                if use_appearance:
                    app_distance = state.appearance_gallery.distance_to(descriptors.get(detection_index))
                    if app_distance is not None:
                        quality = descriptors[detection_index].quality.score
                        cost += self.appearance_weight * quality * app_distance
                viable.append((detection_index, cost))
            edges[track_index] = sorted(viable, key=lambda item: (item[1], item[0]))
        assignments = _maximum_cardinality_min_cost_assignment(track_ids, edges)
        for track_id, detection_index in assignments:
            detection = detections[detection_index]
            state = self._tracks[track_id]
            self._apply_detection(state, detection, descriptors.get(detection_index))
            matched_tracks.add(track_id)
            matched_detections.add(detection_index)
            detection_to_track[detection_index] = track_id
            active.append(_state_to_track(state, lost=False))

        # 3) 未匹配到的检测视为“新目标”，分配新 track_id 并新建轨迹。
        for detection_index, detection in enumerate(detections):
            if detection_index in matched_detections:
                continue
            track_id = self._next_track_id
            self._next_track_id += 1
            state = _TrackState(
                track_id=track_id,
                bbox=list(detection.bbox),
                confidence=detection.confidence,
                last_tick=self._tick,
            )
            state.appearance_gallery.update(descriptors.get(detection_index), confirmed_observed=True)
            self._tracks[track_id] = state
            matched_tracks.add(track_id)
            detection_to_track[detection_index] = track_id
            active.append(_state_to_track(state, lost=False))

        # 4) 本轮未匹配到的轨迹 lost_count+1；超过 max_lost 则彻底删除。
        for track_id in list(self._tracks):
            if track_id in matched_tracks:
                continue
            state = self._tracks[track_id]
            state.lost_count += 1
            state.uncertainty = min(3.0, state.uncertainty + 0.18)
            if state.lost_count > self.max_lost:
                del self._tracks[track_id]

        # 按 track_id 升序返回当前活跃轨迹。
        active.sort(key=lambda track: track.track_id)
        return TrackingUpdate(tracks=active, detection_to_track=detection_to_track)

    def _apply_detection(
        self,
        state: _TrackState,
        detection: Detection,
        descriptor: PlayerAppearanceDescriptor | None,
    ) -> None:
        old_bbox = list(state.bbox)
        old_foot = _footpoint(old_bbox)
        new_bbox = list(detection.bbox)
        new_foot = _footpoint(new_bbox)
        raw_bbox_velocity = [new - old for new, old in zip(new_bbox, old_bbox)]
        raw_foot_velocity = [new - old for new, old in zip(new_foot, old_foot)]
        state.bbox_velocity = [0.20 * old + 0.80 * new for old, new in zip(state.bbox_velocity, raw_bbox_velocity)]
        state.footpoint_velocity = [
            0.20 * old + 0.80 * new for old, new in zip(state.footpoint_velocity, raw_foot_velocity)
        ]
        old_area, new_area = _bbox_area(old_bbox), _bbox_area(new_bbox)
        old_aspect, new_aspect = _bbox_aspect(old_bbox), _bbox_aspect(new_bbox)
        state.area_velocity = 0.7 * state.area_velocity + 0.3 * log(max(new_area, 1.0) / max(old_area, 1.0))
        state.aspect_velocity = 0.7 * state.aspect_velocity + 0.3 * log(
            max(new_aspect, 1e-6) / max(old_aspect, 1e-6)
        )
        state.previous_bbox = old_bbox
        state.bbox = new_bbox
        state.confidence = detection.confidence
        state.lost_count = 0
        state.last_tick = self._tick
        state.uncertainty = max(0.0, state.uncertainty * 0.45 - 0.05)
        state.appearance_gallery.update(descriptor, confirmed_observed=True)

    def _legacy_update(self, detections: list[Detection]) -> TrackingUpdate:
        matched_tracks: set[int] = set()
        matched_detections: set[int] = set()
        active: list[Track] = []
        detection_to_track: dict[int, int] = {}
        candidates: list[tuple[float, int, int]] = []
        for detection_index, detection in enumerate(detections):
            for track_id, state in self._tracks.items():
                candidates.append((_iou(detection.bbox, state.bbox), track_id, detection_index))
        candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
        for score, track_id, detection_index in candidates:
            if score < self.iou_threshold:
                break
            if track_id in matched_tracks or detection_index in matched_detections:
                continue
            detection = detections[detection_index]
            state = self._tracks[track_id]
            state.previous_bbox = list(state.bbox)
            state.bbox = list(detection.bbox)
            state.confidence = detection.confidence
            state.lost_count = 0
            state.last_tick = self._tick
            matched_tracks.add(track_id)
            matched_detections.add(detection_index)
            detection_to_track[detection_index] = track_id
            active.append(_state_to_track(state, lost=False))
        for detection_index, detection in enumerate(detections):
            if detection_index in matched_detections:
                continue
            track_id = self._next_track_id
            self._next_track_id += 1
            state = _TrackState(
                track_id=track_id,
                bbox=list(detection.bbox),
                confidence=detection.confidence,
                last_tick=self._tick,
            )
            self._tracks[track_id] = state
            matched_tracks.add(track_id)
            detection_to_track[detection_index] = track_id
            active.append(_state_to_track(state, lost=False))
        for track_id in list(self._tracks):
            if track_id in matched_tracks:
                continue
            state = self._tracks[track_id]
            state.lost_count += 1
            if state.lost_count > self.max_lost:
                del self._tracks[track_id]
        active.sort(key=lambda track: track.track_id)
        return TrackingUpdate(tracks=active, detection_to_track=detection_to_track)


class EmptyTracker:
    # 空实现，用于测试或无需真实跟踪的占位场景（永远返回空列表）。
    def update(self, detections: list[Detection]) -> list[Track]:
        return []

    def update_with_assignments(self, detections: list[Detection]) -> TrackingUpdate:
        return TrackingUpdate(tracks=[], detection_to_track={})


@dataclass(frozen=True)
class AssociationFeatures:
    predicted_iou: float
    normalized_footpoint_distance: float
    log_area_change: float
    log_aspect_change: float
    detection_confidence: float
    projection_reliability: float


def _predict_bbox(state: _TrackState) -> list[float]:
    horizon = min(state.lost_count + 1, 4)
    return [value + velocity * horizon for value, velocity in zip(state.bbox, state.bbox_velocity)]


def _association_features(
    state: _TrackState,
    predicted_bbox: list[float],
    detection: Detection,
) -> AssociationFeatures:
    predicted_foot = _footpoint(predicted_bbox)
    detection_foot = _footpoint(detection.bbox)
    scale = max(8.0, _bbox_area(predicted_bbox) ** 0.5)
    foot_distance = hypot(
        predicted_foot[0] - detection_foot[0],
        predicted_foot[1] - detection_foot[1],
    ) / scale
    area_change = abs(log(max(_bbox_area(detection.bbox), 1.0) / max(_bbox_area(predicted_bbox), 1.0)))
    aspect_change = abs(
        log(max(_bbox_aspect(detection.bbox), 1e-6) / max(_bbox_aspect(predicted_bbox), 1e-6))
    )
    reliability = detection.projection_reliability
    return AssociationFeatures(
        predicted_iou=_iou(predicted_bbox, detection.bbox),
        normalized_footpoint_distance=foot_distance,
        log_area_change=area_change,
        log_aspect_change=aspect_change,
        detection_confidence=detection.confidence,
        projection_reliability=0.5 if reliability is None else reliability,
    )


def _passes_hard_gate(
    features: AssociationFeatures,
    iou_threshold: float,
    uncertainty: float,
) -> bool:
    if features.log_area_change > log(4.0) + min(0.5, uncertainty * 0.1):
        return False
    if features.log_aspect_change > log(2.5):
        return False
    spatial_gate = 1.15 + min(1.0, uncertainty * 0.35)
    return features.predicted_iou >= max(0.03, iou_threshold * 0.30) or (
        features.normalized_footpoint_distance <= spatial_gate
    )


def _association_cost(features: AssociationFeatures, *, incumbent: bool) -> float:
    cost = (
        0.42 * (1.0 - features.predicted_iou)
        + 0.28 * min(1.0, features.normalized_footpoint_distance)
        + 0.12 * min(1.0, features.log_area_change / log(4.0))
        + 0.06 * min(1.0, features.log_aspect_change / log(2.5))
        + 0.08 * (1.0 - features.detection_confidence)
        + 0.04 * (1.0 - features.projection_reliability)
    )
    if incumbent:
        cost -= 0.04
    return max(0.0, cost)


def _maximum_cardinality_min_cost_assignment(
    track_ids: list[int],
    edges: dict[int, list[tuple[int, float]]],
) -> list[tuple[int, int]]:
    """Exact deterministic assignment; detections are few in a court ROI."""

    @lru_cache(maxsize=None)
    def solve(track_index: int, used_mask: int) -> tuple[int, float, tuple[tuple[int, int], ...]]:
        if track_index >= len(track_ids):
            return 0, 0.0, ()
        best_count, best_cost, best_pairs = solve(track_index + 1, used_mask)
        track_id = track_ids[track_index]
        for detection_index, edge_cost in edges.get(track_index, []):
            bit = 1 << detection_index
            if used_mask & bit:
                continue
            count, cost, pairs = solve(track_index + 1, used_mask | bit)
            candidate = (count + 1, cost + edge_cost, ((track_id, detection_index),) + pairs)
            best = (best_count, best_cost, best_pairs)
            if candidate[0] > best[0] or (
                candidate[0] == best[0]
                and (candidate[1] < best[1] - 1e-12 or (
                    abs(candidate[1] - best[1]) <= 1e-12 and candidate[2] < best[2]
                ))
            ):
                best_count, best_cost, best_pairs = candidate
        return best_count, best_cost, best_pairs

    return list(solve(0, 0)[2])


def _footpoint(bbox: list[float]) -> tuple[float, float]:
    return ((bbox[0] + bbox[2]) / 2.0, bbox[3])


def _bbox_area(bbox: list[float]) -> float:
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


def _bbox_aspect(bbox: list[float]) -> float:
    width = max(1e-6, bbox[2] - bbox[0])
    height = max(1e-6, bbox[3] - bbox[1])
    return width / height


def _state_to_track(state: _TrackState, lost: bool) -> Track:
    # 把内部 _TrackState 转成对外 Track 数据模型。
    return Track(track_id=state.track_id, bbox=state.bbox, confidence=state.confidence, lost=lost)


def _iou(a: list[float], b: list[float]) -> float:
    # 计算两个 [x1,y1,x2,y2] 框的交并比（IOU）。
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b

    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    intersection = inter_w * inter_h

    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - intersection
    if union <= 0:
        return 0.0
    return intersection / union


class DuplicateTrackSuppressor:
    """抑制同一目标被跟踪器分身出的重复重叠 track（仅作用于球员路径输出）。

    当一个 track 对（如 P2 的 track 41 与其分身 track 50）bbox 重叠度超过阈值并持续
    达到连续帧数时，视为同一目标被重复跟踪，从输出中剔除较新的分身。只过滤输出、
    不改内部轨迹状态：若两目标后续分离（IoU 下降），被抑制 track 可自然重新出现。
    """

    def __init__(self, iou_threshold: float = 0.6, sustain_frames: int = 3) -> None:
        # iou_threshold：判定"同一目标"所需的最小 bbox 重叠度；
        # sustain_frames：重叠需持续的连续帧数（含 1 帧缺席容错），避免误杀真·近距离双人。
        self.iou_threshold = iou_threshold
        self.sustain_frames = sustain_frames
        self._pair_count: dict[frozenset[int], int] = {}

    def filter(self, tracks: list[Track]) -> list[Track]:
        # 两两比较当前帧活跃 track；IoU ≥ 阈值则累加该对持续重叠帧数，否则 -1（容错缺席/短暂分离）。
        # 持续 ≥ sustain_frames 时抑制对中较新的 track（track_id 较大者为分身）；
        # 仅当新 track 置信度显著更高（> 旧 + 0.15）时才反过来保留新 track。
        counts: dict[frozenset[int], int] = {}
        seen_pairs: set[frozenset[int]] = set()
        suppressed: set[int] = set()
        for i in range(len(tracks)):
            for j in range(i + 1, len(tracks)):
                a = tracks[i]
                b = tracks[j]
                iou = _iou(a.bbox, b.bbox)
                pair = frozenset({a.track_id, b.track_id})
                prev = self._pair_count.get(pair, 0)
                cur = prev + 1 if iou >= self.iou_threshold else max(0, prev - 1)
                counts[pair] = cur
                seen_pairs.add(pair)
                if cur >= self.sustain_frames:
                    older, newer = (a, b) if a.track_id < b.track_id else (b, a)
                    if newer.confidence > older.confidence + 0.15:
                        suppressed.add(older.track_id)
                    else:
                        suppressed.add(newer.track_id)
        # 本帧缺席的 track 对计数衰减 -1，而非清零，避免单帧缺口打断持续重叠累计
        for pair, prev in self._pair_count.items():
            if pair not in seen_pairs:
                counts[pair] = max(0, prev - 1)
        self._pair_count = counts
        return [track for track in tracks if track.track_id not in suppressed]


# 别名：SimpleDetectionTracker 等价于 MultiObjectTracker（保持历史/兼容命名）。
SimpleDetectionTracker = MultiObjectTracker
