from __future__ import annotations

from app.schemas.metrics import Heatmap, HeatmapCell
from app.schemas.tracking import ProjectedTrackPoint
from app.vision.courtvision_calibration_engine.court_geometry import StandardPickleballCourt, standard_court


def generate_heatmap(
    points: list[ProjectedTrackPoint],
    rows: int = 11,
    cols: int = 5,
    court: StandardPickleballCourt | None = None,
) -> Heatmap:
    court = court or standard_court()
    counts: dict[tuple[int, int], int] = {}

    for point in points:
        if not court.is_in_bounds(point.court_point.x, point.court_point.y):
            continue
        col = min(cols - 1, max(0, int(point.court_point.x / court.width_ft * cols)))
        row = min(rows - 1, max(0, int(point.court_point.y / court.length_ft * rows)))
        counts[(row, col)] = counts.get((row, col), 0) + 1

    cells = [HeatmapCell(row=row, col=col, count=count) for (row, col), count in sorted(counts.items())]
    return Heatmap(rows=rows, cols=cols, cells=cells)
