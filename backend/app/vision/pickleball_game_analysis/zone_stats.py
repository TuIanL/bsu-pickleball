"""球员空间热力图（zone stats）计算 —— 每球员三段区域占用 + Kitchen Control Rate + 网前控制反馈。

数据来源是 VisualizationPoint（球员轨迹点，含 label / x_ft / y_ft / timestamp_seconds）。
有效时间（分母）按可用性分层：调用方传入 effective_windows（比赛净时间窗口）时用它，
否则回退为该球员轨迹首帧至末帧的总时长。
"""

from __future__ import annotations

from typing import Any

from app.vision.courtvision_calibration_engine.court_geometry import PickleballCourtGeometry, standard_court
from app.vision.pickleball_game_analysis.visualization_schemas import (
    PlayerZoneStats,
    ZoneFeedback,
    ZoneStat,
    canonical_player_id,
    display_player_label,
    player_palette_color,
)
from app.vision.pickleball_performance_engine.zone_metrics import ZONE_LABELS, zone_for

# 有效帧充分性阈值：窗口内实际跟踪时间 / 分母 < 该值 → 标记 insufficient。
DATA_SUFFICIENCY_THRESHOLD = 0.3
# 英尺 → 米换算系数（体育习惯用米表示站位距离）。
FEET_TO_METERS = 0.3048


def compute_zone_stats(
    player_points: list[Any],
    *,
    effective_windows: list[tuple[float, float]] | None = None,
    reference_distance_m: float = 0.9,
    court: PickleballCourtGeometry | None = None,
    colors: list[str] | None = None,
) -> list[PlayerZoneStats]:
    """计算每名球员的区域占用统计与网前控制反馈。

    - player_points：每个点需带 label / x_ft / y_ft / timestamp_seconds。
    - effective_windows：比赛有效时间窗口（秒，半开区间）；None 时回退每球员总时长。
    - reference_distance_m：平均站位距厨房线"参考基准"（硬编码常数，反馈文案标注为参考基准）。
    - colors：按 canonical 球员序号分配的球员颜色（与散点图/热力图保持一致），缺省用空色。
    返回顺序与散点图分组一致（按 label 字典序），保证跨图 id/color 对齐。
    """
    court = court or standard_court()
    stats: list[PlayerZoneStats] = []
    grouped = _group_points_by_label(player_points)
    for index, (label, points) in enumerate(sorted(grouped.items())):
        stats.append(
            _player_stats(
                label,
                points,
                effective_windows=effective_windows,
                reference_distance_m=reference_distance_m,
                court=court,
                player_id=canonical_player_id(label),
                color=player_palette_color(colors, index, label),
            )
        )
    return stats


def _player_stats(
    label: str,
    points: list[Any],
    *,
    effective_windows: list[tuple[float, float]] | None,
    reference_distance_m: float,
    court: PickleballCourtGeometry,
    player_id: str,
    color: str,
) -> PlayerZoneStats:
    """单名球员的区域统计（沿用 kitchen_dwell 的相邻帧时间差累计法）。"""
    tracked = [
        point
        for point in points
        if point.x_ft is not None
        and point.y_ft is not None
        and point.timestamp_seconds is not None
        and court.is_in_tracking_bounds(point.x_ft, point.y_ft)
    ]
    tracked.sort(key=lambda point: point.timestamp_seconds or 0.0)

    denominator = _denominator_seconds(tracked, effective_windows)
    zone_seconds = {zone: 0.0 for zone in ZONE_LABELS}
    tracked_seconds = 0.0
    dist_weighted_sum = 0.0
    dist_weight = 0.0
    # own-side 口径：按有效时间内 y 中位数推断球员所属半场，只量该半场厨房线；
    # 无法判定时回退最近厨房线（反馈文案标注口径受限）。
    own_side = _infer_own_side(tracked, effective_windows, court)

    for previous, current in zip(tracked, tracked[1:], strict=False):
        delta = max(0.0, (current.timestamp_seconds or 0.0) - (previous.timestamp_seconds or 0.0))
        if delta <= 0:
            continue
        # 只统计落在有效时间窗口内的相邻帧对（无窗口时全部计入）。
        if not _in_windows(previous.timestamp_seconds or 0.0, effective_windows):
            continue
        tracked_seconds += delta
        # 区域占用只计球场内点；界外（如底线后方）时间计入 tracked_seconds 但不属于任何区。
        if court.is_in_court_bounds(previous.x_ft, previous.y_ft):
            zone = zone_for(previous.x_ft, previous.y_ft, court)
            if zone is not None:
                zone_seconds[zone] += delta
            # 平均站位距厨房线（own-side）：量所属半场厨房线的纵向距离，时间加权。
            distance_ft = _own_side_distance_ft(previous.y_ft, own_side, court)
            dist_weighted_sum += distance_ft * delta
            dist_weight += delta

    kitchen_seconds = zone_seconds["kitchen"]
    nvz_occupancy = max(0.0, min(1.0, kitchen_seconds / denominator)) if denominator > 0 else 0.0
    data_sufficiency = (
        "sufficient"
        if denominator > 0 and tracked_seconds / denominator >= DATA_SUFFICIENCY_THRESHOLD
        else "insufficient"
    )
    avg_distance_m = dist_weighted_sum / dist_weight * FEET_TO_METERS if dist_weight > 0 else 0.0

    zones = [
        ZoneStat(
            zone=zone,
            label=ZONE_LABELS[zone],
            seconds=round(seconds, 2),
            occupancy=round(seconds / denominator, 4) if denominator > 0 else 0.0,
        )
        for zone, seconds in zone_seconds.items()
    ]

    return PlayerZoneStats(
        id=player_id,
        label=display_player_label(label),
        color=color,
        denominator_seconds=round(denominator, 2),
        tracked_seconds=round(tracked_seconds, 2),
        data_sufficiency=data_sufficiency,
        nvz_occupancy_rate=round(nvz_occupancy, 4),
        kitchen_control_rate=round(nvz_occupancy, 4),  # deprecated alias：同值同分母
        avg_distance_to_kitchen_line_m=round(avg_distance_m, 1),
        zones=zones,
        feedback=_feedback(avg_distance_m, reference_distance_m, nvz_occupancy, own_side_known=own_side is not None),
    )


