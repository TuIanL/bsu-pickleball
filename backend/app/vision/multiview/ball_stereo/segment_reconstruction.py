"""Dual-view 3D segment reconstruction（球 3D：整段曲线优化，核心）。

D5：逐帧 triangulation 只是 evidence。对每个飞行段，用**低维参数化**——Cubic B-spline
3D 曲线 (X(t),Y(t),Z(t))、t∈[0,1]、少量 control points（按段时长决定且有上限）——
同时满足：
  Σ Huber(proj_cam_i(XYZ(t_i)) − obs_i)   ← 各摄像机在**各自真实观测时刻**回投
  + 2 阶光滑 + bounce 端 z=0（hard）+ 落点 XY 锚 + z>=0 bound + max-height/max-speed soft
V1 不用 az=-g（避免理想抛物线支配视觉证据）。
段优化消费配对 + Cam1-only + Cam2-only 全部同段观测；暴露 stereo_coverage / prediction_ratio。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from app.vision.multiview.ball_stereo.stereo_measurement import BallStereoMeasurement

try:
    from scipy.optimize import least_squares
    _HAS_SCIPY = True
except ImportError:  # pragma: no cover
    _HAS_SCIPY = False


# 分层可用状态
FULL_ESTIMATED_3D = "FULL_ESTIMATED_3D"
PARTIAL_3D = "PARTIAL_3D"
LANDING_ONLY = "LANDING_ONLY"
UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class Observation:
    """一个真实像素观测（配对或单视角）。t_sec = 摄像机自己的真实观测时刻。"""

    t_sec: float
    cam_index: int  # 0=Cam1, 1=Cam2
    u: float
    v: float
    projection: np.ndarray  # 3x4，该摄像机虚拟相机 P
    paired: bool  # 该时刻是否有另一个视角的观测
    segment_id: str | None = None
    source_view_id: str | None = None
    quality_components: dict[str, float] = field(default_factory=dict)


@dataclass
class Reconstructed3DSample:
    t_norm: float
    x_ft: float
    y_ft: float
    z_ft: float
    source: str = "derived"
    validity: str = "valid"
    height_source: str | None = "estimated"
    height_confidence: float | None = None
    height_uncertainty_ft: float | None = None
    height_validity: str = "valid"


@dataclass
class Reconstructed3DSegment:
    segment_id: str
    status: str  # FULL_ESTIMATED_3D / PARTIAL_3D / LANDING_ONLY / UNAVAILABLE
    samples: list[Reconstructed3DSample] = field(default_factory=list)
    reprojection_error_px: float = math.inf
    stereo_coverage: float = 0.0
    prediction_ratio: float = 0.0
    adult: None = None
    height_validity: str = "unknown"
    height_quality_reason: str | None = None


def _b_spline_basis(t: float, knots: np.ndarray, degree: int, i: int) -> float:
    # Cox-de Boor 递归（t 在 [0,1]，clamped 样条）
    if degree == 0:
        if knots[i] <= t < knots[i + 1]:
            return 1.0
        return 0.0
    d1 = knots[i + degree] - knots[i]
    d2 = knots[i + degree + 1] - knots[i + 1]
    val = 0.0
    if d1 > 1e-12:
        val += ((t - knots[i]) / d1) * _b_spline_basis(t, knots, degree - 1, i)
    if d2 > 1e-12:
        val += ((knots[i + degree + 1] - t) / d2) * _b_spline_basis(t, knots, degree - 1, i + 1)
    return val


def _clamped_knots(n_controls: int, degree: int) -> np.ndarray:
    if n_controls <= degree:
        raise ValueError("cubic spline requires more control points than degree")
    repetitions = degree + 1
    inner_count = max(0, n_controls - degree - 1)
    inner = list(np.linspace(0.0, 1.0, inner_count + 2)[1:-1])
    return np.asarray([0.0] * repetitions + inner + [1.0] * repetitions, dtype=float)


class CubicSpline3D:
    """均匀 clamped cubic B-spline：(X,Y,Z) 由 control points（n×3）决定，t∈[0,1]。"""

    def __init__(self, control: np.ndarray, degree: int = 3):
        self.control = np.asarray(control, dtype=float)
        self.degree = degree
        self.knots = _clamped_knots(len(self.control), degree)

    def evaluate(self, t: float) -> np.ndarray:
        if t <= 0.0:
            return self.control[0].copy()
        if t >= 1.0:
            return self.control[-1].copy()
        basis = np.array([_b_spline_basis(t, self.knots, self.degree, i) for i in range(len(self.control))])
        return basis @ self.control

    def evaluate_many(self, ts: np.ndarray) -> np.ndarray:
        return np.stack([self.evaluate(float(t)) for t in ts])


def _residuals(params: np.ndarray, n_control: int, obs: list[Observation],
               landing_xy: tuple[float, float] | None, bounce_end: bool,
               w_smooth: float, w_anchor: float, w_bounce: float,
               w_zneg: float, w_plaus: float,
               max_height_ft: float, max_speed_ft_s: float, t_duration: float,
               t_norm_min: float, t_span: float) -> np.ndarray:
    control = params.reshape(n_control, 3)
    spline = CubicSpline3D(control)

    res = []
    # reprojection
    for o in obs:
        t_norm = (o.t_sec - t_norm_min) / t_span if t_span > 1e-9 else 0.0
        t_norm = min(1.0, max(0.0, t_norm))
        xyz = spline.evaluate(t_norm)
        try:
            h = o.projection @ np.array([xyz[0], xyz[1], xyz[2], 1.0])
            w = float(h[2])
            if abs(w) < 1e-9:
                res.append(50.0)
                continue
            pu, pv = h[0] / w, h[1] / w
        except Exception:
            res.append(50.0)
            continue
        res.append(pu - o.u)
        res.append(pv - o.v)

    # 2nd-derivative smoothness
    ts = np.linspace(0.0, 1.0, n_control + 2)
    pts = spline.evaluate_many(ts)
    d2 = np.diff(pts, n=2, axis=0) / (t_span ** 2)
    for row in d2:
        res.append(w_smooth * float(np.linalg.norm(row)))

    # bounce z=0 (hard) 与落点锚
    if bounce_end:
        end_x, end_y, end_z = spline.evaluate(1.0)
        res.append(w_bounce * end_z)
    if landing_xy is not None:
        lx, ly = landing_xy
        # 落点应取近端（若 bounce_end 用 t=1，否则用段中 z 最低点）
        tx = 1.0 if bounce_end else _argmin_z(spline)
        p = spline.evaluate(tx)
        res.append(w_anchor * (p[0] - lx))
        res.append(w_anchor * (p[1] - ly))

    # z >= 0 bound（软惩罚）
    zs = np.linspace(0.0, 1.0, 12)
    for zz in spline.evaluate_many(zs)[:, 2]:
        res.append(w_zneg * max(0.0, -zz))

    # max-height / max-speed soft plausibility
    heights = spline.evaluate_many(np.linspace(0, 1, 24))[:, 2]
    res.append(w_plaus * max(0.0, float(np.max(heights)) - max_height_ft))
    path_len = 0.0
    seq = spline.evaluate_many(ts)
    for i in range(1, len(seq)):
        path_len += float(np.linalg.norm(seq[i] - seq[i - 1]))
    speed = path_len / max(t_span, 1e-6)
    res.append(w_plaus * max(0.0, speed - max_speed_ft_s))

    return np.asarray(res, dtype=float)


def _argmin_z(spline: CubicSpline3D) -> float:
    ts = np.linspace(0.0, 1.0, 48)
    zs = spline.evaluate_many(ts)[:, 2]
    return float(ts[int(np.argmin(zs))])


def validate_height_profile(
    samples: list[Reconstructed3DSample],
    *,
    bounce_end: bool = False,
    ground_tolerance_ft: float = 1e-4,
    bounce_tolerance_ft: float = 1e-3,
    max_adjacent_jump_ft: float = 12.0,
) -> tuple[bool, str | None]:
    """对优化后的密集高度采样执行发布前安全校验。"""
    if not samples:
        return False, "empty_height_profile"
    heights = np.asarray([sample.z_ft for sample in samples], dtype=float)
    if not np.isfinite(heights).all():
        return False, "non_finite_height"
    if float(np.min(heights)) < -ground_tolerance_ft:
        return False, "below_ground"
    if bounce_end and abs(float(heights[-1])) > bounce_tolerance_ft:
        return False, "bounce_endpoint_not_grounded"
    if len(heights) > 1 and float(np.max(np.abs(np.diff(heights)))) > max_adjacent_jump_ft:
        return False, "abnormal_height_jump"
    return True, None


def reconstruct_segment(
    *,
    segment_id: str,
    observations: list[Observation],
    landing_xy: tuple[float, float] | None = None,
    bounce_end: bool = False,
    max_control_points: int = 12,
    max_height_ft: float = 14.0,
    max_speed_ft_s: float = 60.0,
    w_smooth: float = 0.05,
    w_anchor: float = 0.5,
    w_bounce: float = 2.0,
    w_zneg: float = 1.0,
    w_plaus: float = 0.1,
    min_observations: int = 2,
    stereo_measurements: list[BallStereoMeasurement] | None = None,
) -> Reconstructed3DSegment:
    """对一段观测拟合估算 3D 曲线，返回采样与质量诊断。

    - 只有配对观测 → 倾向 FULL_ESTIMATED_3D；含单视角 → PARTIAL_3D；
    - 观测不足或优化失败 → LANDING_ONLY / UNAVAILABLE（有落点则 LANDING_ONLY）。
    """
    baseline = Reconstructed3DSegment(segment_id=segment_id, status=UNAVAILABLE)

    if len(observations) < min_observations:
        if landing_xy is not None:
            baseline.status = LANDING_ONLY
            baseline.samples = [Reconstructed3DSample(0.0, landing_xy[0], landing_xy[1], 0.0, "anchor")]
        return baseline
    if not _HAS_SCIPY or not np.isfinite(np.asarray([o.u for o in observations])).all():
        if landing_xy is not None:
            baseline.status = LANDING_ONLY
        return baseline

    t_norm_min = min(o.t_sec for o in observations)
    t_norm_max = max(o.t_sec for o in observations)
    t_span = float(t_norm_max - t_norm_min) or 1.0

    paired_count = sum(1 for o in observations if o.paired)
    coverage = paired_count / len(observations)
    n_control = int(min(max_control_points, max(4, math.ceil(len(observations) / 3.0))))
    if len(observations) < n_control:
        n_control = max(4, min(n_control, len(observations)))

    # 初值：以配对三角测得的 xyz（或逐视角 xyz 均值）作为控制点锚
    init = np.zeros((n_control, 3))
    t_grid = np.linspace(0.0, 1.0, n_control)
    xs = []
    ys = []
    zs = []
    for o in observations:
        t_norm = (o.t_sec - t_norm_min) / t_span
        take_xyz = None
        # 尝试用该视角在 t_norm 处直接射线求最近点（简化：取该观测对应 3D 的近似）
        # 这里用简单启发：用观测直接反投影到球场有歧义，故用 Ding 射线即可——简化用逐观测三角化不可行，
        # 因此初值用"球场投影 + 恒定略高 z"并依赖优化收紧回投。
        xs.append(0.5)
        ys.append(0.5)
        zs.append(2.0)
    if len(xs) == 0:
        return baseline

    # 用球场几何做更好的初值：非关键，优化会修正；这里给中等高度弧线初值
    for i, tn in enumerate(t_grid):
        if landing_xy is not None:
            lx, ly = landing_xy
            base_x = lx - (lx - 10.0) * tn
            base_y = ly - (ly - 22.0) * tn
            hgt = 6.0 * math.sin(math.pi * tn)
            init[i] = [base_x, base_y, hgt]
        else:
            init[i] = [10.0, 22.0, 4.0 * math.sin(math.pi * tn) + 1.0]

    # 合格逐 tick 三角测量只作为稀疏初始化/锚点证据，不直接成为最终曲线。
    trusted = sorted(
        [measurement for measurement in stereo_measurements or [] if measurement.high_quality_anchor],
        key=lambda measurement: measurement.take_timestamp_ms,
    )
    if trusted:
        measurement_times = np.asarray([measurement.take_timestamp_ms / 1000.0 for measurement in trusted])
        measurement_times = (measurement_times - t_norm_min) / t_span
        measurement_times = np.clip(measurement_times, 0.0, 1.0)
        for axis, attr in enumerate(("estimated_x_ft", "estimated_y_ft", "estimated_z_ft")):
            values = np.asarray([float(getattr(measurement, attr)) for measurement in trusted])
            if len(values) == 1:
                init[:, axis] = 0.65 * init[:, axis] + 0.35 * values[0]
            else:
                init[:, axis] = 0.35 * init[:, axis] + 0.65 * np.interp(t_grid, measurement_times, values)

    params0 = init.reshape(-1)

    lower = np.full(n_control * 3, -np.inf, dtype=float)
    upper = np.full(n_control * 3, np.inf, dtype=float)
    # z 是优化变量的第三个分量。地面是硬边界，不再依赖软惩罚把负高度拉回去。
    lower[2::3] = 0.0
    if bounce_end:
        # clamped spline 的末端等于最后一个控制点，因此 bounce 端可直接施加等式边界。
        lower[-1] = 0.0
        # scipy 要求每个上下界严格有间隔；用 1e-9 作为数值等式窗口，发布采样仍强制为 0。
        upper[-1] = 1e-9
    params0[2::3] = np.maximum(params0[2::3], 0.0)
    if bounce_end:
        params0[-1] = 0.0

    try:
        result = least_squares(
            _residuals,
            params0,
            args=(n_control, observations, landing_xy, bounce_end, w_smooth, w_anchor, w_bounce,
                  w_zneg, w_plaus, max_height_ft, max_speed_ft_s, t_span, t_norm_min, t_span),
            method="trf", max_nfev=1200,
            loss="soft_l1",  # Huber 近似
            bounds=(lower, upper),
        )
    except Exception:
        if landing_xy is not None:
            baseline.status = LANDING_ONLY
        return baseline

    control = result.x.reshape(n_control, 3)
    spline = CubicSpline3D(control)

    # 采样
    n_samples = max(8, t_span * 8)
    ts = np.linspace(0.0, 1.0, int(n_samples))
    samples = [Reconstructed3DSample(float(t), *spline.evaluate(float(t))) for t in ts]
    if bounce_end and samples:
        samples[-1].z_ft = 0.0

    # 回投误差
    errs = []
    for o in observations:
        t_norm = min(1.0, max(0.0, (o.t_sec - t_norm_min) / t_span))
        xyz = spline.evaluate(t_norm)
        h = o.projection @ np.array([xyz[0], xyz[1], xyz[2], 1.0])
        w = float(h[2])
        if abs(w) > 1e-9:
            errs.append(math.hypot(h[0] / w - o.u, h[1] / w - o.v))
    reproj = float(np.mean(errs)) if errs else math.inf

    height_ok, height_reason = validate_height_profile(samples, bounce_end=bounce_end)
    if not height_ok:
        for sample in samples:
            sample.validity = "invalid"
            sample.height_validity = f"invalid_{height_reason}" if height_reason else "invalid"
        return Reconstructed3DSegment(
            segment_id=segment_id,
            status=UNAVAILABLE,
            samples=samples,
            reprojection_error_px=round(reproj, 3) if np.isfinite(reproj) else math.inf,
            stereo_coverage=round(coverage, 3),
            prediction_ratio=round(1.0 - coverage, 3),
            height_validity="invalid",
            height_quality_reason=height_reason,
        )

    if len(observations) >= min_observations and np.isfinite(reproj) and reproj < 60.0:
        status = FULL_ESTIMATED_3D if coverage >= 0.5 else PARTIAL_3D
    else:
        status = LANDING_ONLY if landing_xy is not None else UNAVAILABLE

    if status == UNAVAILABLE:
        # 保留诊断采样但显式标记无效，消费者不得把失败拟合串成一条可见球路。
        for sample in samples:
            sample.validity = "invalid"

    return Reconstructed3DSegment(
        segment_id=segment_id, status=status, samples=samples,
        reprojection_error_px=round(reproj, 3),
        stereo_coverage=round(coverage, 3),
        prediction_ratio=round(1.0 - coverage, 3),
        height_validity="valid",
    )
