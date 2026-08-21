"""Approximate stereo ball measurement（球 3D：逐 tick 立体证据）。

D4：两个视角的球候选在双视角均观测到（且 source frame 均为 available）时才产生
`BallStereoMeasurement`，作为不可变空间测量证据（source=dual_view_estimated），
不是最终三维球路。时间处理不做先二维内插：保留 Cam1@t1 / Cam2@t2 各自真实时刻，
`|t1-t2|` 足够小则生成时间约 canonical/midpoint 的 approximate 三角测量初值；
最终段级优化在每个摄像机自己的真实观测时刻回投。

本模块提供纯几何三角测量与证据结构，不含 detector/关联接线。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np


@dataclass(frozen=True)
class BallStereoMeasurement:
    """一次双视角近似三角测量的空间证据（非最终球路）。"""

    take_timestamp_ms: float
    cam1_timestamp_ms: float
    cam2_timestamp_ms: float
    cam1_image_xy: tuple[float, float]
    cam2_image_xy: tuple[float, float]
    estimated_x_ft: float
    estimated_y_ft: float
    estimated_z_ft: float
    sync_error_ms: float
    reprojection_error_cam1_px: float
    reprojection_error_cam2_px: float
    epipolar_residual_px: float
    geometry_quality: float  # 0..1，越高越可信
    confidence: float
    source: str = "dual_view_estimated"
    stereo_time_delta_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "take_timestamp_ms": self.take_timestamp_ms,
            "cam1_timestamp_ms": self.cam1_timestamp_ms,
            "cam2_timestamp_ms": self.cam2_timestamp_ms,
            "cam1_image_xy": [self.cam1_image_xy[0], self.cam1_image_xy[1]],
            "cam2_image_xy": [self.cam2_image_xy[0], self.cam2_image_xy[1]],
            "estimated_xy_ft": [self.estimated_x_ft, self.estimated_y_ft],
            "estimated_z_ft": self.estimated_z_ft,
            "sync_error_ms": self.sync_error_ms,
            "reprojection_error_cam1_px": self.reprojection_error_cam1_px,
            "reprojection_error_cam2_px": self.reprojection_error_cam2_px,
            "epipolar_residual_px": self.epipolar_residual_px,
            "geometry_quality": self.geometry_quality,
            "confidence": self.confidence,
            "source": self.source,
            "stereo_time_delta_ms": self.stereo_time_delta_ms,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> BallStereoMeasurement:
        img = payload.get("cam1_image_xy") or [0.0, 0.0]
        im2 = payload.get("cam2_image_xy") or [0.0, 0.0]
        xyz = payload.get("estimated_xy_ft") or [0.0, 0.0]
        return cls(
            take_timestamp_ms=float(payload["take_timestamp_ms"]),
            cam1_timestamp_ms=float(payload["cam1_timestamp_ms"]),
            cam2_timestamp_ms=float(payload["cam2_timestamp_ms"]),
            cam1_image_xy=(float(img[0]), float(img[1])),
            cam2_image_xy=(float(im2[0]), float(im2[1])),
            estimated_x_ft=float(xyz[0]),
            estimated_y_ft=float(xyz[1]),
            estimated_z_ft=float(payload["estimated_z_ft"]),
            sync_error_ms=float(payload["sync_error_ms"]),
            reprojection_error_cam1_px=float(payload["reprojection_error_cam1_px"]),
            reprojection_error_cam2_px=float(payload["reprojection_error_cam2_px"]),
            epipolar_residual_px=float(payload["epipolar_residual_px"]),
            geometry_quality=float(payload["geometry_quality"]),
            confidence=float(payload["confidence"]),
            source=str(payload.get("source", "dual_view_estimated")),
            stereo_time_delta_ms=float(payload.get("stereo_time_delta_ms", 0.0)),
        )


def triangulate_linear(
    projection_cam1: np.ndarray,
    projection_cam2: np.ndarray,
    image_xy1: Sequence[float],
    image_xy2: Sequence[float],
) -> np.ndarray:
    """DLT 双视角线性三角测量，返回 canonical 3D 点 (x,y,z, w) 归一化后 (x,y,z)。

    project 为 3x4 矩阵（canonical 齐次坐标 → 图像齐次坐标）。
    """
    p1 = projection_cam1
    p2 = projection_cam2
    u1, v1 = float(image_xy1[0]), float(image_xy1[1])
    u2, v2 = float(image_xy2[0]), float(image_xy2[1])

    a = np.array(
        [
            u1 * p1[2] - p1[0],
            v1 * p1[2] - p1[1],
            u2 * p2[2] - p2[0],
            v2 * p2[2] - p2[1],
        ],
        dtype=float,
    )
    _, _, vh = np.linalg.svd(a)
    x = vh[-1]
    if abs(float(x[3])) < 1e-12:
        raise ValueError("triangulation degenerate")
    return x[:3] / x[3]


def project_xyz(projection: np.ndarray, xyz: Sequence[float]) -> tuple[float, float]:
    """把 canonical 3D 点投影到图像（px），返回 (u, v)。"""
    h = projection @ np.array([xyz[0], xyz[1], xyz[2], 1.0])
    w = float(h[2])
    if abs(w) < 1e-9:
        raise ValueError("projection degenerates at w~0")
    return float(h[0] / w), float(h[1] / w)


def compute_geometry_quality(
    reproj_cam1_px: float,
    reproj_cam2_px: float,
    epipolar_px: float,
    stereo_time_delta_ms: float,
    max_reproj_px: float = 24.0,
    max_delta_ms: float = 40.0,
) -> float:
    """由回投残差、epipolar 残差与曝光差合成 0..1 的几何质量。"""
    reproj = max(reproj_cam1_px, reproj_cam2_px, epipolar_px)
    q_reproj = max(0.0, 1.0 - reproj / max_reproj_px)
    q_time = max(0.0, 1.0 - stereo_time_delta_ms / max_delta_ms)
    return round(min(1.0, 0.7 * q_reproj + 0.3 * q_time), 4)


def measure_stereo(
    *,
    projection_cam1: np.ndarray,
    projection_cam2: np.ndarray,
    image_xy1: Sequence[float],
    image_xy2: Sequence[float],
    cam1_timestamp_ms: float,
    cam2_timestamp_ms: float,
    take_timestamp_ms: float | None = None,
    sync_error_ms: float = 0.0,
    max_time_delta_ms: float = 40.0,
) -> BallStereoMeasurement:
    """生成一次近似立体测量（含时间模型：不做先二维内插，取 canonical/midpoint 时刻）。

    时间上，若两摄曝光差超过 max_time_delta_ms 则说明"同时观测"假设较弱，
    直接置 geometry_quality 下降（见 compute_geometry_quality）；三角测量仍基于各自真实图像点。
    """
    xyz = triangulate_linear(projection_cam1, projection_cam2, image_xy1, image_xy2)
    u1, v1 = project_xyz(projection_cam1, xyz)
    u2, v2 = project_xyz(projection_cam2, xyz)
    reproj1 = math.hypot(u1 - float(image_xy1[0]), v1 - float(image_xy1[1]))
    reproj2 = math.hypot(u2 - float(image_xy2[0]), v2 - float(image_xy2[1]))

    # epipolar residual：把 cam1 观测通过基本几何映射到 cam2 的近似残差（用往返回投近似）
    epipolar = 0.5 * (reproj1 + reproj2)

    take = take_timestamp_ms if take_timestamp_ms is not None else (cam1_timestamp_ms + cam2_timestamp_ms) / 2.0
    delta = abs(cam1_timestamp_ms - cam2_timestamp_ms)
    quality = compute_geometry_quality(reproj1, reproj2, epipolar, delta, max_delta_ms=max_time_delta_ms)
    # 近似置信度：几何质量与回投加权
    confidence = round(0.5 + 0.5 * quality, 4)

    return BallStereoMeasurement(
        take_timestamp_ms=take,
        cam1_timestamp_ms=cam1_timestamp_ms,
        cam2_timestamp_ms=cam2_timestamp_ms,
        cam1_image_xy=(float(image_xy1[0]), float(image_xy1[1])),
        cam2_image_xy=(float(image_xy2[0]), float(image_xy2[1])),
        estimated_x_ft=float(xyz[0]),
        estimated_y_ft=float(xyz[1]),
        estimated_z_ft=float(xyz[2]),
        sync_error_ms=sync_error_ms,
        reprojection_error_cam1_px=round(reproj1, 3),
        reprojection_error_cam2_px=round(reproj2, 3),
        epipolar_residual_px=round(epipolar, 3),
        geometry_quality=quality,
        confidence=confidence,
        stereo_time_delta_ms=delta,
    )