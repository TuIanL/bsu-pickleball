"""轨迹指标计算 —— 按球员分组轨迹点并计算累计移动距离。"""

from __future__ import annotations

# defaultdict：当访问不存在的键时自动创建空列表，方便按 track_id 收集轨迹点。
from collections import defaultdict

# hypot：计算两点间的欧几里得距离（勾股定理），用于求球场坐标系下的位移量。
from math import hypot

# DistanceMetric：单名球员累计移动距离的指标数据模型（见 schemas/metrics.py）。
from app.schemas.metrics import DistanceMetric

# ProjectedTrackPoint：已经投影到标准球场坐标系（单位：英尺）的轨迹点。
from app.schemas.tracking import ProjectedTrackPoint


def group_tracks(points: list[ProjectedTrackPoint]) -> dict[str, list[ProjectedTrackPoint]]:
    """将一维的轨迹点列表按球员（track_id）分组，并对每组按时间/帧序排序。

    返回：{ track_id: [按时间升序排列的该球员轨迹点列表], ... }
    """
    # 用 defaultdict 按 track_id 把点归类。
    tracks: dict[str, list[ProjectedTrackPoint]] = defaultdict(list)
    for point in points:
        tracks[point.track_id].append(point)
    # 构造返回字典的同时，对每名球员的轨迹点按 (时间戳, 帧序号) 升序排序，
    # 保证后续按相邻帧计算距离/速度时顺序正确。
    return {
        track_id: sorted(items, key=lambda item: (item.timestamp_seconds, item.frame_index))
        for track_id, items in tracks.items()
    }


def total_distances(points: list[ProjectedTrackPoint]) -> list[DistanceMetric]:
    """计算每名球员在整个视频中的累计移动距离（单位：英尺）。

    思路：把同一名球员相邻两帧的球场坐标用勾股定理求位移，全部求和。
    """
    metrics: list[DistanceMetric] = []
    # 逐名球员处理。
    for track_id, track_points in group_tracks(points).items():
        distance = 0.0
        # 用 zip 把轨迹点错开一位，得到 (前一帧, 当前帧) 的相邻点对。
        for previous, current in zip(track_points, track_points[1:], strict=False):
            # 累加相邻两帧之间的球场平面位移。
            distance += hypot(
                current.court_point.x - previous.court_point.x,
                current.court_point.y - previous.court_point.y,
            )
        # 记录该球员的总移动距离。
        metrics.append(DistanceMetric(track_id=track_id, distance_ft=distance))
    return metrics
