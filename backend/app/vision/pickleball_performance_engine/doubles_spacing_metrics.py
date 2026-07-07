"""双打间距指标 —— 计算同一侧两名球员之间的站位间距变化。"""

from __future__ import annotations

# defaultdict：按“场地方位（side）”分组收集 track_id 列表。
from collections import defaultdict
# hypot：计算同一帧两名球员之间的欧几里得距离（站位间距）。
from math import hypot

# DoublesSpacingSample：某一帧的间距采样（时间戳、双方 track_id、间距英尺）。
# DoublesSpacingSummary：一对球员（组合）的间距汇总（平均/最小/最大间距 + 全部采样）。
from app.schemas.metrics import DoublesSpacingSample, DoublesSpacingSummary
# ProjectedTrackPoint：投影到标准球场坐标系（英尺）的轨迹点。
from app.schemas.tracking import ProjectedTrackPoint
# group_tracks：按球员分组并排序轨迹点的工具函数。
from app.vision.pickleball_performance_engine.trajectory_metrics import group_tracks


def doubles_spacing(points: list[ProjectedTrackPoint]) -> list[DoublesSpacingSummary]:
    """计算双打中“同一侧”每对球员之间的站位间距汇总。

    只对同一 side（同队同侧）且至少有 2 条轨迹的球员做两两配对；
    对每一对，按帧对齐计算间距，再汇总平均/最小/最大间距。
    """
    # 先按球员分组（按 track_id），保证后续按帧对齐。
    tracks = group_tracks(points)
    # 按场地方位（side）收集 track_id 列表，例如 {"left": [...], "right": [...]}。
    by_side: dict[str, list[str]] = defaultdict(list)

    for track_id, track_points in tracks.items():
        # 取该轨迹的第一帧判定其所在方位；无轨迹则记为 "unknown"。
        side = track_points[0].side if track_points else "unknown"
        # 只把已知方位的球员归入对应一侧（unknown 不参与配对）。
        if side != "unknown":
            by_side[side].append(track_id)

    summaries: list[DoublesSpacingSummary] = []
    # 对每个方位下的球员列表做两两组合。
    for track_ids in by_side.values():
        # 少于 2 人无法构成配对，跳过。
        if len(track_ids) < 2:
            continue
        # 用双循环枚举所有 (first, second) 无序对，避免重复。
        for first_index, first_id in enumerate(track_ids):
            for second_id in track_ids[first_index + 1 :]:
                # 计算这对球员逐帧的间距采样。
                samples = _spacing_samples(tracks[first_id], tracks[second_id])
                if not samples:
                    continue
                # 汇总这一对的间距统计。
                distances = [sample.distance_ft for sample in samples]
                summaries.append(
                    DoublesSpacingSummary(
                        pair=(first_id, second_id),
                        average_spacing_ft=sum(distances) / len(distances),
                        min_spacing_ft=min(distances),
                        max_spacing_ft=max(distances),
                        samples=samples,
                    )
                )
    return summaries


def _spacing_samples(
    track_a: list[ProjectedTrackPoint],
    track_b: list[ProjectedTrackPoint],
) -> list[DoublesSpacingSample]:
    """对两条球员轨迹按帧对齐，计算每一共有帧的两人间距。

    返回按 track_a 遍历顺序的间距采样列表（仅包含两人同时出现的帧）。
    """
    # 把 track_b 建成 {帧序号: 轨迹点} 的索引，便于 O(1) 查找同帧点。
    by_frame_b = {point.frame_index: point for point in track_b}
    samples: list[DoublesSpacingSample] = []

    for point_a in track_a:
        # 找到 track_b 在同一帧的点；若该帧 track_b 缺失则跳过。
        point_b = by_frame_b.get(point_a.frame_index)
        if point_b is None:
            continue
        # 计算同一帧两名球员在球场坐标系下的直线距离（英尺）。
        distance = hypot(
            point_a.court_point.x - point_b.court_point.x,
            point_a.court_point.y - point_b.court_point.y,
        )
        samples.append(
            DoublesSpacingSample(
                timestamp_seconds=point_a.timestamp_seconds,
                track_a=point_a.track_id,
                track_b=point_b.track_id,
                distance_ft=distance,
            )
        )

    return samples
