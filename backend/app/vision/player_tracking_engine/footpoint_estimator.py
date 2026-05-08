from __future__ import annotations

from app.schemas.tracking import BoundingBox, FootpointEstimate, FootpointMethod, Track


class FootpointEstimator:
    """Estimate image-space player footpoints from tracked person boxes."""

    def __init__(self, method: FootpointMethod = "bbox_bottom_center") -> None:
        self.method = method

    def estimate(self, bbox_or_track: BoundingBox | Track | list[float] | tuple[float, float, float, float]) -> FootpointEstimate:
        if self.method != "bbox_bottom_center":
            raise NotImplementedError(f"Footpoint method is not implemented yet: {self.method}")

        x1, _, x2, y2 = _bbox_values(bbox_or_track)
        return FootpointEstimate(
            image_footpoint=[float(x1 + x2) / 2.0, float(y2)],
            method=self.method,
        )


def estimate_footpoint(bbox: BoundingBox | list[float] | tuple[float, float, float, float]) -> tuple[float, float]:
    """Compatibility wrapper returning the bbox bottom-center tuple."""

    estimate = FootpointEstimator().estimate(bbox)
    return (estimate.image_footpoint[0], estimate.image_footpoint[1])


def _bbox_values(bbox_or_track: BoundingBox | Track | list[float] | tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    if isinstance(bbox_or_track, Track):
        x1, y1, x2, y2 = bbox_or_track.bbox
    elif isinstance(bbox_or_track, BoundingBox):
        x1, y1, x2, y2 = bbox_or_track.x1, bbox_or_track.y1, bbox_or_track.x2, bbox_or_track.y2
    else:
        x1, y1, x2, y2 = bbox_or_track
    return (float(x1), float(y1), float(x2), float(y2))
