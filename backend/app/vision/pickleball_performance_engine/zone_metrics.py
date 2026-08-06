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


# 后场带深（英尺）：从每条底线向内 7 英尺为后场区。
BACKCOURT_DEPTH_FT = 7.0

# 三区展示标签（与前端区域卡片对应）。
ZONE_LABELS: dict[str, str] = {
    "kitchen": "网前区",
    "transition": "过渡区",
    "backcourt": "后场区",
}


def zone_for(
    x_ft: float,
    y_ft: float,
    court: StandardPickleballCourt | None = None,
) -> str | None:
    """返回 (x, y) 所在的三段区域名（kitchen/transition/backcourt）；球场外返回 None。

    全球场三段横带（y 从近端底线 0 → 远端底线 length）：
    - kitchen：近/远厨房线之间（网前 kitchen_depth 英尺，含球网两侧）；
    - transition：厨房线到"距底线 BACKCOURT_DEPTH_FT 英尺"之间；
    - backcourt：两条底线向内各 BACKCOURT_DEPTH_FT 英尺。
    三段划分由球场几何常量推导，不写魔法数（backcourt 深度为显式常量）。
    """
    court = court or standard_court()
    length = court.length_ft
    near_kitchen = court.net_y_ft - court.kitchen_depth_ft
    far_kitchen = court.net_y_ft + court.kitchen_depth_ft

    if near_kitchen <= y_ft <= far_kitchen:
        return "kitchen"
    if BACKCOURT_DEPTH_FT <= y_ft < near_kitchen or far_kitchen < y_ft <= length - BACKCOURT_DEPTH_FT:
        return "transition"
    if 0 <= y_ft < BACKCOURT_DEPTH_FT or length - BACKCOURT_DEPTH_FT < y_ft <= length:
        return "backcourt"
    return None