def _infer_own_side(
    tracked: list[Any],
    effective_windows: list[tuple[float, float]] | None,
    court: PickleballCourtGeometry,
) -> str | None:
    """按有效时间内 y 中位数推断球员所属半场（near / far）；无法判定返回 None。"""
    net_y = court.net_y_ft
    ys = [
        point.y_ft
        for point in tracked
        if point.y_ft is not None and _in_windows(point.timestamp_seconds or 0.0, effective_windows)
    ]
    if not ys:
        return None
    ys.sort()
    median = ys[len(ys) // 2]
    if median < net_y:
        return "near"
    if median > net_y:
        return "far"
    return None


def _own_side_distance_ft(y_ft: float, own_side: str | None, court: PickleballCourtGeometry) -> float:
    """own-side 厨房线距离：量所属半场厨房线；无法判定半场时回退最近厨房线。"""
    if own_side == "near":
        return abs(y_ft - court.near_kitchen_y_ft)
    if own_side == "far":
        return abs(y_ft - court.far_kitchen_y_ft)
    return min(abs(y_ft - court.near_kitchen_y_ft), abs(y_ft - court.far_kitchen_y_ft))


def _denominator_seconds(
    tracked: list[Any],
    windows: list[tuple[float, float]] | None,
) -> float:
    """分母：有有效窗口时 = Σ窗口长度；否则 = 该球员轨迹首帧至末帧总时长。"""
    if windows:
        return sum(max(0.0, end - start) for start, end in windows)
    if len(tracked) >= 2:
        return max(0.0, (tracked[-1].timestamp_seconds or 0.0) - (tracked[0].timestamp_seconds or 0.0))
    return 0.0


def _in_windows(timestamp: float, windows: list[tuple[float, float]] | None) -> bool:
    """判断时间戳是否落在任一有效窗口内；无窗口时视为全部有效。"""
    if not windows:
        return True
    return any(start <= timestamp < end for start, end in windows)


def _feedback(
    avg_distance_m: float,
    reference_m: float,
    nvz_occupancy: float,
    *,
    own_side_known: bool,
) -> ZoneFeedback:
    """按平均站位距厨房线相对参考基准生成描述性反馈档位与文案。

    文案只陈述站位与 NVZ 占用事实（design D4：删除"网前控制优秀/良好/不足"能力评价），
    参考基准是硬编码常数（设计选型 A），文案强制标注"参考基准"而非真实同水平规范数据。
    own_side_known=False 时标注口径受限（回退最近厨房线估算）。
    """
    nvz_percent = nvz_occupancy * 100
    basis_note = "" if own_side_known else "（按最近厨房线估算，未能确定所属半场）"
    if avg_distance_m <= reference_m:
        return ZoneFeedback(
            level="near_line",
            summary=(
                f"平均站位较接近厨房线（{avg_distance_m:.1f}m，参考基准 {reference_m:.1f}m），"
                f"非截击区占用率 {nvz_percent:.0f}%{basis_note}。"
            ),
        )
    if avg_distance_m <= reference_m * 1.5:
        return ZoneFeedback(
            level="moderate",
            summary=(
                f"平均站位距厨房线 {avg_distance_m:.1f}m，略高于参考基准 {reference_m:.1f}m，"
                f"非截击区占用率 {nvz_percent:.0f}%{basis_note}。"
            ),
        )
    return ZoneFeedback(
        level="deep",
        summary=(
            f"平均站位距厨房线 {avg_distance_m:.1f}m，高于参考基准 {reference_m:.1f}m，"
            f"非截击区占用率 {nvz_percent:.0f}%{basis_note}。"
        ),
    )


def _group_points_by_label(points: list[Any]) -> dict[str, list[Any]]:
    grouped: dict[str, list[Any]] = {}
    for point in points:
        label = point.label or "Player"
        grouped.setdefault(label, []).append(point)
    return grouped
