"""区域指标计算 —— 统计球员在厨房区（非截击区）的停留帧数和时间。"""

from __future__ import annotations

from app.schemas.metrics import ZoneDwellMetric
from app.schemas.tracking import ProjectedTrackPoint
from app.vision.courtvision_calibration_engine.court_geometry import StandardPickleballCourt, standard_court
from app.vision.pickleball_performance_engine.trajectory_metrics import group_tracks


def kitchen_dwell(
    points: list[ProjectedTrackPoint],
    court: StandardPickleballCourt | None = None,
) -> list[ZoneDwellMetric]:
    court = court or standard_court()
    metrics: list[ZoneDwellMetric] = []

    for track_id, track_points in group_tracks(points).items():
        kitchen_points = [point for point in track_points if court.is_in_kitchen(point.court_point.x, point.court_point.y)]
        seconds = 0.0
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
