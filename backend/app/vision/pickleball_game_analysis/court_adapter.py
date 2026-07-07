"""Court coordinate adapter for ball image points."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.vision.courtvision_calibration_engine.court_geometry import PickleballCourtGeometry, standard_court
from app.vision.courtvision_calibration_engine.homography import HomographyError, image_to_court
from app.vision.pickleball_game_analysis.schemas import Point2D, clean_point, coordinate_system_metadata


@dataclass(frozen=True)
class CourtProjection:
    court_xy: Point2D | None
    in_bounds: bool | None
    detail: str


class BallCourtAdapter:
    """Project ball image coordinates into the project's feet-based court coordinates."""

    def __init__(self, court: PickleballCourtGeometry | None = None) -> None:
        self.court = court or standard_court()

    @property
    def coordinate_system(self) -> dict[str, object]:
        return coordinate_system_metadata(self.court.width_ft, self.court.length_ft)

    def project(
        self,
        image_xy: Sequence[float] | None,
        homography: Sequence[Sequence[float]] | None,
    ) -> CourtProjection:
        point = clean_point(image_xy)
        if point is None:
            return CourtProjection(court_xy=None, in_bounds=None, detail="missing_image_point")
        if homography is None:
            return CourtProjection(court_xy=None, in_bounds=None, detail="missing_homography")

        try:
            court_x, court_y = image_to_court(point, homography)
            court_xy = clean_point((court_x, court_y))
        except (HomographyError, ValueError, TypeError):
            return CourtProjection(court_xy=None, in_bounds=None, detail="invalid_homography")

        if court_xy is None:
            return CourtProjection(court_xy=None, in_bounds=None, detail="invalid_court_point")
        in_bounds = self.court.is_in_bounds(court_xy[0], court_xy[1])
        return CourtProjection(court_xy=court_xy, in_bounds=in_bounds, detail="projected")
