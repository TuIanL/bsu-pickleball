from __future__ import annotations

from math import hypot

from app.schemas.metrics import SpeedSegment, SpeedSummary
from app.schemas.tracking import ProjectedTrackPoint
from app.vision.pickleball_performance_engine.trajectory_metrics import group_tracks


def speed_summaries(points: list[ProjectedTrackPoint]) -> list[SpeedSummary]:
    summaries: list[SpeedSummary] = []

    for track_id, track_points in group_tracks(points).items():
        segments: list[SpeedSegment] = []
        for previous, current in zip(track_points, track_points[1:]):
            elapsed = current.timestamp_seconds - previous.timestamp_seconds
            if elapsed <= 0:
                continue
            distance = hypot(
                current.court_point.x - previous.court_point.x,
                current.court_point.y - previous.court_point.y,
            )
            segments.append(
                SpeedSegment(
                    track_id=track_id,
                    start_time=previous.timestamp_seconds,
                    end_time=current.timestamp_seconds,
                    speed_ft_per_s=distance / elapsed,
                )
            )

        average = sum(segment.speed_ft_per_s for segment in segments) / len(segments) if segments else 0.0
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
