"""主链集成测试：关联 → 段重建 → 指标 → 落点（Synthetic Geometry 层）。

合成一个已知双摄 + 3D 弧线，投影出配对与单视角观测，验证整段重建与指标。
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.vision.multiview.ball_stereo.association import associate_views
from app.vision.multiview.ball_stereo.landing_authority import resolve_landing
from app.vision.multiview.ball_stereo.metrics import compute_metrics, eligibility
from app.vision.multiview.ball_stereo.segment_reconstruction import (
    FULL_ESTIMATED_3D,
    LANDING_ONLY,
    PARTIAL_3D,
    Observation,
    reconstruct_segment,
)
from app.vision.multiview.ball_stereo.stereo_measurement import triangulate_linear


def _cam(focal, w, h, ry, rx, t_z):
    cx, cy = w / 2.0, h / 2.0
    k = np.array([[focal, 0, cx], [0, focal, cy], [0, 0, 1]])
    ry, rx = math.radians(ry), math.radians(rx)
    r1 = np.array([
        [math.cos(ry), 0, math.sin(ry)],
        [0, 1, 0],
        [-math.sin(ry), 0, math.cos(ry)],
    ])
    r2 = np.array([
        [1, 0, 0],
        [0, math.cos(rx), -math.sin(rx)],
        [0, math.sin(rx), math.cos(rx)],
    ])
    r = r1 @ r2
    t = np.array([0.0, 25.0, t_z])
    return k @ np.hstack([r, t.reshape(3, 1)])


def _proj(p, x):
    h = p @ np.array([x[0], x[1], x[2], 1.0])
    return (h[0] / h[2], h[1] / h[2])


def _make_arc(t):
    """canonical 球场弧线：从近端 y=10 飞出过网到 y=30，~4ft 高。"""
    x = 10.0 + 1.0 * t
    y = 10.0 + 22.0 * t
    z = 4.5 * math.sin(math.pi * t)
    return (x, y, z)


def test_mainchain_reconstruct_full_with_landing():
    p1 = _cam(1200.0, 1920, 1080, 12.0, 42.0, 750.0)
    p2 = _cam(1150.0, 1920, 1080, -14.0, 38.0, 800.0)

    ts = 0.0
    obs = []
    W = 60.0
    for i in range(11):
        t = i / 10.0
        xyz = _make_arc(t)
        u1, v1 = _proj(p1, xyz)
        u2, v2 = _proj(p2, xyz)
        # 配对观测（各自真实时刻）
        obs.append(Observation(ts + t * W, 0, u1, v1, p1, paired=True))
        obs.append(Observation(ts + t * W + 4.0, 1, u2, v2, p2, paired=True))

    landing = (10.0, 33.0)  # 近末端落点（bounce_end=True 用 t=1 端）
    seg = reconstruct_segment(
        segment_id="seg1", observations=obs, landing_xy=landing, bounce_end=True,
        max_control_points=8,
    )
    assert seg.status in (FULL_ESTIMATED_3D, PARTIAL_3D), seg.status
    assert seg.stereo_coverage == 1.0
    # bounce 端 z≈0
    assert abs(seg.samples[-1].z_ft) < 1.5

    metrics = compute_metrics(seg, duration_sec=W)
    assert metrics.average_speed_validity == "estimated"
    assert metrics.average_speed_kmh is not None and metrics.average_speed_kmh > 0
    assert metrics.peak_height_ft is not None and metrics.peak_height_ft > 1.0


def test_mainchain_partial_with_single_view():
    p1 = _cam(1200.0, 1920, 1080, 12.0, 42.0, 750.0)
    p2 = _cam(1150.0, 1920, 1080, -14.0, 38.0, 800.0)
    W = 40.0
    obs = []
    for i in range(6):
        t = i / 5.0
        xyz = _make_arc(t)
        u1, v1 = _proj(p1, xyz)
        u2, v2 = _proj(p2, xyz)
        paired = (i % 2 == 0)
        obs.append(Observation(t * W, 0, u1, v1, p1, paired=paired))
        if paired:
            obs.append(Observation(t * W + 3.0, 1, u2, v2, p2, paired=True))

    seg = reconstruct_segment(segment_id="seg2", observations=obs, min_observations=3)
    # 含单视角观测 → 覆盖率 < 1，判 PARTIAL
    assert seg.status in (FULL_ESTIMATED_3D, PARTIAL_3D), seg.status
    assert seg.stereo_coverage < 1.0
    assert seg.stereo_coverage > 0.0


def test_association_rescues_local_misdetection():
    # Cam1 {A=真球, B=误检}，Cam2 {A=真球}；几何应选出 A↔A
    p1 = _cam(1200.0, 1920, 1080, 12.0, 42.0, 750.0)
    p2 = _cam(1150.0, 1920, 1080, -14.0, 38.0, 800.0)
    xyz_a = (10.0, 22.0, 3.0)
    u1a, v1a = _proj(p1, xyz_a)
    u2a, v2a = _proj(p2, xyz_a)
    cand1_a = (u1a, v1a, 0.8)
    cand1_b = (u1a + 500.0, v1a + 300.0, 0.9)  # 本地误检：离真实远，高置信

    pairs = associate_views(
        cam1_candidates=[cand1_a, cand1_b],
        cam2_candidates=[(u2a, v2a, 0.7)],
        projection_cam1=p1, projection_cam2=p2,
        cam1_timestamp_ms=100.0, cam2_timestamp_ms=102.0,
    )
    assert pairs, "should have at least one passing pairing"
    # 评分最高的配对应为真实 A↔A（回投残差小）
    best = pairs[0]
    assert best.cam1_candidate == cand1_a


def test_association_hard_gate_rejects_absurd():
    p1 = _cam(1200.0, 1920, 1080, 12.0, 42.0, 750.0)
    p2 = _cam(1150.0, 1920, 1080, -14.0, 38.0, 800.0)
    # 两路观测完全错配（远距），应全部被物理硬门拒绝
    pairs = associate_views(
        cam1_candidates=[(100.0, 100.0, 0.9)],
        cam2_candidates=[(1800.0, 900.0, 0.9)],
        projection_cam1=p1, projection_cam2=p2,
        cam1_timestamp_ms=100.0, cam2_timestamp_ms=300.0,  # 时间远
    )
    assert pairs == []  # 时间门拒绝


def test_landing_dual_and_single_and_none():
    # image→court 单应（identity 简单对角映射便于断言）
    Hg = np.array([[1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0]])
    dual = resolve_landing(
        reference_bounce=True, reference_image_xy=(10.0, 30.0), reference_homography=Hg,
        reference_quality=0.8,
        cam2_image_xy=(12.0, 31.0), cam2_homography=Hg, cam2_quality=0.6,
    )
    assert dual.landing_source == "dual_view_ground_fused"
    assert dual.landing_validity == "high"
    assert abs(dual.landing_xy[0] - 10.8) < 0.2  # 加权融合 (0.8/1.4*10 + 0.6/1.4*12)

    single = resolve_landing(
        reference_bounce=True, reference_image_xy=(10.0, 30.0), reference_homography=Hg,
        reference_quality=0.8, cam2_image_xy=None, cam2_homography=Hg,
    )
    assert single.landing_source == "single_view_ground"
    assert single.landing_xy == (10.0, 30.0)

    none = resolve_landing(
        reference_bounce=False, reference_image_xy=(10.0, 30.0), reference_homography=Hg,
        reference_quality=0.8, cam2_image_xy=None, cam2_homography=Hg,
    )
    assert none.landing_source == "unavailable"


def test_speed_eligibility_gate():
    assert eligibility(coverage=0.8, reprojection_error_px=12.0, prediction_ratio=0.1, duration_sec=0.8) is None
    assert eligibility(coverage=0.1, reprojection_error_px=12.0, prediction_ratio=0.1, duration_sec=0.8) is not None
    assert eligibility(coverage=0.8, reprojection_error_px=95.0, prediction_ratio=0.1, duration_sec=0.8) is not None