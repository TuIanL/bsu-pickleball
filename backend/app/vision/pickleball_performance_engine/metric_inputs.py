"""Metric input preparation for standard-court performance calculations."""

from __future__ import annotations

# ProjectedTrackPoint：投影到标准球场坐标系（英尺）的轨迹点。
from app.schemas.tracking import ProjectedTrackPoint

# StandardPickleballCourt / standard_court：标准球场几何，提供边界判定。
from app.vision.courtvision_calibration_engine.court_geometry import StandardPickleballCourt, standard_court


def standard_court_metric_points(
    points: list[ProjectedTrackPoint],
    court: StandardPickleballCourt | None = None,
) -> list[ProjectedTrackPoint]:
    """筛选出落在标准球场界内的轨迹点，供后续指标计算使用。

    参数：
      points：全部投影轨迹点（可能包含界外点）。
      court：球场几何定义；缺省时使用标准球场。
    返回：仅保留 is_in_bounds 为真的轨迹点列表。
    """
    # 未显式传入球场时，使用标准球场定义。
    court = court or standard_court()
    # 列表推导式：只保留界内的点。
    return [point for point in points if court.is_in_bounds(point.court_point.x, point.court_point.y)]
