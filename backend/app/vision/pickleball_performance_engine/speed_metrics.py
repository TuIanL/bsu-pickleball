"""速度指标计算 —— 基于相邻帧坐标差和时间间隔计算球员移动速度。"""

from __future__ import annotations

# hypot：计算相邻两帧之间的位移（勾股定理）。
from math import hypot

# SpeedSegment：单个“相邻帧速度片段”的数据模型（含起止时间、速度）。
# SpeedSummary：单名球员的速度汇总（平均、最大、全部片段列表）。
from app.schemas.metrics import SpeedSegment, SpeedSummary
# ProjectedTrackPoint：投影到标准球场坐标系（英尺）的轨迹点。
from app.schemas.tracking import ProjectedTrackPoint
# group_tracks：本包内轨迹指标模块提供的“按球员分组并排序”工具函数。
from app.vision.pickleball_performance_engine.trajectory_metrics import group_tracks


def speed_summaries(points: list[ProjectedTrackPoint]) -> list[SpeedSummary]:
    """计算每名球员的移动速度汇总。

    速度 = 相邻两帧的球场位移 / 两帧的时间间隔（单位：英尺/秒）。
    返回每个 track_id 一条 SpeedSummary（含平均速度和最大速度）。
    """
    summaries: list[SpeedSummary] = []

    # 逐名球员计算。
    for track_id, track_points in group_tracks(points).items():
        segments: list[SpeedSegment] = []  # 该球员的所有“相邻帧速度片段”。
        # 遍历相邻帧对 (前一帧, 当前帧)。
        for previous, current in zip(track_points, track_points[1:]):
            # 两帧之间的时间差（秒）。
            elapsed = current.timestamp_seconds - previous.timestamp_seconds
            # 时间差非正（时间戳异常或倒退）时跳过，避免除零或负速度。
            if elapsed <= 0:
                continue
            # 计算相邻两帧之间的球场平面位移（英尺）。
            distance = hypot(
                current.court_point.x - previous.court_point.x,
                current.court_point.y - previous.court_point.y,
            )
            # 记录这一小段的速度片段。
            segments.append(
                SpeedSegment(
                    track_id=track_id,
                    start_time=previous.timestamp_seconds,
                    end_time=current.timestamp_seconds,
                    speed_ft_per_s=distance / elapsed,
                )
            )

        # 该球员所有片段速度的平均值（无片段时记为 0.0）。
        average = sum(segment.speed_ft_per_s for segment in segments) / len(segments) if segments else 0.0
        # 该球员所有片段速度的最大值（无片段时 default=0.0）。
        maximum = max((segment.speed_ft_per_s for segment in segments), default=0.0)
        summaries.append(
            SpeedSummary(
                track_id=track_id,
                average_speed_ft_per_s=average,
                max_speed_ft_per_s=maximum,
                segments=segments,
            )
        )

    return summaries
