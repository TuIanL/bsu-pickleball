from __future__ import annotations

from dataclasses import dataclass

from app.schemas.tracking import Detection, Track


@dataclass
class _TrackState:
    track_id: int
    bbox: list[float]
    confidence: float
    lost_count: int = 0


class MultiObjectTracker:
    """Simple IOU tracker with a replaceable detection-in / tracks-out contract."""

    def __init__(self, iou_threshold: float = 0.3, max_lost: int = 15) -> None:
        self.iou_threshold = iou_threshold
        self.max_lost = max_lost
        self._next_track_id = 1
        self._tracks: dict[int, _TrackState] = {}

    def update(self, detections: list[Detection]) -> list[Track]:
        matched_tracks: set[int] = set()
        matched_detections: set[int] = set()
        active: list[Track] = []

        candidates: list[tuple[float, int, int]] = []
        for detection_index, detection in enumerate(detections):
            for track_id, state in self._tracks.items():
                candidates.append((_iou(detection.bbox, state.bbox), track_id, detection_index))

        candidates.sort(key=lambda item: item[0], reverse=True)
        for score, track_id, detection_index in candidates:
            if score < self.iou_threshold:
                break
            if track_id in matched_tracks or detection_index in matched_detections:
                continue
            detection = detections[detection_index]
            state = self._tracks[track_id]
            state.bbox = detection.bbox
            state.confidence = detection.confidence
            state.lost_count = 0
            matched_tracks.add(track_id)
            matched_detections.add(detection_index)
            active.append(_state_to_track(state, lost=False))

        for detection_index, detection in enumerate(detections):
            if detection_index in matched_detections:
                continue
            track_id = self._next_track_id
            self._next_track_id += 1
            state = _TrackState(track_id=track_id, bbox=detection.bbox, confidence=detection.confidence)
            self._tracks[track_id] = state
            matched_tracks.add(track_id)
            active.append(_state_to_track(state, lost=False))

        for track_id in list(self._tracks):
            if track_id in matched_tracks:
                continue
            state = self._tracks[track_id]
            state.lost_count += 1
            if state.lost_count > self.max_lost:
                del self._tracks[track_id]

        active.sort(key=lambda track: track.track_id)
        return active


class EmptyTracker:
    def update(self, detections: list[Detection]) -> list[Track]:
        return []


def _state_to_track(state: _TrackState, lost: bool) -> Track:
    return Track(track_id=state.track_id, bbox=state.bbox, confidence=state.confidence, lost=lost)


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

    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - intersection
    if union <= 0:
        return 0.0
    return intersection / union


SimpleDetectionTracker = MultiObjectTracker
