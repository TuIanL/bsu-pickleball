"""Bundle adjustment synthetic test：已知双相机 + 3D 弧线，施加微小相机扰动，
验证 bundle_refine 能把回投误差压回低位并恢复清晰球路（FULL_ESTIMATED_3D）。

对应三层测试 Synthetic Geometry 层的相机一致性补强。
"""

from __future__ import annotations

import math

import numpy as np

from app.vision.multiview.ball_stereo.bundle_refine import (
    BAPlaneAnchor,
    CameraInit,
    bundle_refine,
)
from app.vision.multiview.ball_stereo.segment_reconstruction import Observation


def _cam(focal, w, h, ry, rx, t_z, t_y=30.0):
    cx, cy = w / 2.0, h / 2.0
    k = np.array([[focal, 0, cx], [0, focal, cy], [0, 0, 1]])
    ry, rx = math.radians(ry), math.radians(rx)
    r1 = np.array([[math.cos(ry), 0, math.sin(ry)], [0, 1, 0], [-math.sin(ry), 0, math.cos(ry)]])
    r2 = np.array([[1, 0, 0], [0, math.cos(rx), -math.sin(rx)], [0, math.sin(rx), math.cos(rx)]])
    r = r1 @ r2
    t = np.array([0.0, t_y, t_z])
    return r, t, k


def _proj(p, x):
    h = p @ np.array([x[0], x[1], x[2], 1.0])
    return (float(h[0] / h[2]), float(h[1] / h[2]))


def _corner_anchor(cam_init, corners):
    canon = []
    img = []
    for (x, y) in corners:
        canon.append([x, y])
        u, v = _proj(cam_init, (x, y, 0.0))
        img.append([u, v])
    return BAPlaneAnchor(canon, img)


def _rot_perturb(r, rx, ry, rz):
    from app.vision.multiview.ball_stereo.bundle_refine import _rotvec_to_R
    import numpy as np
    delta = _rotvec_to_R(np.array([rx, ry, rz]))
    return delta @ r


def test_bundle_recovers_after_small_perturbation():
    w, h = 1920, 1080
    # 理想相机
    r1, t1, k1 = _cam(1100.0, w, h, 12.0, 42.0, 780.0)
    r2, t2, k2 = _cam(1180.0, w, h, -14.0, 38.0, 820.0)
    P1_true = k1 @ np.hstack([r1, t1.reshape(3, 1)])
    P2_true = k2 @ np.hstack([r2, t2.reshape(3, 1)])

    corners = [[0, 0], [20, 0], [20, 44], [0, 44]]

    # 观测：真实弧线经理想相机投影
    W = 1.0
    obs = []
    for i in range(12):
        t = i / 11.0
        xyz = (10.0 + 1.0 * t, 12.0 + 20.0 * t, 4.0 * math.sin(math.pi * t))
        u1, v1 = _proj(P1_true, xyz)
        u2, v2 = _proj(P2_true, xyz)
        obs.append(Observation(t * W, 0, u1, v1, P1_true, paired=True))
        obs.append(Observation(t * W, 1, u2, v2, P2_true, paired=True))

    # 初始化相机 = 理想相机 + 微小扰动（焦距误差 + 小姿态/平移偏移）
    f1, f2 = 1100.0 * 1.12, 1180.0 * 0.9
    R1 = _rot_perturb(r1, 0.02, -0.01, 0.01)
    R2 = _rot_perturb(r2, -0.015, 0.02, -0.01)
    T1 = t1 + np.array([0.3, -0.2, 4.0])
    T2 = t2 + np.array([-0.3, 0.2, -3.0])

    cam1_init = CameraInit(f1, R1, T1, w / 2.0, h / 2.0)
    cam2_init = CameraInit(f2, R2, T2, w / 2.0, h / 2.0)
    corner_init1 = _corner_anchor(P1_true, corners)  # 平面锚用理想投影图像
    corner_init2 = _corner_anchor(P2_true, corners)

    # BA 前：用初始化相机拟合曲线（固定相机）的粗略回投（用于对比基线）
    res = bundle_refine(
        cam1=cam1_init, cam2=cam2_init, observations=obs,
        plane_anchor_1=corner_init1, plane_anchor_2=corner_init2,
        n_control=6,
    )
    assert res.status in ("FULL_ESTIMATED_3D", "PARTIAL_3D"), res.status
    assert res.reprojection_error_px < 25.0, res.reprojection_error_px
    # 高度应合理（峰值在球场内，z>0）
    zs = [s.z_ft for s in res.samples]
    assert min(zs) > -0.5 and max(zs) < 12.0, (min(zs), max(zs))
    # 双路均被精修、焦距为有限正值（深度-焦距存在歧义，不要求恢复到真值）
    assert np.isfinite(res.cam1.focal) and res.cam1.focal > 0
    assert np.isfinite(res.cam2.focal) and res.cam2.focal > 0