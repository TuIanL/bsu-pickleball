"""比赛状态实验使用的时间对齐和结构化时序特征。

本模块只消费视觉缓存：RGB 帧索引、球员骨架、球候选和场地线几何。
它不读取 rally/non_play 预测，也不把“未检测到球”解释为场上没有球。
所有速度均默认是归一化图像坐标每秒；没有经过验证的单应性时，不伪造米制速度。
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

FEATURE_SCHEMA_VERSION = "match_state_aligned_feature.v1"
DEFAULT_MAX_ALIGNMENT_GAP_MS = 60.0
DEFAULT_BALL_MAX_SPEED_NORM_PER_S = 3.0
DEFAULT_BALL_STATIONARY_SPEED_NORM_PER_S = 0.08


def _array(value: Any, shape: tuple[int, ...] | None = None) -> np.ndarray:
    result = np.asarray(value, dtype=np.float32)
    if shape is not None and result.shape != shape:
        return np.zeros(shape, dtype=np.float32)
    return result


def _round_list(value: Any, digits: int = 6) -> Any:
    return np.asarray(value, dtype=np.float32).round(digits).tolist()


def _norm(value: np.ndarray) -> float:
    return float(np.linalg.norm(value))


def _safe_dt(timestamp_ms: float, previous_ms: float | None) -> float:
    if previous_ms is None:
        return 1.0 / 12.0
    return max((timestamp_ms - previous_ms) / 1000.0, 1e-3)


@dataclass
class _PlayerState:
    timestamp_ms: float
    footpoint: np.ndarray
    velocity: np.ndarray
    keypoints: np.ndarray | None = None
    visible: np.ndarray | None = None


@dataclass
class PlayerFeatureState:
    previous_timestamp_ms: float | None = None
    tracks: dict[int, _PlayerState] = field(default_factory=dict)
    previous_formation_spread: float | None = None


def _player_footpoint(person: dict[str, Any]) -> np.ndarray:
    bbox = _array(person.get("bbox_xyxy_norm"), (4,))
    if np.any(bbox):
        return np.array([(bbox[0] + bbox[2]) * 0.5, bbox[3]], dtype=np.float32)
    keypoints = _array(person.get("keypoints_xy_norm"))
    if keypoints.ndim == 2 and len(keypoints):
        return keypoints[-1]
    return np.zeros(2, dtype=np.float32)


def _player_keypoints(person: dict[str, Any]) -> tuple[np.ndarray | None, np.ndarray | None]:
    points = _array(person.get("keypoints_xy_norm"))
    if points.ndim != 2 or points.shape[1] != 2:
        return None, None
    visibility = np.asarray(person.get("keypoint_visible_mask", [1] * len(points)), dtype=bool)
    if visibility.shape != (len(points),):
        visibility = np.ones(len(points), dtype=bool)
    return points, visibility


def _formation_features(
    positions: np.ndarray,
    velocities: np.ndarray,
    previous_spread: float | None,
    dt: float,
) -> tuple[dict[str, Any], float | None]:
    if len(positions) == 0:
        return {
            "player_count": 0,
            "centroid_xy_norm": None,
            "spread_mean_pair_distance": None,
            "spread_max_pair_distance": None,
            "range_xy_norm": None,
            "centroid_speed_norm_per_s": None,
            "formation_change_speed": None,
        }, previous_spread
    centroid = positions.mean(axis=0)
    pairwise = []
    for first in range(len(positions)):
        for second in range(first + 1, len(positions)):
            pairwise.append(_norm(positions[first] - positions[second]))
    spread = float(np.mean(pairwise)) if pairwise else 0.0
    centroid_velocity = velocities.mean(axis=0) if len(velocities) else np.zeros(2, dtype=np.float32)
    change_speed = None if previous_spread is None else abs(spread - previous_spread) / max(dt, 1e-3)
    return {
        "player_count": int(len(positions)),
        "centroid_xy_norm": _round_list(centroid),
        "spread_mean_pair_distance": round(spread, 6),
        "spread_max_pair_distance": round(max(pairwise, default=0.0), 6),
        "range_xy_norm": _round_list(positions.max(axis=0) - positions.min(axis=0)),
        "centroid_speed_norm_per_s": round(_norm(centroid_velocity), 6),
        "formation_change_speed": None if change_speed is None else round(float(change_speed), 6),
    }, spread


def derive_player_features(record: dict[str, Any], state: PlayerFeatureState) -> dict[str, Any]:
    """从单个结构化帧生成带速度、加速度和身体活动量的球员/队形特征。"""

    timestamp_ms = float(record.get("take_timestamp_ms", 0.0))
    dt = _safe_dt(timestamp_ms, state.previous_timestamp_ms)
    features: list[dict[str, Any]] = []
    positions: list[np.ndarray] = []
    velocities: list[np.ndarray] = []
    for person in record.get("people", []):
        if not isinstance(person, dict):
            continue
        track_id = int(person.get("track_id", -1))
        footpoint = _player_footpoint(person)
        keypoints, visible = _player_keypoints(person)
        previous = state.tracks.get(track_id)
        velocity = np.zeros(2, dtype=np.float32)
        acceleration = np.zeros(2, dtype=np.float32)
        activity = 0.0
        activity_coverage = 0.0
        if previous is not None:
            velocity = (footpoint - previous.footpoint) / dt
            acceleration = (velocity - previous.velocity) / dt
            if (
                keypoints is not None
                and visible is not None
                and previous.keypoints is not None
                and previous.visible is not None
            ):
                usable = (
                    visible
                    & previous.visible
                    & (np.isfinite(keypoints).all(axis=1))
                    & np.isfinite(previous.keypoints).all(axis=1)
                )
                if np.any(usable):
                    activity = float(np.linalg.norm(keypoints[usable] - previous.keypoints[usable], axis=1).mean() / dt)
                    activity_coverage = float(np.mean(usable))
        visibility_ratio = float(np.mean(visible)) if visible is not None and len(visible) else 0.0
        positions.append(footpoint)
        velocities.append(velocity)
        features.append(
            {
                "track_id": track_id,
                "position_xy_norm": _round_list(footpoint),
                "velocity_xy_norm_per_s": _round_list(velocity),
                "speed_norm_per_s": round(_norm(velocity), 6),
                "acceleration_xy_norm_per_s2": _round_list(acceleration),
                "acceleration_norm_per_s2": round(_norm(acceleration), 6),
                "body_activity_intensity": round(activity, 6),
                "body_activity_coverage": round(activity_coverage, 6),
                "det_confidence": round(float(person.get("det_confidence", 0.0)), 6),
                "visibility_ratio": round(visibility_ratio, 6),
                "keypoints_xy_norm": None if keypoints is None else _round_list(keypoints),
                "keypoint_visible_mask": None if visible is None else visible.astype(int).tolist(),
                "missing": False,
            }
        )
        state.tracks[track_id] = _PlayerState(timestamp_ms, footpoint, velocity, keypoints, visible)
    positions_array = (
        np.asarray(positions, dtype=np.float32).reshape((-1, 2)) if positions else np.zeros((0, 2), dtype=np.float32)
    )
    velocities_array = (
        np.asarray(velocities, dtype=np.float32).reshape((-1, 2)) if velocities else np.zeros((0, 2), dtype=np.float32)
    )
    formation, state.previous_formation_spread = _formation_features(
        positions_array,
        velocities_array,
        state.previous_formation_spread,
        dt,
    )
    state.previous_timestamp_ms = timestamp_ms
    quality = record.get("quality", {})
    return {
        "players": features,
        "formation": formation,
        "pose_usable": bool(quality.get("pose_usable", False)),
        "four_players_observed": bool(quality.get("four_players_observed", False)),
        "pose_visible_ratio": round(float(quality.get("pose_visible_ratio", 0.0)), 6),
        "structured_loss_mask": int(quality.get("structured_loss_mask", 0)),
    }


@dataclass
class _BallTrack:
    track_id: int
    center: np.ndarray
    timestamp_ms: float
    velocity: np.ndarray = field(default_factory=lambda: np.zeros(2, dtype=np.float32))
    previous_velocity: np.ndarray = field(default_factory=lambda: np.zeros(2, dtype=np.float32))
    previous_timestamp_ms: float | None = None
    confidence: float = 0.0
    age: int = 1
    missed: int = 0


@dataclass
class BallFeatureState:
    next_track_id: int = 1
    tracks: dict[int, _BallTrack] = field(default_factory=dict)
    primary_track_id: int | None = None


def _ball_center(candidate: dict[str, Any]) -> np.ndarray:
    center = _array(candidate.get("center_xy_norm"), (2,))
    if np.any(center):
        return center
    box = _array(candidate.get("bbox_xyxy_norm"), (4,))
    return np.array([(box[0] + box[2]) * 0.5, (box[1] + box[3]) * 0.5], dtype=np.float32)


def derive_ball_features(
    record: dict[str, Any],
    state: BallFeatureState,
    *,
    max_speed_norm_per_s: float = DEFAULT_BALL_MAX_SPEED_NORM_PER_S,
    stationary_speed_norm_per_s: float = DEFAULT_BALL_STATIONARY_SPEED_NORM_PER_S,
) -> dict[str, Any]:
    """对每帧球候选做连续关联，并输出主轨迹的速度/方向/停滞特征。"""

    timestamp_ms = float(record.get("take_timestamp_ms", 0.0))
    candidates = [candidate for candidate in record.get("ball_candidates", []) if isinstance(candidate, dict)]
    observations = [(_ball_center(candidate), float(candidate.get("confidence", 0.0))) for candidate in candidates]
    active = [track for track in state.tracks.values() if track.missed <= 6]
    assignments: dict[int, int] = {}
    available_tracks = set(track.track_id for track in active)
    available_candidates = set(range(len(observations)))
    pairs: list[tuple[float, int, int]] = []
    for track in active:
        dt = _safe_dt(timestamp_ms, track.timestamp_ms)
        max_distance = max(0.08, max_speed_norm_per_s * dt)
        for index, (center, confidence) in enumerate(observations):
            distance = _norm(center - track.center)
            if distance <= max_distance:
                pairs.append((distance - confidence * 0.01, track.track_id, index))
    for _, track_id, candidate_index in sorted(pairs):
        if track_id not in available_tracks or candidate_index not in available_candidates:
            continue
        assignments[candidate_index] = track_id
        available_tracks.remove(track_id)
        available_candidates.remove(candidate_index)
    for candidate_index in sorted(available_candidates):
        track_id = state.next_track_id
        state.next_track_id += 1
        assignments[candidate_index] = track_id
        center, confidence = observations[candidate_index]
        state.tracks[track_id] = _BallTrack(track_id, center, timestamp_ms, confidence=confidence)
    for track in state.tracks.values():
        if track.track_id in assignments.values():
            continue
        track.missed += 1
    for candidate_index, track_id in assignments.items():
        center, confidence = observations[candidate_index]
        track = state.tracks[track_id]
        track.previous_velocity = track.velocity.copy()
        track.previous_timestamp_ms = track.timestamp_ms
        dt = _safe_dt(timestamp_ms, track.timestamp_ms)
        track.velocity = (center - track.center) / dt
        track.center = center
        track.timestamp_ms = timestamp_ms
        track.confidence = confidence
        track.age += 1
        track.missed = 0
    stale = [track_id for track_id, track in state.tracks.items() if track.missed > 6]
    for track_id in stale:
        state.tracks.pop(track_id, None)

    primary: _BallTrack | None = None
    if state.primary_track_id is not None and state.primary_track_id in state.tracks:
        candidate_primary = state.tracks[state.primary_track_id]
        if candidate_primary.missed == 0:
            primary = candidate_primary
    if primary is None and assignments:
        primary = max(
            (state.tracks[track_id] for track_id in assignments.values()),
            key=lambda track: (track.age, track.confidence),
        )
        state.primary_track_id = primary.track_id
    association_ids = [assignments[index] for index in range(len(observations))]
    if primary is None:
        return {
            "candidate_count": len(candidates),
            "candidate_track_ids": association_ids,
            "observed": False,
            "missing_semantics": "unknown_not_no_ball",
            "track_id": state.primary_track_id,
            "center_xy_norm": None,
            "velocity_xy_norm_per_s": None,
            "speed_norm_per_s": None,
            "direction_rad": None,
            "acceleration_norm_per_s2": None,
            "stationary": None,
            "visibility": 0.0,
        }
    acceleration_dt = _safe_dt(timestamp_ms, primary.previous_timestamp_ms)
    acceleration = (primary.velocity - primary.previous_velocity) / max(acceleration_dt, 1e-3)
    speed = _norm(primary.velocity)
    direction = math.atan2(float(primary.velocity[1]), float(primary.velocity[0])) if speed > 1e-6 else None
    return {
        "candidate_count": len(candidates),
        "candidate_track_ids": association_ids,
        "observed": True,
        "missing_semantics": None,
        "track_id": primary.track_id,
        "center_xy_norm": _round_list(primary.center),
        "velocity_xy_norm_per_s": _round_list(primary.velocity),
        "speed_norm_per_s": round(speed, 6),
        "direction_rad": None if direction is None else round(direction, 6),
        "acceleration_norm_per_s2": round(_norm(acceleration), 6),
        "stationary": bool(speed <= stationary_speed_norm_per_s),
        "visibility": round(float(primary.confidence), 6),
    }


def nearest_by_timestamp(
    records: list[dict[str, Any]], timestamp_ms: float, max_gap_ms: float
) -> tuple[dict[str, Any] | None, float | None]:
    """返回距离目标时间最近的记录；超过门限时显式返回缺失。"""

    return TimestampIndex(records).nearest(timestamp_ms, max_gap_ms)


class TimestampIndex:
    """可重复查询的时间索引，避免全量缓存构建时重复扫描时间戳。"""

    def __init__(self, records: list[dict[str, Any]], timestamp_key: str = "take_timestamp_ms") -> None:
        self.records = records
        self.timestamps = np.asarray(
            [float(item.get(timestamp_key, item.get("timestamp_ms", 0.0))) for item in records]
        )

    def nearest(self, timestamp_ms: float, max_gap_ms: float) -> tuple[dict[str, Any] | None, float | None]:
        if not self.records:
            return None, None
        index = int(np.searchsorted(self.timestamps, timestamp_ms))
        candidates = [max(0, min(len(self.records) - 1, index + offset)) for offset in (-1, 0)]
        best = min(candidates, key=lambda item: abs(float(self.timestamps[item]) - timestamp_ms))
        delta = float(self.timestamps[best] - timestamp_ms)
        if abs(delta) > max_gap_ms:
            return None, delta
        return self.records[best], delta


def rgb_frame_reference(entry: dict[str, Any], timestamp_ms: float, fps: float) -> dict[str, Any]:
    """将 take 时间映射到 RGB cache 帧号，并显式记录量化误差。"""

    duration_ms = max(0.0, float(entry.get("duration_ms", 0.0)))
    clamped = min(max(0.0, timestamp_ms), duration_ms)
    frame_count = int(entry.get("frame_count", 0))
    index = max(1, min(frame_count, int(round(clamped / 1000.0 * fps)) + 1)) if frame_count else None
    frame_timestamp = None if index is None else (index - 1) * 1000.0 / fps
    return {
        "available": index is not None,
        "frame_index": index,
        "timestamp_ms": None if frame_timestamp is None else round(frame_timestamp, 3),
        "alignment_delta_ms": None if frame_timestamp is None else round(frame_timestamp - timestamp_ms, 3),
        "frame_path": None if index is None else str(PathLikeFrame(entry.get("frame_dir"), index)),
    }


class PathLikeFrame(str):
    """延迟格式化 RGB 文件名，避免在非远程机器访问帧文件。"""

    def __new__(cls, frame_dir: Any, index: int) -> PathLikeFrame:
        return super().__new__(cls, f"{frame_dir}/{index:06d}.jpg")


def build_aligned_view(
    *,
    timestamp_ms: float,
    rgb_entry: dict[str, Any] | None,
    structured_records: list[dict[str, Any]],
    court_records: list[dict[str, Any]],
    player_state: PlayerFeatureState,
    ball_state: BallFeatureState,
    rgb_fps: float,
    max_alignment_gap_ms: float,
    feature_timestamp_ms: float | None = None,
    structured_index: TimestampIndex | None = None,
    court_index: TimestampIndex | None = None,
) -> dict[str, Any]:
    structured_index = structured_index or TimestampIndex(structured_records)
    court_index = court_index or TimestampIndex(court_records, timestamp_key="timestamp_ms")
    structured, structured_delta = structured_index.nearest(timestamp_ms, max_alignment_gap_ms)
    court, court_delta = court_index.nearest(timestamp_ms, max(30_000.0, max_alignment_gap_ms * 2.0))
    rgb = None if rgb_entry is None else rgb_frame_reference(rgb_entry, timestamp_ms, rgb_fps)
    if structured is None:
        pose = {
            "players": [],
            "formation": {"player_count": 0},
            "pose_usable": False,
            "four_players_observed": False,
            "pose_visible_ratio": 0.0,
            "structured_loss_mask": 0,
        }
        ball = {
            "candidate_count": 0,
            "candidate_track_ids": [],
            "observed": False,
            "missing_semantics": "unknown_not_no_ball",
            "track_id": ball_state.primary_track_id,
            "center_xy_norm": None,
            "velocity_xy_norm_per_s": None,
            "speed_norm_per_s": None,
            "direction_rad": None,
            "acceleration_norm_per_s2": None,
            "stationary": None,
            "visibility": 0.0,
        }
    else:
        feature_record = (
            structured if feature_timestamp_ms is None else {**structured, "take_timestamp_ms": feature_timestamp_ms}
        )
        pose = derive_player_features(feature_record, player_state)
        ball = derive_ball_features(feature_record, ball_state)
    quality = structured.get("quality", {}) if structured else {}
    return {
        "rgb": rgb,
        "structured": {
            "available": structured is not None,
            "timestamp_ms": None if structured is None else structured.get("take_timestamp_ms"),
            "source_frame_index": None if structured is None else structured.get("decoded_frame_index"),
            "alignment_delta_ms": None if structured_delta is None else round(structured_delta, 3),
            "schema_version": None if structured is None else structured.get("schema_version"),
        },
        "court_line": {
            "available": court is not None,
            "timestamp_ms": None if court is None else court.get("timestamp_ms"),
            "alignment_delta_ms": None if court_delta is None else round(court_delta, 3),
            "geometry": court,
            "projection_available": bool(quality.get("court_projection_available", False)) if structured else False,
        },
        "features": {"pose": pose, "ball": ball},
        "quality": {
            "rgb_available": bool(rgb and rgb.get("available")),
            "structured_available": structured is not None,
            "court_line_available": court is not None,
            "pose_usable": bool(pose.get("pose_usable", False)),
            "ball_observed": bool(ball.get("observed", False)),
            "ball_missing_semantics": ball.get("missing_semantics"),
            "view_missing": not bool(rgb and rgb.get("available")) or structured is None,
        },
    }


def canonical_grid(max_timestamp_ms: float, fps: float) -> Iterable[int]:
    step_ms = 1000.0 / fps
    count = int(math.floor(max_timestamp_ms / step_ms + 1e-6)) + 1
    return (int(round(index * step_ms)) for index in range(max(0, count)))
