"""球检测链路共享的精度优先质量门。

这个模块只做确定性的规则判断，不运行 detector，也不修改 tracker 状态。
候选、运动、插值和双摄 pair 都返回结构化 reason code，供 tracker、stereo
association、artifact diagnostics 共同消费。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import acos, degrees, hypot, isfinite
from typing import Any, Sequence

from app.vision.pickleball_game_analysis.schemas import BallCandidate, Point2D


QUALITY_GATE_SCHEMA_VERSION = "ball_quality_gates.v1"


@dataclass(frozen=True)
class BallQualityGateConfig:
    """规则阈值快照；写入 artifact diagnostics 以便离线复现。"""

    schema_version: str = QUALITY_GATE_SCHEMA_VERSION
    min_confidence: float = 0.22
    max_box_area_ratio: float = 0.004
    max_aspect_ratio: float = 4.0
    min_box_size_px: float = 2.0
    court_margin_ft: float = 2.0
    max_interpolation_gap_seconds: float = 0.20
    max_speed_px_per_sec: float = 12000.0
    max_acceleration_px_per_sec2: float = 350000.0
    max_direction_change_degrees: float = 170.0
    max_reprojection_error_px: float = 24.0
    min_geometry_quality: float = 0.40
    min_pair_score_margin: float = 0.08
    max_z_ft: float = 50.0

    def snapshot(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class QualityGateDecision:
    """一次质量门判断的可审计结果。"""

    status: str
    reason: str
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def accepted(self) -> bool:
        return self.status == "accepted"


def evaluate_candidate(
    candidate: BallCandidate,
    *,
    frame_shape: Sequence[int],
    roi_corners: tuple[tuple[int, int], tuple[int, int]] | None,
    config: BallQualityGateConfig,
    point_in_roi: bool,
    projected_xy: Point2D | None = None,
    projection_detail: str | None = None,
    court_width_ft: float = 20.0,
    court_length_ft: float = 44.0,
) -> QualityGateDecision:
    """执行候选置信度、框形状、ROI 和球场投影约束。"""

    confidence = float(candidate.confidence)
    if not isfinite(confidence) or confidence < config.min_confidence:
        return QualityGateDecision("rejected", "low_confidence", {"confidence": confidence})

    width = float(candidate.width) if candidate.width is not None else None
    height = float(candidate.height) if candidate.height is not None else None
    if width is not None and height is not None and (width < config.min_box_size_px or height < config.min_box_size_px):
        return QualityGateDecision(
            "rejected",
            "box_too_small",
            {"width_px": width, "height_px": height, "min_box_size_px": config.min_box_size_px},
        )

    frame_area = max(1.0, float(frame_shape[0] * frame_shape[1]))
    area_ratio = candidate.area_ratio
    aspect_ratio = candidate.aspect_ratio
    if width is not None and height is not None:
        area_ratio = area_ratio if area_ratio is not None else width * height / frame_area
        aspect_ratio = aspect_ratio if aspect_ratio is not None else max(width / height, height / width)
    if area_ratio is not None and float(area_ratio) > config.max_box_area_ratio:
        return QualityGateDecision("rejected", "box_too_large", {"area_ratio": float(area_ratio)})
    if aspect_ratio is not None and float(aspect_ratio) > config.max_aspect_ratio:
        return QualityGateDecision("rejected", "aspect_ratio", {"aspect_ratio": float(aspect_ratio)})
    if not point_in_roi:
        return QualityGateDecision("rejected", "outside_roi", {"roi_configured": roi_corners is not None})

    if projection_detail in {"invalid_homography", "invalid_court_point"}:
        return QualityGateDecision("diagnostic_only", "invalid_court_projection", {"detail": projection_detail})
    if projected_xy is not None:
        x, y = projected_xy
        margin = max(0.0, config.court_margin_ft)
        in_prism_projection = -margin <= x <= court_width_ft + margin and -margin <= y <= court_length_ft + margin
        if not in_prism_projection:
            return QualityGateDecision(
                "rejected",
                "outside_court_projection",
                {"court_xy": [float(x), float(y)], "margin_ft": margin},
            )

    return QualityGateDecision(
        "accepted",
        "accepted",
        {
            "confidence": confidence,
            "area_ratio": float(area_ratio) if area_ratio is not None else None,
            "aspect_ratio": float(aspect_ratio) if aspect_ratio is not None else None,
            "projection_detail": projection_detail,
        },
    )


def evaluate_motion(
    history: Sequence[tuple[float, Point2D]],
    current_timestamp_sec: float,
    current_point: Point2D,
    *,
    config: BallQualityGateConfig,
) -> QualityGateDecision:
    """以真实秒级时间检查速度、加速度和方向跳变。"""

    if not history:
        return QualityGateDecision("accepted", "no_motion_history")
    previous_timestamp, previous_point = history[-1]
    dt = float(current_timestamp_sec) - float(previous_timestamp)
    if dt <= 0:
        return QualityGateDecision("rejected", "non_increasing_timestamp", {"dt_sec": dt})
    vx = (float(current_point[0]) - float(previous_point[0])) / dt
    vy = (float(current_point[1]) - float(previous_point[1])) / dt
    speed = hypot(vx, vy)
    diagnostics: dict[str, Any] = {"dt_sec": dt, "speed_px_per_sec": speed}
    if speed > config.max_speed_px_per_sec:
        return QualityGateDecision("rejected", "speed_jump", diagnostics)

    if len(history) < 2:
        return QualityGateDecision("accepted", "motion_consistent", diagnostics)
    previous_timestamp_2, previous_point_2 = history[-2]
    previous_dt = float(previous_timestamp) - float(previous_timestamp_2)
    if previous_dt <= 0:
        return QualityGateDecision("accepted", "motion_history_reset", diagnostics)
    pvx = (float(previous_point[0]) - float(previous_point_2[0])) / previous_dt
    pvy = (float(previous_point[1]) - float(previous_point_2[1])) / previous_dt
    acceleration = hypot(vx - pvx, vy - pvy) / max(dt, 1e-6)
    diagnostics["acceleration_px_per_sec2"] = acceleration
    if acceleration > config.max_acceleration_px_per_sec2:
        return QualityGateDecision("rejected", "acceleration_jump", diagnostics)

    previous_speed = hypot(pvx, pvy)
    if previous_speed > 1e-6 and speed > 1e-6:
        cosine = max(-1.0, min(1.0, (pvx * vx + pvy * vy) / (previous_speed * speed)))
        turn_degrees = degrees(acos(cosine))
        diagnostics["direction_change_degrees"] = turn_degrees
        if turn_degrees > config.max_direction_change_degrees:
            return QualityGateDecision("rejected", "direction_jump", diagnostics)
    return QualityGateDecision("accepted", "motion_consistent", diagnostics)


def evaluate_interpolation_gap(
    left_timestamp_sec: float,
    right_timestamp_sec: float,
    *,
    config: BallQualityGateConfig,
    blocked: bool = False,
) -> QualityGateDecision:
    """检查两个有效观测之间是否允许插值。"""

    gap = float(right_timestamp_sec) - float(left_timestamp_sec)
    if blocked:
        return QualityGateDecision("rejected", "explicit_break", {"gap_seconds": gap})
    if gap <= 0:
        return QualityGateDecision("rejected", "non_increasing_timestamp", {"gap_seconds": gap})
    if gap > config.max_interpolation_gap_seconds:
        return QualityGateDecision(
            "rejected", "long_gap", {"gap_seconds": gap, "max_gap_seconds": config.max_interpolation_gap_seconds}
        )
    return QualityGateDecision("accepted", "short_gap", {"gap_seconds": gap})


def evaluate_pair_quality(
    *,
    timestamp_delta_ms: float,
    reprojection_error_px: float,
    geometry_quality: float,
    depth_valid: bool,
    xyz: Sequence[float],
    score: float,
    next_best_score: float | None,
    previous_xyz: Sequence[float] | None,
    config: BallQualityGateConfig,
    max_time_delta_ms: float,
    court_width_ft: float = 20.0,
    court_length_ft: float = 44.0,
) -> QualityGateDecision:
    """双摄 pair 的时间、重投影、3D 范围和歧义余量硬门。"""

    if timestamp_delta_ms > max_time_delta_ms:
        return QualityGateDecision("rejected", "time_mismatch", {"sync_error_ms": timestamp_delta_ms})
    if not depth_valid:
        return QualityGateDecision("rejected", "invalid_depth")
    if len(xyz) < 3 or not all(isfinite(float(value)) for value in xyz[:3]):
        return QualityGateDecision("rejected", "non_finite_3d")
    x, y, z = (float(xyz[0]), float(xyz[1]), float(xyz[2]))
    if z < -0.5:
        return QualityGateDecision("rejected", "below_ground", {"z_ft": z})
    if z > config.max_z_ft:
        return QualityGateDecision("rejected", "z_absurd", {"z_ft": z})
    margin = config.court_margin_ft
    if not (-margin <= x <= court_width_ft + margin and -margin <= y <= court_length_ft + margin):
        return QualityGateDecision("rejected", "out_of_court", {"xyz": [x, y, z]})
    if reprojection_error_px > config.max_reprojection_error_px:
        return QualityGateDecision("rejected", "reprojection_error", {"reprojection_error_px": reprojection_error_px})
    if geometry_quality < config.min_geometry_quality:
        return QualityGateDecision("rejected", "geometry_quality", {"geometry_quality": geometry_quality})
    if next_best_score is not None and score - next_best_score < config.min_pair_score_margin:
        return QualityGateDecision(
            "diagnostic_only",
            "ambiguous_pair",
            {"score": score, "next_best_score": next_best_score, "margin": score - next_best_score},
        )
    if previous_xyz is not None:
        distance = hypot(hypot(x - float(previous_xyz[0]), y - float(previous_xyz[1])), z - float(previous_xyz[2]))
        if distance > 12.0:
            return QualityGateDecision("diagnostic_only", "3d_motion_jump", {"distance_ft": distance})
    return QualityGateDecision("accepted", "trusted_pair", {"score": score, "reprojection_error_px": reprojection_error_px})
