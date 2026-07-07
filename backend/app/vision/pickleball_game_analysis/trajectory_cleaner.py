"""Trajectory outlier cleanup and short-gap interpolation."""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from app.vision.pickleball_game_analysis.schemas import Point2D, TrajectoryPoint


@dataclass(frozen=True)
class TrajectoryCleanerConfig:
    max_interpolation_gap: int = 12
    outlier_step_floor_px: float = 90.0


class TrajectoryCleaner:
    def __init__(self, config: TrajectoryCleanerConfig | None = None) -> None:
        self.config = config or TrajectoryCleanerConfig()

    def clean(self, points: list[TrajectoryPoint]) -> list[TrajectoryPoint]:
        return self.interpolate(self.remove_outliers(points))

    def remove_outliers(self, points: list[TrajectoryPoint]) -> list[TrajectoryPoint]:
        cleaned = [replace(point) for point in points]
        coords = self._coords(cleaned)
        valid_indices = np.where(~np.isnan(coords[:, 0]) & ~np.isnan(coords[:, 1]))[0]
        if len(valid_indices) < 5:
            return cleaned

        steps: list[float] = []
        for left, right in zip(valid_indices[:-1], valid_indices[1:]):
            frame_gap = max(1, cleaned[right].frame_index - cleaned[left].frame_index)
            steps.append(float(np.linalg.norm(coords[right] - coords[left]) / frame_gap))
        threshold = self._robust_threshold(np.array(steps, dtype=np.float32), self.config.outlier_step_floor_px)

        for index in valid_indices[1:-1]:
            prev_index = self._previous_valid(coords, int(index))
            next_index = self._next_valid(coords, int(index))
            if prev_index is None or next_index is None:
                continue
            prev_dist = float(np.linalg.norm(coords[index] - coords[prev_index]) / max(1, index - prev_index))
            next_dist = float(np.linalg.norm(coords[next_index] - coords[index]) / max(1, next_index - index))
            bridge_dist = float(np.linalg.norm(coords[next_index] - coords[prev_index]) / max(1, next_index - prev_index))
            if prev_dist > threshold and next_dist > threshold and bridge_dist < threshold:
                diagnostics = dict(cleaned[index].diagnostics)
                diagnostics["cleaner_reject_reason"] = "isolated_jump"
                cleaned[index] = replace(
                    cleaned[index],
                    image_xy=None,
                    court_xy=None,
                    confidence=None,
                    source="outlier_removed",
                    diagnostics=diagnostics,
                )
        return cleaned

    def interpolate(self, points: list[TrajectoryPoint]) -> list[TrajectoryPoint]:
        interpolated = [replace(point) for point in points]
        valid = [index for index, point in enumerate(interpolated) if point.image_xy is not None]
        for left, right in zip(valid[:-1], valid[1:]):
            gap = right - left
            if gap <= 1 or gap - 1 > self.config.max_interpolation_gap:
                continue
            left_point = interpolated[left]
            right_point = interpolated[right]
            if left_point.image_xy is None or right_point.image_xy is None:
                continue
            for index in range(left + 1, right):
                alpha = (index - left) / gap
                image_xy = self._lerp(left_point.image_xy, right_point.image_xy, alpha)
                court_xy = None
                if left_point.court_xy is not None and right_point.court_xy is not None:
                    court_xy = self._lerp(left_point.court_xy, right_point.court_xy, alpha)
                diagnostics = dict(interpolated[index].diagnostics)
                diagnostics["interpolation_source_frames"] = [left_point.frame_index, right_point.frame_index]
                interpolated[index] = replace(
                    interpolated[index],
                    image_xy=image_xy,
                    court_xy=court_xy,
                    confidence=None,
                    interpolated=True,
                    source="interpolated",
                    diagnostics=diagnostics,
                )
        return interpolated

    @staticmethod
    def _coords(points: list[TrajectoryPoint]) -> np.ndarray:
        return np.array([point.image_xy if point.image_xy is not None else (np.nan, np.nan) for point in points], dtype=np.float32)

    @staticmethod
    def _previous_valid(coords: np.ndarray, index: int) -> int | None:
        for candidate in range(index - 1, -1, -1):
            if not np.isnan(coords[candidate]).any():
                return candidate
        return None

    @staticmethod
    def _next_valid(coords: np.ndarray, index: int) -> int | None:
        for candidate in range(index + 1, len(coords)):
            if not np.isnan(coords[candidate]).any():
                return candidate
        return None

    @staticmethod
    def _robust_threshold(values: np.ndarray, floor: float) -> float:
        if len(values) == 0:
            return floor
        median = float(np.median(values))
        mad = float(np.median(np.abs(values - median)))
        return max(float(floor), median + 6.0 * max(mad, 1.0))

    @staticmethod
    def _lerp(start: Point2D, end: Point2D, alpha: float) -> Point2D:
        return (float(start[0] + (end[0] - start[0]) * alpha), float(start[1] + (end[1] - start[1]) * alpha))
