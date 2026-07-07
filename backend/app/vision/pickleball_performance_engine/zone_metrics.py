"""区域指标计算 —— 统计球员在厨房区（非截击区）的停留帧数和时间。"""

from __future__ import annotations

# ZoneDwellMetric：单名球员在厨房区的停留指标（停留帧数、停留秒数）数据模型。
from app.schemas.metrics import ZoneDwellMetric
# ProjectedTrackPoint：投影到标准球场坐标系（英尺）的轨迹点。
from app.schemas.tracking import ProjectedTrackPoint
# StandardPickleballCourt / standard_court：标准球场几何定义，提供厨房区判定等方法。
from app.vision.courtvision_calibration_engine.court_geometry import StandardPickleballCourt, standard_court
# group_tracks：按球员分组并排序轨迹点的工具函数。
from app.vision.pickleball_performance_engine.trajectory_metrics import group_tracks


def kitchen_dwell(
    points: list[ProjectedTrackPoint],
    court: StandardPickleballCourt | None = None,
) -> list[ZoneDwellMetric]:
    """统计每名球员在厨房区（kitchen / non-volley zone）的停留情况。

    - kitchen_frames：该球员落在厨房区内的轨迹帧数。
    - kitchen_seconds：该球员在厨房区内累计停留的时间（秒），按相邻帧时间差累加。
    若不传入 court，则使用标准球场尺寸作为判定基准。
    """
    # 未显式传入球场时，回退到标准球场定义。
    court = court or standard_court()
    metrics: list[ZoneDwellMetric] = []

    for track_id, track_points in group_tracks(points).items():
        # 统计落在厨房区内的轨迹点数量（即“停留帧数”）。
        kitchen_points = [point for point in track_points if court.is_in_kitchen(point.court_point.x, point.court_point.y)]
        seconds = 0.0
        # 遍历相邻帧对，累加“前一帧在厨房区内”的时间差，得到停留秒数。
        for previous, current in zip(track_points, track_points[1:]):
            if court.is_in_kitchen(previous.court_point.x, previous.court_point.y):
                seconds += max(0.0, current.timestamp_seconds - previous.timestamp_seconds)
        metrics.append(
            ZoneDwellMetric(
                track_id=track_id,
                kitchen_frames=len(kitchen_points),
                kitchen_seconds=seconds,
            )
        )

    return metrics
