"""Landing point authority（球 3D：落点权威）。

D6: bounce 事件权威第一版 = reference-view confirmed bounce（复用 BounceDetector，不重写）。
经 canonical clock 定夺 take_timestamp 后，在 Cam2 于 ± tolerance 内找最近 accepted ball evidence：
  双路均有 → 双路地面 Homography 加权融合
  仅 reference → 单视角落地
  均无        → landing unavailable
不从 3D 曲线与 z=0 交点倒推。字段用 landing_source + landing_validity（avoid metric 暗示）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

Point2D = tuple[float, float]


@dataclass(frozen=True)
class LandingPointResult:
    landing_xy: Point2D | None  # canonical court (x,y)
    landing_source: str  # dual_view_ground_fused / single_view_ground / unavailable
    landing_validity: str  # high / unavailable
    geometry_quality: float = 0.0  # 融合权重来源（加权平均的质量）


def _map_homography(image_xy: Point2D, homography) -> Point2D:
    """image → court 映射（H 为 image→court 方向，即 CalibrationResult.homography）。"""
    p = homography @ (image_xy[0], image_xy[1], 1.0)
    w = float(p[2])
    if abs(w) < 1e-12:
        raise ValueError("landing mapping degenerate")
    return (float(p[0] / w), float(p[1] / w))


def resolve_landing(
    *,
    reference_bounce: bool,
    reference_image_xy: Point2D,
    reference_homography,  # image→court
    reference_quality: float,
    cam2_image_xy: Point2D | None,
    cam2_homography,
    cam2_quality: float = 0.0,
) -> LandingPointResult:
    """依据能否在 Cam2 找到 accepted ball evidence，产出落点权威。"""
    if not reference_bounce:
        return LandingPointResult(None, "unavailable", "unavailable", 0.0)

    # 仅双路都具备离散像素证据才融合；否则单视角；再否则不可用
    if cam2_image_xy is not None:
        try:
            l1 = _map_homography(reference_image_xy, reference_homography)
            l2 = _map_homography(cam2_image_xy, cam2_homography)
        except ValueError:
            return LandingPointResult(None, "unavailable", "unavailable", 0.0)
        q1 = max(reference_quality, 1e-6)
        q2 = max(cam2_quality, 1e-6)
        w1 = q1 / (q1 + q2)
        w2 = q2 / (q1 + q2)
        fused = (w1 * l1[0] + w2 * l2[0], w1 * l1[1] + w2 * l2[1])
        return LandingPointResult(
            fused, "dual_view_ground_fused", "high",
            geometry_quality=round((q1 + q2) / 2.0, 3),
        )

    try:
        l1 = _map_homography(reference_image_xy, reference_homography)
    except ValueError:
        return LandingPointResult(None, "unavailable", "unavailable", 0.0)
    return LandingPointResult(l1, "single_view_ground", "high", geometry_quality=reference_quality)