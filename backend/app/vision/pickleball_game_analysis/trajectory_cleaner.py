"""Trajectory outlier cleanup and short-gap interpolation."""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from app.vision.pickleball_game_analysis.schemas import Point2D, TrajectoryPoint


@dataclass(frozen=True)
class TrajectoryCleanerConfig:
    """
    轨迹清洗超参数。

    两件事：
      - 去掉"孤立跳变"的异常点（某一帧相对前后都突然很远）；
      - 对短距离缺失（连续无球）做线性插值补全。
    """

    max_interpolation_gap: int = 12  # 允许插值的最大缺失帧数（超过则不补）
    outlier_step_floor_px: float = 90.0  # 单帧位移的异常阈值下限（像素/帧），低于此不可能判为异常


class TrajectoryCleaner:
    """轨迹清洗器：先去异常点，再对短缺口做插值。"""

    def __init__(self, config: TrajectoryCleanerConfig | None = None) -> None:
        self.config = config or TrajectoryCleanerConfig()

    def clean(self, points: list[TrajectoryPoint]) -> list[TrajectoryPoint]:
        """对外主流程：去除异常点 → 插值补全缺失。"""
        return self.interpolate(self.remove_outliers(points))

    def remove_outliers(self, points: list[TrajectoryPoint]) -> list[TrajectoryPoint]:
        """
        去除"孤立跳变"异常点。

        判据：对候选点，比较它到前一个点、后一个点的距离，以及前后两点"直接跨越"的距离；
        若"前后两段都超过阈值"且"跨点距离低于阈值"，说明它像一个 outlier（突兀地偏离再回来），
        则把该点的 image_xy / court_xy / confidence 置空，并标记为 source="outlier_removed"。
        有效点过少（<5）则不做任何处理，直接返回原样副本。
        """
        cleaned = [replace(point) for point in points]
        coords = self._coords(cleaned)
        valid_indices = np.where(~np.isnan(coords[:, 0]) & ~np.isnan(coords[:, 1]))[0]
        if len(valid_indices) < 5:
            return cleaned

        # 先计算每段"每帧位移"（已按帧间隔归一化）
        steps: list[float] = []
        for left, right in zip(valid_indices[:-1], valid_indices[1:], strict=False):
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
            bridge_dist = float(
                np.linalg.norm(coords[next_index] - coords[prev_index]) / max(1, next_index - prev_index)
            )
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
        """
        短缺口线性插值：对两个有效点之间的缺失帧，按位置线性补全。

        规则：
          - 缺口长度 gap-1 超过 max_interpolation_gap 则不补；
          - 对中间每帧，按 alpha 比例在左右有效点之间插值 image_xy（及 court_xy）；
          - 补全点标记 interpolated=True、source="interpolated"、confidence=None（插值无置信度）。
        """
        interpolated = [replace(point) for point in points]
        valid = [index for index, point in enumerate(interpolated) if point.image_xy is not None]
        for left, right in zip(valid[:-1], valid[1:], strict=False):
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
        """把轨迹点抽成 numpy 坐标数组，缺失点填 (nan, nan)。"""
        return np.array(
            [point.image_xy if point.image_xy is not None else (np.nan, np.nan) for point in points], dtype=np.float32
        )

    @staticmethod
    def _previous_valid(coords: np.ndarray, index: int) -> int | None:
        """从 index 向前找最近一个非 nan 的坐标索引。"""
        for candidate in range(index - 1, -1, -1):
            if not np.isnan(coords[candidate]).any():
                return candidate
        return None

    @staticmethod
    def _next_valid(coords: np.ndarray, index: int) -> int | None:
        """从 index 向后找最近一个非 nan 的坐标索引。"""
        for candidate in range(index + 1, len(coords)):
            if not np.isnan(coords[candidate]).any():
                return candidate
        return None

    @staticmethod
    def _robust_threshold(values: np.ndarray, floor: float) -> float:
        """
        用"中位数 + 6×MAD（中位数绝对偏差）"估计异常阈值，且不低于 floor。

        MAD 对极端值不敏感，比直接用均值/标准差更稳健，适合找 outlier。
        """
        if len(values) == 0:
            return floor
        median = float(np.median(values))
        mad = float(np.median(np.abs(values - median)))
        return max(float(floor), median + 6.0 * max(mad, 1.0))

    @staticmethod
    def _lerp(start: Point2D, end: Point2D, alpha: float) -> Point2D:
        """线性插值：alpha=0 取 start，alpha=1 取 end。"""
        return (float(start[0] + (end[0] - start[0]) * alpha), float(start[1] + (end[1] - start[1]) * alpha))
