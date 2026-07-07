"""Rule-based bounce detection from cleaned ball trajectories."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.vision.courtvision_calibration_engine.court_geometry import PickleballCourtGeometry, standard_court
from app.vision.pickleball_game_analysis.schemas import BounceEvent, TrajectoryPoint


@dataclass(frozen=True)
class BounceDetectorConfig:
    fps: float = 30.0
    window_size: int = 20
    center_offset: int = 10
    min_event_gap_sec: float = 0.45
    min_score: float = 0.34
    max_center_velocity: float = 2500.0
    max_speed_ratio: float = 12.0
    court_margin_ft: float = 3.0


class BounceDetector:
    detection_method = "trajectory_lag20"

    def __init__(
        self,
        config: BounceDetectorConfig | None = None,
        court: PickleballCourtGeometry | None = None,
    ) -> None:
        self.config = config or BounceDetectorConfig()
        self.fps = max(float(self.config.fps), 1.0)
        self.min_event_gap_frames = max(1, int(float(self.config.min_event_gap_sec) * self.fps))
        self.court = court or standard_court()

    def detect(self, points: list[TrajectoryPoint]) -> list[BounceEvent]:
        coords = np.array([point.image_xy if point.image_xy is not None else (np.nan, np.nan) for point in points], dtype=np.float32)
        velocity = self._velocity(coords)
        court_coords = np.array([point.court_xy if point.court_xy is not None else (np.nan, np.nan) for point in points], dtype=np.float32)
        raw_events: list[BounceEvent] = []

        for end_index in range(self.config.window_size - 1, len(points)):
            start_index = end_index - self.config.window_size + 1
            center_index = end_index - self.config.center_offset
            if center_index <= 0 or center_index >= len(points) - 1:
                continue
            window = coords[start_index:end_index + 1]
            window_v = velocity[start_index:end_index + 1]
            if np.isnan(window).any() or np.isnan(window_v).any():
                continue
            court_window = court_coords[start_index:end_index + 1]
            score, diagnostics = self._score_window(
                window,
                window_v,
                self.config.window_size - self.config.center_offset - 1,
                court_window=None if np.isnan(court_window).any() else court_window,
            )
            if score < self.config.min_score:
                continue
            point = points[center_index]
            if point.image_xy is None or not self._valid_bounce_court_position(point.court_xy):
                continue
            raw_events.append(
                BounceEvent(
                    event_id=f"bounce-{len(raw_events) + 1}",
                    frame_index=int(point.frame_index),
                    timestamp_sec=round(float(point.timestamp_sec), 6),
                    image_xy=(round(float(point.image_xy[0]), 2), round(float(point.image_xy[1]), 2)),
                    court_xy=(
                        (round(float(point.court_xy[0]), 4), round(float(point.court_xy[1]), 4))
                        if point.court_xy is not None
                        else None
                    ),
                    confidence=round(float(score), 3),
                    detection_method=self.detection_method,
                    diagnostics=diagnostics,
                )
            )
        return self._dedupe_events(raw_events)

    def _score_window(
        self,
        window: np.ndarray,
        velocity: np.ndarray,
        center: int,
        court_window: np.ndarray | None = None,
    ) -> tuple[float, dict[str, object]]:
        centered = window - np.nanmean(window, axis=0)
        scale = max(float(np.nanstd(centered)), 1.0)
        normalized = centered / scale
        smooth = self._smooth(window)
        center_point = smooth[center]
        before = smooth[max(0, center - 5):center]
        after = smooth[center + 1:min(len(smooth), center + 6)]
        if len(before) < 3 or len(after) < 3:
            return 0.0, {}

        before_center = np.mean(before, axis=0)
        after_center = np.mean(after, axis=0)
        v_in = center_point - before_center
        v_out = after_center - center_point
        turn_degrees = self._angle_between(v_in, v_out)
        deviation = self._point_line_distance(center_point, before_center, after_center)

        v_center = float(velocity[center])
        local_v = velocity[max(0, center - 4):min(len(velocity), center + 5)]
        median_v = float(np.nanmedian(local_v))
        peak_v = float(np.nanmax(local_v))
        speed_ratio = peak_v / max(median_v, 1.0)
        if v_center > self.config.max_center_velocity or speed_ratio > self.config.max_speed_ratio:
            return 0.0, {
                "reject_reason": "unstable_velocity",
                "center_velocity": round(v_center, 3),
                "speed_ratio": round(speed_ratio, 3),
                "window_size": int(self.config.window_size),
            }

        y = normalized[:, 1]
        y_slope_in = self._line_slope(np.arange(center + 1), y[:center + 1])
        y_slope_out = self._line_slope(np.arange(len(y) - center), y[center:])
        y_reversal = y_slope_in > 0.05 and y_slope_out < -0.05
        local_y = window[max(0, center - 5):min(len(window), center + 6), 1]
        local_y_peak = window[center, 1] >= np.max(local_y) - 4.0
        local_y_valley = window[center, 1] <= np.min(local_y) + 4.0
        y_extreme = bool(local_y_peak or local_y_valley)

        court_turn = 0.0
        court_deviation = 0.0
        if court_window is not None:
            court_smooth = self._smooth(court_window)
            court_center = court_smooth[center]
            court_before = np.mean(court_smooth[max(0, center - 5):center], axis=0)
            court_after = np.mean(court_smooth[center + 1:min(len(court_smooth), center + 6)], axis=0)
            court_turn = self._angle_between(court_center - court_before, court_after - court_center)
            court_deviation = self._point_line_distance(court_center, court_before, court_after)

        if not (y_reversal or y_extreme):
            return 0.0, {
                "reject_reason": "no_local_y_extreme",
                "turn_degrees": round(float(turn_degrees), 3),
                "deviation_px": round(float(deviation), 3),
                "window_size": int(self.config.window_size),
            }

        angle_score = min(1.0, turn_degrees / 95.0)
        deviation_score = min(1.0, deviation / 18.0)
        speed_score = min(1.0, max(0.0, speed_ratio - 1.0) / 2.0)
        reversal_score = 1.0 if y_reversal else 0.0
        extreme_score = 1.0 if y_extreme else 0.0
        court_score = max(min(1.0, court_turn / 75.0), min(1.0, court_deviation / 1.8))
        score = (
            0.28 * angle_score
            + 0.24 * deviation_score
            + 0.12 * speed_score
            + 0.16 * reversal_score
            + 0.10 * extreme_score
            + 0.10 * court_score
        )
        diagnostics = {
            "turn_degrees": round(float(turn_degrees), 3),
            "deviation_px": round(float(deviation), 3),
            "center_velocity": round(float(v_center), 3),
            "speed_ratio": round(float(speed_ratio), 3),
            "y_slope_in": round(float(y_slope_in), 4),
            "y_slope_out": round(float(y_slope_out), 4),
            "local_y_peak": bool(local_y_peak),
            "local_y_valley": bool(local_y_valley),
            "court_turn_degrees": round(float(court_turn), 3),
            "court_deviation_ft": round(float(court_deviation), 3),
            "window_size": int(self.config.window_size),
        }
        return float(score), diagnostics

    def _valid_bounce_court_position(self, court_xy: tuple[float, float] | None) -> bool:
        if court_xy is None:
            return True
        x, y = court_xy
        if not np.isfinite(x) or not np.isfinite(y):
            return False
        margin = float(self.config.court_margin_ft)
        return -margin <= x <= self.court.width_ft + margin and -margin <= y <= self.court.length_ft + margin

    def _dedupe_events(self, events: list[BounceEvent]) -> list[BounceEvent]:
        selected: list[BounceEvent] = []
        for event in sorted(events, key=lambda item: item.confidence, reverse=True):
            if any(abs(event.frame_index - kept.frame_index) < self.min_event_gap_frames for kept in selected):
                continue
            selected.append(event)
        ordered = sorted(selected, key=lambda item: item.frame_index)
        return [
            BounceEvent(
                event_id=f"bounce-{index + 1}",
                frame_index=event.frame_index,
                timestamp_sec=event.timestamp_sec,
                image_xy=event.image_xy,
                court_xy=event.court_xy,
                confidence=event.confidence,
                detection_method=event.detection_method,
                diagnostics=event.diagnostics,
                rally_id=event.rally_id,
            )
            for index, event in enumerate(ordered)
        ]

    def _velocity(self, coords: np.ndarray) -> np.ndarray:
        velocity = np.full(len(coords), np.nan, dtype=np.float32)
        for index in range(1, len(coords)):
            if np.isnan(coords[index]).any() or np.isnan(coords[index - 1]).any():
                continue
            velocity[index] = float(np.linalg.norm(coords[index] - coords[index - 1]) * self.fps)
        if len(velocity) > 1:
            velocity[0] = velocity[1]
        return velocity

    @staticmethod
    def _smooth(points: np.ndarray) -> np.ndarray:
        if len(points) < 3:
            return points
        smoothed = points.copy()
        for index in range(1, len(points) - 1):
            smoothed[index] = (points[index - 1] + points[index] * 2 + points[index + 1]) / 4.0
        return smoothed

    @staticmethod
    def _line_slope(x: np.ndarray, y: np.ndarray) -> float:
        if len(x) < 2:
            return 0.0
        return float(np.polyfit(np.asarray(x, dtype=np.float32), np.asarray(y, dtype=np.float32), 1)[0])

    @staticmethod
    def _angle_between(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
        denom = float(np.linalg.norm(vec_a) * np.linalg.norm(vec_b))
        if denom <= 1e-6:
            return 0.0
        cosine = float(np.clip(np.dot(vec_a, vec_b) / denom, -1.0, 1.0))
        return float(np.degrees(np.arccos(cosine)))

    @staticmethod
    def _point_line_distance(point: np.ndarray, line_start: np.ndarray, line_end: np.ndarray) -> float:
        line = line_end - line_start
        denom = float(np.linalg.norm(line))
        if denom <= 1e-6:
            return float(np.linalg.norm(point - line_start))
        delta = point - line_start
        cross = float(line[0] * delta[1] - line[1] * delta[0])
        return float(abs(cross) / denom)
