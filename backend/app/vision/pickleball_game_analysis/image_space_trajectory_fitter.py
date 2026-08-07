"""图像空间鲁棒轨迹拟合（image_space_trajectory_fitter）。

在测量空间（图像像素坐标）对飞行段做带置信度权重的 Huber 二次回归拟合
`u(t)`、`v(t)`；存在严重离群点时先用 RANSAC 初始化。损失基于图像坐标，
不使用已失真的球场坐标。

RANSAC 固定随机种子，保证确定性（设计决策：同一输入重复运行结果一致）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite

import numpy as np

from app.vision.pickleball_game_analysis.schemas import TrajectoryPoint


@dataclass(frozen=True)
class FitConfig:
    """图像拟合超参数。"""

    min_observation_points: int = 6  # 低于此数量不输出正式拟合曲线
    ransac_iterations: int = 120  # RANSAC 迭代次数
    ransac_inlier_threshold_px: float = 12.0  # RANSAC 内点阈值（像素）
    ransac_random_seed: int = 0  # 固定随机种子（确定性）
    huber_delta_px: float = 10.0  # Huber 损失的拐点（像素）
    huber_iterations: int = 8  # IRLS 迭代次数
    interpolated_weight: float = 0.3  # 插值点的低权重（置信度不可信）


@dataclass
class FitResult:
    """一次图像拟合的结果。"""

    u_coeff: tuple[float, float, float] = (0.0, 0.0, 0.0)  # u(t) = a0 + a1*t + a2*t²
    v_coeff: tuple[float, float, float] = (0.0, 0.0, 0.0)  # v(t) = b0 + b1*t + b2*t²
    t_offset: float = 0.0  # t 时间原点（减去首观测时间，秒）
    residual_rmse_px: float = 0.0  # 图像拟合残差（像素）
    coverage: float = 0.0  # 观测覆盖率（有效观测帧 / 段跨度帧）
    observed_count: int = 0
    expected_count: int = 0
    outlier_indices: list[int] = field(default_factory=list)  # 判定为离群点的局部下标
    converged: bool = False


class ImageSpaceTrajectoryFitter:
    """对单个飞行段的图像坐标做鲁棒二次回归拟合。"""

    def __init__(self, config: FitConfig | None = None) -> None:
        self.config = config or FitConfig()

    def fit(self, points: list[TrajectoryPoint]) -> FitResult:
        """拟合一组轨迹点（使用 image_xy 非 None 的点）。"""
        # 提取有效观测：image_xy 有限
        obs_indices: list[int] = []
        obs_time: list[float] = []
        obs_u: list[float] = []
        obs_v: list[float] = []
        for index, point in enumerate(points):
            xy = point.image_xy
            if xy is None or not (isfinite(xy[0]) and isfinite(xy[1])):
                continue
            obs_indices.append(index)
            obs_time.append(float(point.timestamp_sec))
            obs_u.append(float(xy[0]))
            obs_v.append(float(xy[1]))

        expected_count = len(points)
        observed_count = len(obs_indices)
        if observed_count < self.config.min_observation_points:
            return FitResult(
                observed_count=observed_count,
                expected_count=expected_count,
                coverage=0.0,
                converged=False,
            )

        t = np.asarray(obs_time, dtype=np.float64)
        t0 = float(t[0])
        tn = t - t0
        u = np.asarray(obs_u, dtype=np.float64)
        v = np.asarray(obs_v, dtype=np.float64)

        # 权重：插值点低权重，检测点用其置信度
        weights = np.asarray(
            [
                self.config.interpolated_weight
                if point.interpolated or point.source == "interpolated"
                else max(0.1, min(1.0, point.confidence if point.confidence is not None else 0.5))
                for point in (points[index] for index in obs_indices)
            ],
            dtype=np.float64,
        )

        # 先 RANSAC 初始化，再 Huber（IRLS）精修
        inlier_mask = self._ransac_init(tn, u, v, weights)
        u_coeff, v_coeff = self._huber_refine(tn, u, v, weights, inlier_mask)
        fitted_u, fitted_v = self._evaluate(tn, u_coeff, v_coeff)

        residual = np.hypot(u - fitted_u, v - fitted_v)
        rmse = float(np.sqrt(float(np.mean(residual**2))))
        outlier_indices = [obs_indices[index] for index in range(observed_count) if not inlier_mask[index]]

        # 覆盖率：段内（首末有效观测之间）有多少比例被观测覆盖
        span = max(1, int(points[-1].frame_index) - int(points[0].frame_index) + 1)
        coverage = float(observed_count) / float(span) if span > 0 else 0.0

        return FitResult(
            u_coeff=u_coeff,
            v_coeff=v_coeff,
            t_offset=t0,
            residual_rmse_px=round(rmse, 3),
            coverage=round(min(1.0, coverage), 4),
            observed_count=observed_count,
            expected_count=expected_count,
            outlier_indices=outlier_indices,
            converged=True,
        )

    def evaluate(
        self,
        result: FitResult,
        timestamps_sec: list[float] | np.ndarray,
    ) -> tuple[list[tuple[float, float]], np.ndarray, np.ndarray]:
        """在任意时间点上评估拟合曲线，返回 [(u, v)] 与 u/v 数组。"""
        tn = np.asarray(timestamps_sec, dtype=np.float64) - result.t_offset
        u, v = self._evaluate(tn, result.u_coeff, result.v_coeff)
        points = [(float(ui), float(vi)) for ui, vi in zip(u, v, strict=False)]
        return points, u, v

    # ---- 内部实现 ----

    def _design_matrix(self, t: np.ndarray) -> np.ndarray:
        return np.column_stack([np.ones_like(t), t, t * t])

    def _evaluate(
        self,
        tn: np.ndarray,
        u_coeff: tuple[float, float, float],
        v_coeff: tuple[float, float, float],
    ) -> tuple[np.ndarray, np.ndarray]:
        x = self._design_matrix(tn)
        u = x @ np.asarray(u_coeff, dtype=np.float64)
        v = x @ np.asarray(v_coeff, dtype=np.float64)
        return u, v

    def _least_squares(
        self,
        tn: np.ndarray,
        u: np.ndarray,
        v: np.ndarray,
        weights: np.ndarray,
    ) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        x = self._design_matrix(tn)
        w = np.sqrt(np.clip(weights, 1e-6, None))
        xw = x * w[:, None]
        uw = u * w
        vw = v * w
        u_coeff, *_ = np.linalg.lstsq(xw, uw, rcond=None)
        v_coeff, *_ = np.linalg.lstsq(xw, vw, rcond=None)
        return tuple(float(c) for c in u_coeff), tuple(float(c) for c in v_coeff)

    def _ransac_init(
        self,
        tn: np.ndarray,
        u: np.ndarray,
        v: np.ndarray,
        weights: np.ndarray,
    ) -> np.ndarray:
        """RANSAC 初始化：在固定种子的随机子集上做最小二乘，统计内点。"""
        rng = np.random.RandomState(self.config.ransac_random_seed)
        n = len(tn)
        best_inliers = np.zeros(n, dtype=bool)
        if n < 4:
            return np.ones(n, dtype=bool)
        threshold = self.config.ransac_inlier_threshold_px
        for _ in range(self.config.ransac_iterations):
            sample = rng.choice(n, size=min(4, n), replace=False)
            if np.unique(sample).size < 3:
                continue
            try:
                u_coeff, v_coeff = self._least_squares(tn[sample], u[sample], v[sample], weights[sample])
            except np.linalg.LinAlgError:
                continue
            fit_u, fit_v = self._evaluate(tn, u_coeff, v_coeff)
            residual = np.hypot(u - fit_u, v - fit_v)
            inliers = residual < threshold
            if int(inliers.sum()) > int(best_inliers.sum()):
                best_inliers = inliers
        return best_inliers

    def _huber_refine(
        self,
        tn: np.ndarray,
        u: np.ndarray,
        v: np.ndarray,
        weights: np.ndarray,
        inlier_mask: np.ndarray,
    ) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        """Huber 损失（IRLS 迭代加权最小二乘）精修，初始权重由 RANSAC 内点决定。"""
        delta = self.config.huber_delta_px
        eff_weights = weights.copy()
        if inlier_mask.any():
            eff_weights[~inlier_mask] *= 0.25  # RANSAC 判定的离群点降权

        u_coeff = (0.0, 0.0, 0.0)
        v_coeff = (0.0, 0.0, 0.0)
        for _ in range(self.config.huber_iterations):
            u_coeff, v_coeff = self._least_squares(tn, u, v, eff_weights)
            fit_u, fit_v = self._evaluate(tn, u_coeff, v_coeff)
            residual = np.hypot(u - fit_u, v - fit_v)
            # Huber 权重：|r| <= delta 时 w=1，否则 w=delta/|r|
            huber_w = np.where(residual <= delta, 1.0, delta / np.maximum(residual, 1e-6))
            eff_weights = weights * huber_w
        return u_coeff, v_coeff
