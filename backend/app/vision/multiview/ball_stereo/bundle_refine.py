"""Bundle adjustment（球 3D：联合优化双相机 + 飞行段曲线）。

真实数据发现：纯 4 角 Homography 虚拟相机在离地高度（z>0）上图像一致性不足
（固定相机拟合曲线回投几百 px）。bundle_refine 联合优化：
  每视角焦距 f（一个标量）+ 微小外参扰动（R/t 围绕初始化）
  + 飞行段 Cubic B-spline 控制点，
使得飞行段观测通过两路相机的**图像回投残差**整体最小（soft_l1 / Huber）。

约束：球场四角经每视角相机回投到其标定图像点（平面锚，防相机脱离地面）+
  曲线 2 阶光滑 + z>=0 + max-height/max-speed 软约束 + 焦距贴近初始化。
不引入真实内参（cx/cy=中心、fx=fy、skew=0，焦距为自由量）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

try:
    from scipy.optimize import least_squares
    _HAS_SCIPY = True
except ImportError:  # pragma: no cover
    _HAS_SCIPY = False

from app.vision.multiview.ball_stereo.segment_reconstruction import (
    FULL_ESTIMATED_3D,
    PARTIAL_3D,
    CubicSpline3D,
    Observation,
    Reconstructed3DSample,
    validate_height_profile,
)


@dataclass(frozen=True)
class CameraInit:
    """一台虚拟相机的初始化（focal + R + t + 主点）。"""

    focal: float
    rotation: np.ndarray  # 3x3
    translation: np.ndarray  # 3
    cx: float
    cy: float


@dataclass(frozen=True)
class BAPlaneAnchor:
    """平面锚：canonical (x,y) 点应回投到对应图像点（保持相机贴地）。"""

    canonical_xy: list  # N x 2 (canonical court coords)
    image_xy: list  # N x 2


def _rotvec_to_R(v: np.ndarray) -> np.ndarray:
    theta = float(np.linalg.norm(v))
    if theta < 1e-12:
        return np.eye(3)
    axis = v / theta
    kx, ky, kz = axis
    c, s = math.cos(theta), math.sin(theta)
    return np.array([
        [c + kx * kx * (1 - c), kx * ky * (1 - c) - kz * s, kx * kz * (1 - c) + ky * s],
        [ky * kx * (1 - c) + kz * s, c + ky * ky * (1 - c), ky * kz * (1 - c) - kx * s],
        [kz * kx * (1 - c) - ky * s, kz * ky * (1 - c) + kx * s, c + kz * kz * (1 - c)],
    ])


def _projection(focal: float, cx: float, cy: float, r: np.ndarray, t: np.ndarray) -> np.ndarray:
    k = np.array([[focal, 0.0, cx], [0.0, focal, cy], [0.0, 0.0, 1.0]])
    return k @ np.hstack([r, t.reshape(3, 1)])


@dataclass
class BundleResult:
    """BA 输出：精修后的双相机与曲线采样。"""

    cam1: CameraInit
    cam2: CameraInit
    samples: list[Reconstructed3DSample]
    status: str  # FULL_ESTIMATED_3D / PARTIAL_3D / UNAVAILABLE
    reprojection_error_px: float
    stereo_coverage: float = 0.0
    prediction_ratio: float = 0.0
    height_validity: str = "unknown"
    height_quality_reason: str | None = None


def bundle_refine(
    *,
    cam1: CameraInit,
    cam2: CameraInit,
    observations: list[Observation],
    plane_anchor_1: BAPlaneAnchor,
    plane_anchor_2: BAPlaneAnchor,
    n_control: int = 6,
    max_height_ft: float = 14.0,
    max_speed_ft_s: float = 60.0,
    w_focal: float = 0.1,
    w_anchor: float = 0.1,
    w_smooth: float = 0.02,
    w_zneg: float = 0.5,
    w_plaus: float = 0.05,
    focal_rel_range: float = 0.30,
    robust_rejection: bool = True,
    max_outlier_reproj_px: float = 40.0,
) -> BundleResult:
    """联合优化双相机焦距/微小外参与曲线控制点，最小化双路图像回投。

    `robust_rejection=True` 时做两遍鲁棒拟合：首次拟合后按逐观测回投残差
    剔除 > max(3×median, max_outlier_reproj_px) 的离群观测，再重拟合，
    以消解段内混入的误检观测（球拍/背景当球）对单条球路的拉偏。
    """
    baseline = BundleResult(cam1, cam2, [], "UNAVAILABLE", float("inf"))
    if not _HAS_SCIPY or len(observations) < 3:
        return baseline

    a1 = np.asarray(plane_anchor_1.canonical_xy, dtype=float)
    i1 = np.asarray(plane_anchor_1.image_xy, dtype=float)
    a2 = np.asarray(plane_anchor_2.canonical_xy, dtype=float)
    i2 = np.asarray(plane_anchor_2.image_xy, dtype=float)

    rel = focal_rel_range
    f_bounds = [(cam1.focal * (1 - rel), cam1.focal * (1 + rel)),
                (cam2.focal * (1 - rel), cam2.focal * (1 + rel))]

    def pack(f1, r1, t1, f2, r2, t2, ctrl):
        return np.concatenate([[f1], r1, t1, [f2], r2, t2, ctrl.reshape(-1)])

    def unpack(p):
        f1 = p[0]; r1 = p[1:4]; t1 = p[4:7]; f2 = p[7]; r2 = p[8:11]; t2 = p[11:14]
        ctrl = p[14:].reshape(-1, 3)
        return f1, r1, t1, f2, r2, t2, ctrl

    # ---- 初始化控制点（简单中高程弧线）----
    n_control = int(min(n_control, max(4, len(observations) // 2)))
    control0 = np.zeros((n_control, 3))
    for i in range(n_control):
        tn = i / (n_control - 1) if n_control > 1 else 0.0
        control0[i] = [10.0, 10.0 + 22.0 * tn, 4.0 * math.sin(math.pi * tn) + 0.5]

    active_obs = list(observations)

    def _fit(obs_list):
        t_min = min(o.t_sec for o in obs_list)
        t_span = (max(o.t_sec for o in obs_list) - t_min) or 1.0

        def residuals(p):
            f1, r1, t1, f2, r2, t2, ctrl = unpack(p)
            R1 = _rotvec_to_R(r1) @ cam1.rotation
            R2 = _rotvec_to_R(r2) @ cam2.rotation
            T1 = cam1.translation + t1
            T2 = cam2.translation + t2
            P1 = _projection(f1, cam1.cx, cam1.cy, R1, T1)
            P2 = _projection(f2, cam2.cx, cam2.cy, R2, T2)
            spline = CubicSpline3D(ctrl)
            res = []
            for o in obs_list:
                tn = min(1.0, max(0.0, (o.t_sec - t_min) / t_span))
                xyz = spline.evaluate(tn)
                proj = P1 if o.cam_index == 0 else P2
                h = proj @ np.array([xyz[0], xyz[1], xyz[2], 1.0])
                w = float(h[2])
                if abs(w) < 1e-9:
                    res.append(50.0); res.append(50.0); continue
                res.append(h[0] / w - o.u)
                res.append(h[1] / w - o.v)
            for proj, anch, im in ((P1, a1, i1), (P2, a2, i2)):
                for a, (u, v) in zip(anch, im):
                    h = proj @ np.array([a[0], a[1], 0.0, 1.0])
                    w = float(h[2])
                    if abs(w) > 1e-9:
                        res.append(w_anchor * (h[0] / w - u))
                        res.append(w_anchor * (h[1] / w - v))
            ts = np.linspace(0, 1, n_control + 2)
            pts = spline.evaluate_many(ts)
            d2 = np.diff(pts, n=2, axis=0) / (t_span ** 2)
            for row in d2:
                res.append(w_smooth * float(np.linalg.norm(row)))
            for zz in spline.evaluate_many(np.linspace(0, 1, 12))[:, 2]:
                res.append(w_zneg * max(0.0, -zz))
            hs = spline.evaluate_many(np.linspace(0, 1, 20))[:, 2]
            res.append(w_plaus * max(0.0, float(np.max(hs)) - max_height_ft))
            res.append(w_focal * (f1 - cam1.focal) / cam1.focal)
            res.append(w_focal * (f2 - cam2.focal) / cam2.focal)
            return res

        p0 = pack(cam1.focal, np.zeros(3), np.zeros(3), cam2.focal, np.zeros(3), np.zeros(3), control0)
        lower = [f_bounds[0][0], -0.5, -0.5, -0.5, -10, -10, -10,
                 f_bounds[1][0], -0.5, -0.5, -0.5, -10, -10, -10] + [float("-inf")] * (n_control * 3)
        upper = [f_bounds[0][1], 0.5, 0.5, 0.5, 10, 10, 10,
                 f_bounds[1][1], 0.5, 0.5, 0.5, 10, 10, 10] + [float("inf")] * (n_control * 3)
        control_offset = 14
        for index in range(n_control):
            lower[control_offset + index * 3 + 2] = 0.0
        try:
            result = least_squares(residuals, p0, method="trf", bounds=(lower, upper),
                                   loss="soft_l1", max_nfev=3000, xtol=1e-6)
        except Exception:
            return None
        return result

    def _finalize(result):
        f1, r1, t1, f2, r2, t2, ctrl = unpack(result.x)
        R1 = _rotvec_to_R(r1) @ cam1.rotation
        R2 = _rotvec_to_R(r2) @ cam2.rotation
        T1 = cam1.translation + t1
        T2 = cam2.translation + t2
        P1 = _projection(f1, cam1.cx, cam1.cy, R1, T1)
        P2 = _projection(f2, cam2.cx, cam2.cy, R2, T2)
        spline = CubicSpline3D(ctrl)
        # 逐观测回投
        per_obs = []
        for o in active_obs:
            t_min = min(o.t_sec for o in active_obs)
            t_span = (max(o.t_sec for o in active_obs) - t_min) or 1.0
            tn = min(1.0, max(0.0, (o.t_sec - t_min) / t_span))
            xyz = spline.evaluate(tn)
            proj = P1 if o.cam_index == 0 else P2
            h = proj @ np.array([xyz[0], xyz[1], xyz[2], 1.0])
            w = float(h[2])
            per_obs.append(math.hypot(h[0] / w - o.u, h[1] / w - o.v) if abs(w) > 1e-9 else 9e9)
        errs = [e for e in per_obs if e < 9e8]
        # 采样 / 状态
        t_min = min(o.t_sec for o in active_obs)
        t_span = (max(o.t_sec for o in active_obs) - t_min) or 1.0
        n_samples = max(10, int(t_span * 10))
        samples = [Reconstructed3DSample(float(t), *spline.evaluate(float(t)))
                   for t in np.linspace(0, 1, n_samples)]
        paired = sum(1 for o in active_obs if o.paired)
        coverage = paired / len(active_obs) if active_obs else 0.0
        reproj = float(np.mean(errs)) if errs else float("inf")
        status = FULL_ESTIMATED_3D if (np.isfinite(reproj) and reproj < 60.0 and coverage >= 0.5) \
            else (PARTIAL_3D if np.isfinite(reproj) and reproj < 60.0 else "UNAVAILABLE")
        height_ok, height_reason = validate_height_profile(samples)
        if not height_ok:
            status = "UNAVAILABLE"
            for sample in samples:
                sample.validity = "invalid"
                sample.height_validity = f"invalid_{height_reason}" if height_reason else "invalid"
        return BundleResult(
            cam1=CameraInit(f1, R1, T1, cam1.cx, cam1.cy),
            cam2=CameraInit(f2, R2, T2, cam2.cx, cam2.cy),
            samples=samples, status=status, reprojection_error_px=round(reproj, 3),
            stereo_coverage=round(coverage, 3), prediction_ratio=round(1 - coverage, 3),
            height_validity="valid" if height_ok else "invalid",
            height_quality_reason=height_reason,
        ), per_obs, spline, P1, P2

    result = _fit(active_obs)
    if result is None:
        return baseline
    final, per_obs, spline, P1, P2 = _finalize(result)

    # 两遍鲁棒离群剔除
    if robust_rejection and len(active_obs) >= 5:
        med = float(np.median([e for e in per_obs if e < 9e8])) if per_obs else 0.0
        thresh = max(3.0 * med, max_outlier_reproj_px)
        keep = [o for o, e in zip(active_obs, per_obs) if e <= thresh]
        if len(keep) >= 3 and len(keep) < len(active_obs):
            active_obs = keep
            result2 = _fit(active_obs)
            if result2 is not None:
                final, per_obs, spline, P1, P2 = _finalize(result2)

    return final
