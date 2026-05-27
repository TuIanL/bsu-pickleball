"""Metric input preparation for standard-court performance calculations."""

from __future__ import annotations

from app.schemas.tracking import ProjectedTrackPoint
from app.vision.courtvision_calibration_engine.court_geometry import StandardPickleballCourt, standard_court


def standard_court_metric_points(
    points: list[ProjectedTrackPoint],
    court: StandardPickleballCourt | None = None,
) -> list[ProjectedTrackPoint]:
    court = court or standard_court()
    return [point for point in points if court.is_in_bounds(point.court_point.x, point.court_point.y)]
