from __future__ import annotations

from app.schemas.tracking import BoundingBox


def estimate_footpoint(bbox: BoundingBox | tuple[float, float, float, float]) -> tuple[float, float]:
    """Estimate player footpoint as the bottom-center of a person bounding box."""

    if isinstance(bbox, BoundingBox):
        x1, y1, x2, y2 = bbox.x1, bbox.y1, bbox.x2, bbox.y2
    else:
        x1, y1, x2, y2 = bbox

    return (float(x1 + x2) / 2.0, float(y2))
