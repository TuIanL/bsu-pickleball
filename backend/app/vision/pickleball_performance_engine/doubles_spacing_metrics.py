from __future__ import annotations

from collections import defaultdict
from math import hypot

from app.schemas.metrics import DoublesSpacingSample, DoublesSpacingSummary
from app.schemas.tracking import ProjectedTrackPoint
from app.vision.pickleball_performance_engine.trajectory_metrics import group_tracks


def doubles_spacing(points: list[ProjectedTrackPoint]) -> list[DoublesSpacingSummary]:
    tracks = group_tracks(points)
    by_side: dict[str, list[str]] = defaultdict(list)

    for track_id, track_points in tracks.items():
        side = track_points[0].side if track_points else "unknown"
        if side != "unknown":
            by_side[side].append(track_id)

    summaries: list[DoublesSpacingSummary] = []
    for track_ids in by_side.values():
        if len(track_ids) < 2:
            continue
        for first_index, first_id in enumerate(track_ids):
            for second_id in track_ids[first_index + 1 :]:
                samples = _spacing_samples(tracks[first_id], tracks[second_id])
                if not samples:
                    continue
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
    by_frame_b = {point.frame_index: point for point in track_b}
    samples: list[DoublesSpacingSample] = []

    for point_a in track_a:
        point_b = by_frame_b.get(point_a.frame_index)
        if point_b is None:
            continue
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
