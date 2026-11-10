"""Short same-camera continuity evidence across raw tracker fragmentation."""
from math import isfinite

VERSION = "short-image-handoff.v2"


def bbox_iou(first, second):
    if not first or not second or len(first) != 4 or len(second) != 4:
        return 0.0
    if not all(isfinite(v) for v in [*first, *second]):
        return 0.0
    x1, y1, x2, y2 = first
    a, b, c, d = second
    if x2 <= x1 or y2 <= y1 or c <= a or d <= b:
        return 0.0
    intersection = max(0.0, min(x2, c)-max(x1, a))*max(0.0, min(y2, d)-max(y1, b))
    return intersection / ((x2-x1)*(y2-y1)+(c-a)*(d-b)-intersection)


def continuous_image_box(previous, current):
    """Require actual advancing source frames and near-overlapping body boxes."""
    if (previous.view_id != current.view_id or current.detection_origin != "base"
            or previous.detection_origin != "base" or current.confidence < .65
            or current.source_frame_index <= previous.source_frame_index
            or not 0 < current.take_timestamp_ms-previous.take_timestamp_ms <= 250
            or bbox_iou(previous.bbox, current.bbox) < .5):
        return False
    old, new = previous.bbox, current.bbox
    height = old[3]-old[1]
    return (abs((new[0]+new[2]-old[0]-old[2])/2) <= .25*height
            and .5 <= (new[2]-new[0])/(old[2]-old[0]) <= 2
            and .5 <= (new[3]-new[1])/height <= 2)
