from __future__ import annotations

from math import hypot

from app.schemas.ball import BallOverlayFrame, BallTrajectoryPoint
from app.schemas.multitarget import MultiTargetDetection, bbox_center


class BallTrajectoryBuilder:
    def __init__(
        self,
        max_gap_frames: int = 5,
        max_speed_px_per_frame: float = 180.0,
        min_repair_confidence: float = 0.2,
    ) -> None:
        self.max_gap_frames = max(0, int(max_gap_frames))
        self.max_speed_px_per_frame = max(1.0, float(max_speed_px_per_frame))
        self.min_repair_confidence = min(max(min_repair_confidence, 0.0), 1.0)

    def build(
        self,
        detections: list[MultiTargetDetection],
    ) -> tuple[list[BallOverlayFrame], dict[str, int]]:
        selected = self._select_primary_candidates(detections)
        diagnostics = {
            "raw_ball_detections": len(detections),
            "observed_points": len(selected),
            "repaired_points": 0,
            "segments": 0,
            "unresolved_gaps": 0,
            "implausible_candidates": max(0, len(detections) - len(selected)),
        }
        if not selected:
            return ([], diagnostics)

        points: list[BallTrajectoryPoint] = []
        previous_point: BallTrajectoryPoint | None = None
        previous_detection: MultiTargetDetection | None = None
        segment_id = 1

        for detection in selected:
            current_point = self._observed_point(detection, segment_id)
            if previous_point is not None and previous_detection is not None:
                gap = detection.frame_index - previous_point.frame_index
                if gap > 1:
                    can_repair = gap - 1 <= self.max_gap_frames and self._plausible_gap(previous_detection, detection, gap)
                    if can_repair:
                        repaired = self._repair_gap(previous_point, current_point, gap)
                        diagnostics["repaired_points"] += len(repaired)
                        points.extend(repaired)
                    else:
                        diagnostics["unresolved_gaps"] += 1
                        segment_id += 1
                        current_point.segment_id = segment_id
            points.append(current_point)
            previous_point = current_point
            previous_detection = detection

        diagnostics["segments"] = len({point.segment_id for point in points})
        frames = [
            BallOverlayFrame(
                frame_index=point.frame_index,
                timestamp_seconds=point.timestamp_seconds,
                points=[point],
            )
            for point in sorted(points, key=lambda item: (item.frame_index, item.timestamp_seconds, item.source))
        ]
        return (frames, diagnostics)

    def _select_primary_candidates(self, detections: list[MultiTargetDetection]) -> list[MultiTargetDetection]:
        by_frame: dict[int, list[MultiTargetDetection]] = {}
        for detection in detections:
            if detection.class_name != "ball":
                continue
            by_frame.setdefault(detection.frame_index, []).append(detection)

        selected: list[MultiTargetDetection] = []
        previous: MultiTargetDetection | None = None
        for frame_index in sorted(by_frame):
            candidates = sorted(by_frame[frame_index], key=lambda item: item.confidence, reverse=True)
            candidate = candidates[0]
            if previous is not None:
                gap = max(1, candidate.frame_index - previous.frame_index)
                if not self._plausible_gap(previous, candidate, gap):
                    plausible = [item for item in candidates[1:] if self._plausible_gap(previous, item, max(1, item.frame_index - previous.frame_index))]
                    if not plausible:
                        previous = candidate
                        selected.append(candidate)
                        continue
                    candidate = plausible[0]
            selected.append(candidate)
            previous = candidate
        return selected

    def _observed_point(self, detection: MultiTargetDetection, segment_id: int) -> BallTrajectoryPoint:
        return BallTrajectoryPoint(
            frame_index=detection.frame_index,
            timestamp_seconds=detection.timestamp_seconds,
            image_point=bbox_center(detection.bbox),
            confidence=detection.confidence,
            source="observed",
            segment_id=segment_id,
            bbox=detection.bbox,
        )

    def _repair_gap(
        self,
        previous: BallTrajectoryPoint,
        current: BallTrajectoryPoint,
        gap: int,
    ) -> list[BallTrajectoryPoint]:
        repaired: list[BallTrajectoryPoint] = []
        for offset in range(1, gap):
            ratio = offset / gap
            frame_index = previous.frame_index + offset
            timestamp = previous.timestamp_seconds + ((current.timestamp_seconds - previous.timestamp_seconds) * ratio)
            x = previous.image_point[0] + ((current.image_point[0] - previous.image_point[0]) * ratio)
            y = previous.image_point[1] + ((current.image_point[1] - previous.image_point[1]) * ratio)
            confidence = max(
                self.min_repair_confidence,
                min(previous.confidence, current.confidence) * (1.0 - (0.12 * offset)),
            )
            repaired.append(
                BallTrajectoryPoint(
                    frame_index=frame_index,
                    timestamp_seconds=timestamp,
                    image_point=[x, y],
                    confidence=confidence,
                    source="repaired",
                    segment_id=previous.segment_id,
                )
            )
        return repaired

    def _plausible_gap(
        self,
        previous: MultiTargetDetection,
        current: MultiTargetDetection,
        gap: int,
    ) -> bool:
        previous_center = bbox_center(previous.bbox)
        current_center = bbox_center(current.bbox)
        distance = hypot(current_center[0] - previous_center[0], current_center[1] - previous_center[1])
        return (distance / max(1, gap)) <= self.max_speed_px_per_frame
