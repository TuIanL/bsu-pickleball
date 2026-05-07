from __future__ import annotations

from app.schemas.calibration import CourtPoint2D
from app.schemas.tracking import ImageTrackPoint, ProjectedTrackPoint
from app.vision.courtvision_calibration_engine.homography import project_point


def project_track_points(
    track_points: list[ImageTrackPoint],
    homography: list[list[float]],
) -> list[ProjectedTrackPoint]:
    projected: list[ProjectedTrackPoint] = []

    for point in track_points:
        x, y = project_point(homography, (point.image_point.x, point.image_point.y))
        projected.append(
            ProjectedTrackPoint(
                **point.model_dump(),
                court_point=CourtPoint2D(x=x, y=y),
            )
        )

    return projected
