import pytest

from app.schemas.tracking import ProjectedTrackPoint
from app.vision.pickleball_performance_engine.doubles_spacing_metrics import doubles_spacing
from app.vision.pickleball_performance_engine.heatmap_generator import generate_heatmap
from app.vision.pickleball_performance_engine.speed_metrics import speed_summaries
from app.vision.pickleball_performance_engine.trajectory_metrics import total_distances
from app.vision.pickleball_performance_engine.zone_metrics import kitchen_dwell


def point(track_id, frame, time, x, y, side="near"):
    return ProjectedTrackPoint(
        frame_index=frame,
        timestamp_seconds=time,
        track_id=track_id,
        image_point={"x": x * 10, "y": y * 10},
        confidence=1,
        side=side,
        court_point={"x": x, "y": y},
    )


def test_distance_and_speed_metrics():
    points = [point("p1", 0, 0, 0, 0), point("p1", 1, 1, 3, 4), point("p1", 2, 2, 6, 8)]

    distances = total_distances(points)
    speeds = speed_summaries(points)

    assert distances[0].distance_ft == pytest.approx(10)
    assert speeds[0].average_speed_ft_per_s == pytest.approx(5)
    assert speeds[0].max_speed_ft_per_s == pytest.approx(5)


def test_kitchen_dwell_heatmap_and_doubles_spacing():
    points = [
        point("a", 0, 0, 5, 14),
        point("a", 1, 1, 5, 16),
        point("a", 2, 2, 5, 18),
        point("b", 0, 0, 15, 14),
        point("b", 1, 1, 15, 16),
        point("b", 2, 2, 15, 18),
    ]

    dwell = kitchen_dwell(points)
    heatmap = generate_heatmap(points, rows=4, cols=2)
    spacing = doubles_spacing(points)

    assert dwell[0].kitchen_frames == 2
    assert dwell[0].kitchen_seconds == pytest.approx(1)
    assert sum(cell.count for cell in heatmap.cells) == 6
    assert spacing[0].average_spacing_ft == pytest.approx(10)
