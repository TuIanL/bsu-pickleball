from dataclasses import dataclass


@dataclass(frozen=True)
class CourtCoordinate:
    x: float
    y: float
    confidence: float


class CourtCalibrator:
    def map_pixel_to_court(self, x: float, y: float) -> CourtCoordinate:
        raise NotImplementedError("Court calibration will be implemented after real court-line detection is available.")
