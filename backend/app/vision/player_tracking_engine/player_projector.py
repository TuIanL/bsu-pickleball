"""球员投影器 —— 将跟踪球员的脚点从图像像素坐标投影到球场英尺坐标。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from app.schemas.calibration import CourtPoint2D
from app.schemas.tracking import (
    FootpointEstimate,
    ImageTrackPoint,
    PlayerFramePosition,
    ProjectedTrackPoint,
    Track,
)
from app.vision.courtvision_calibration_engine.homography import image_to_court, project_point
from app.vision.player_tracking_engine.footpoint_estimator import FootpointEstimator


class PlayerProjector:
    """Project tracked player footpoints from image pixels into court feet."""

    def __init__(
        self,
        x_bounds: tuple[float, float] = (-2.0, 22.0),
        y_bounds: tuple[float, float] = (-2.0, 46.0),
        include_invalid: bool = False,
        footpoint_estimator: FootpointEstimator | None = None,
    ) -> None:
        self.x_bounds = x_bounds
        self.y_bounds = y_bounds
        self.include_invalid = include_invalid
        self.footpoint_estimator = footpoint_estimator or FootpointEstimator()

    def project(
        self,
        tracks: Sequence[Track],
        homography: Sequence[Sequence[float]],
        frame_index: int,
        timestamp: float,
        footpoints: Mapping[int, FootpointEstimate] | None = None,
    ) -> list[PlayerFramePosition]:
        positions: list[PlayerFramePosition] = []

        for track in tracks:
            footpoint = footpoints.get(track.track_id) if footpoints is not None else None
            footpoint = footpoint or self.footpoint_estimator.estimate(track)
            court_x, court_y = image_to_court(footpoint.image_footpoint, homography)
            court_position = [float(court_x), float(court_y)]
            valid = self._in_bounds(court_position)
            if not valid and not self.include_invalid:
                continue
            positions.append(
                PlayerFramePosition(
                    frame_index=frame_index,
                    timestamp=timestamp,
                    track_id=track.track_id,
                    bbox=track.bbox,
                    image_footpoint=footpoint.image_footpoint,
                    court_position=court_position,
                    confidence=track.confidence,
                    valid=valid,
                    validity="valid" if valid else "invalid",
                    footpoint_method=footpoint.method,
                )
            )

        return positions

    def _in_bounds(self, court_position: list[float]) -> bool:
        x, y = court_position
        return self.x_bounds[0] <= x <= self.x_bounds[1] and self.y_bounds[0] <= y <= self.y_bounds[1]


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
