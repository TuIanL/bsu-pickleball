"""Ball derived metrics（球 3D：段级平均球速 / 最高点 / 过网高度）。

D8: 平均球速 = 3D path length / flight duration，带 eligibility 门（dual_view coverage、
回投残差、prediction 比例、段时长）。不满足 → average_speed=unavailable 但 landing 仍可用。
D7: 瞬时 / 出拍瞬时球速 V1 不输出。来源标注 derived_from_estimated_3d。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from app.vision.multiview.ball_stereo.segment_reconstruction import (
    Reconstructed3DSample,
    Reconstructed3DSegment,
)

# 球场下 42 英寸 = 3.5 ft 为常见网高（Pickleball 网高 36" 中点 / 34" 两侧；用 3.0 ft 近似）
NET_HEIGHT_FT = 3.0


@dataclass(frozen=True)
class BallMetrics:
    average_speed_kmh: float | None
    average_speed_validity: str  # estimated / unavailable
    peak_height_ft: float | None
    net_height_ft: float | None  # 过网高度（网处 z 扣减 NET_HEIGHT_FT）
    speed_eligibility_reason: str | None = None
    derived_from: str = "derived_from_estimated_3d"


def _path_length(samples: Sequence[Reconstructed3DSample]) -> float:
    if len(samples) < 2:
        return 0.0
    return sum(
        math.dist(s[i], s[i + 1])
        for s in [tuple((p.x_ft, p.y_ft, p.z_ft) for p in samples)]
        for i in range(len(s) - 1)
    )


def eligibility(
    *,
    coverage: float,
    reprojection_error_px: float,
    prediction_ratio: float,
    duration_sec: float,
    min_coverage: float = 0.4,
    max_reproj_px: float = 40.0,
    max_prediction_ratio: float = 0.6,
    min_duration_sec: float = 0.3,
) -> str | None:
    if coverage < min_coverage:
        return f"stereo_coverage_too_low_{coverage:.2f}"
    if reprojection_error_px > max_reproj_px:
        return f"reprojection_error_too_high_{reprojection_error_px:.1f}"
    if prediction_ratio > max_prediction_ratio:
        return f"prediction_ratio_too_high_{prediction_ratio:.2f}"
    if duration_sec < min_duration_sec:
        return f"duration_too_short_{duration_sec:.2f}"
    return None


def compute_metrics(
    segment: Reconstructed3DSegment,
    *,
    duration_sec: float,
    min_coverage: float = 0.4,
    max_reproj_px: float = 40.0,
    max_prediction_ratio: float = 0.6,
    min_duration_sec: float = 0.3,
) -> BallMetrics:
    samples = segment.samples
    heights = [s.z_ft for s in samples]
    peak = max(heights) if heights else None
    net_clearance = _net_clearance(samples)

    reason = eligibility(
        coverage=segment.stereo_coverage,
        reprojection_error_px=segment.reprojection_error_px,
        prediction_ratio=segment.prediction_ratio,
        duration_sec=duration_sec,
        min_coverage=min_coverage, max_reproj_px=max_reproj_px,
        max_prediction_ratio=max_prediction_ratio, min_duration_sec=min_duration_sec,
    )
    if reason is not None:
        return BallMetrics(None, "unavailable", peak, None, speed_eligibility_reason=reason)

    path_len = _path_length(samples)
    speed_mps = path_len / max(duration_sec, 1e-6)
    speed_kmh = speed_mps * 3.6
    return BallMetrics(
        average_speed_kmh=round(speed_kmh, 1),
        average_speed_validity="estimated",
        peak_height_ft=round(peak, 2) if peak is not None else None,
        net_height_ft=round(net_clearance, 2) if net_clearance is not None else None,
        speed_eligibility_reason=None,
    )


def _net_clearance(samples: Sequence[Reconstructed3DSample]) -> float | None:
    """过网高度：在 canonical y 跨越 22（球网）处内插 z，再扣减 NET_HEIGHT_FT。"""
    if len(samples) < 2:
        return None
    sorted_samples = sorted(samples, key=lambda s: s.y_ft)
    crossings = []
    for i in range(len(sorted_samples) - 1):
        y0, y1 = sorted_samples[i].y_ft, sorted_samples[i + 1].y_ft
        if y0 <= 22.0 <= y1 or y1 <= 22.0 <= y0:
            span = y1 - y0
            if abs(span) < 1e-9:
                continue
            f = (22.0 - y0) / span
            z = sorted_samples[i].z_ft + f * (sorted_samples[i + 1].z_ft - sorted_samples[i].z_ft)
            crossings.append(z)
    if not crossings:
        return None
    return float(min(crossings) - NET_HEIGHT_FT)