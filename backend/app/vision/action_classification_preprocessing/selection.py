"""目标球员选择策略。"""

from __future__ import annotations

from app.schemas.tracking import Detection


def select_target_detection(
    detections: list[Detection],
    *,
    strategy: str,
    frame_shape: tuple[int, ...],
    previous_bbox: list[float] | None = None,
    manual_initial_bbox: list[float] | None = None,
) -> Detection | None:
    if not detections:
        return None
    if strategy == "largest":
        return max(detections, key=lambda detection: _area(detection.bbox))
    if strategy == "near-left":
        return max(detections, key=lambda detection: _near_score(detection.bbox, frame_shape, prefer_left=True))
    if strategy == "near-right":
        return max(detections, key=lambda detection: _near_score(detection.bbox, frame_shape, prefer_left=False))
    if strategy == "track-iou":
        if previous_bbox is None:
            return max(detections, key=lambda detection: _area(detection.bbox))
        return max(detections, key=lambda detection: _iou(detection.bbox, previous_bbox))
    if strategy == "manual-initial-bbox":
        reference = previous_bbox or manual_initial_bbox
        if reference is None:
            return max(detections, key=lambda detection: _area(detection.bbox))
        return max(detections, key=lambda detection: _iou(detection.bbox, reference))
    raise ValueError(f"Unknown target selection strategy: {strategy}")


def _area(box: list[float]) -> float:
    x1, y1, x2, y2 = box
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def _near_score(box: list[float], frame_shape: tuple[int, ...], *, prefer_left: bool) -> float:
    height, width = frame_shape[:2]
    x1, y1, x2, y2 = box
    cx = (x1 + x2) / 2.0
    area = _area(box)
    horizontal = (width - cx) if prefer_left else cx
    lower = y2
    return area + horizontal * height * 0.25 + lower * height * 0.001


def _iou(a: list[float], b: list[float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    intersection = inter_w * inter_h
    union = _area(a) + _area(b) - intersection
    if union <= 0:
        return 0.0
    return intersection / union
