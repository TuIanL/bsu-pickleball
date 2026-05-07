from __future__ import annotations

from collections import defaultdict
from math import hypot

from app.schemas.metrics import DistanceMetric
from app.schemas.tracking import ProjectedTrackPoint


def group_tracks(points: list[ProjectedTrackPoint]) -> dict[str, list[ProjectedTrackPoint]]:
    tracks: dict[str, list[ProjectedTrackPoint]] = defaultdict(list)
    for point in points:
        tracks[point.track_id].append(point)
    return {track_id: sorted(items, key=lambda item: (item.timestamp_seconds, item.frame_index)) for track_id, items in tracks.items()}


def total_distances(points: list[ProjectedTrackPoint]) -> list[DistanceMetric]:
    metrics: list[DistanceMetric] = []
    for track_id, track_points in group_tracks(points).items():
        distance = 0.0
        for previous, current in zip(track_points, track_points[1:]):
            distance += hypot(
                current.court_point.x - previous.court_point.x,
                current.court_point.y - previous.court_point.y,
            )
        metrics.append(DistanceMetric(track_id=track_id, distance_ft=distance))
    return metrics
