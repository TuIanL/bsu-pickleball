"""Ball candidate filtering and trajectory continuity tracking."""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from math import hypot

import numpy as np

from app.vision.pickleball_game_analysis.ball_detector_protocol import BallDetectorProtocol
from app.vision.pickleball_game_analysis.court_adapter import BallCourtAdapter
from app.vision.pickleball_game_analysis.schemas import BallCandidate, BallFrameSample, Point2D


@dataclass(frozen=True)
class BallTrackerConfig:
    confidence: float = 0.18
    trajectory_length: int = 30
    max_jump_pixels: float = 220.0
    prediction_gate_pixels: float = 260.0
    max_missing_frames: int = 5
    roi_padding_ratio: float = 0.08
    max_box_area_ratio: float = 0.004
    max_aspect_ratio: float = 4.0


class BallTracker:
    def __init__(
        self,
        detector: BallDetectorProtocol,
        config: BallTrackerConfig | None = None,
        court_adapter: BallCourtAdapter | None = None,
    ) -> None:
        self.detector = detector
        self.config = config or BallTrackerConfig()
        self.court_adapter = court_adapter or BallCourtAdapter()
        self.trajectory: deque[Point2D] = deque(maxlen=self.config.trajectory_length)
        self.last_valid_position: Point2D | None = None
        self.missing_frames = 0

    def update(
        self,
        frame: np.ndarray,
        frame_index: int,
        timestamp_sec: float,
        roi_corners: tuple[tuple[int, int], tuple[int, int]] | None = None,
        homography: Sequence[Sequence[float]] | None = None,
    ) -> BallFrameSample:
        raw_candidates = self.detector.detect(frame, conf=self.config.confidence)
        candidates, reject_reasons = self._extract_candidates(raw_candidates, frame.shape, roi_corners)
        selected = self._select_candidate(candidates)
        if selected is None:
            self._record_missing_detection()
            reason = reject_reasons[0] if reject_reasons else "no_candidates"
            return self._sample(
                frame_index=frame_index,
                timestamp_sec=timestamp_sec,
                image_xy=None,
                court_xy=None,
                confidence=None,
                visible=bool(raw_candidates),
                accepted=False,
                candidate_count=len(candidates),
                reject_reason=reason,
                in_bounds=None,
            )

        point = selected.image_xy
        reject_reason = self._continuity_reject_reason(point)
        if reject_reason is not None:
            self._record_missing_detection()
            return self._sample(
                frame_index=frame_index,
                timestamp_sec=timestamp_sec,
                image_xy=point,
                court_xy=None,
                confidence=selected.confidence,
                visible=True,
                accepted=False,
                candidate_count=len(candidates),
                reject_reason=reject_reason,
                in_bounds=None,
            )

        projection = self.court_adapter.project(point, homography)
        self._append_valid_point(point)
        return self._sample(
            frame_index=frame_index,
            timestamp_sec=timestamp_sec,
            image_xy=point,
            court_xy=projection.court_xy,
            confidence=selected.confidence,
            visible=True,
            accepted=True,
            candidate_count=len(candidates),
            reject_reason=None,
            in_bounds=projection.in_bounds,
            diagnostics={"court_projection": projection.detail},
        )

    def clear(self) -> None:
        self.trajectory.clear()
        self.last_valid_position = None
        self.missing_frames = 0

    def _extract_candidates(
        self,
        candidates: Sequence[BallCandidate],
        frame_shape: Sequence[int],
        roi_corners: tuple[tuple[int, int], tuple[int, int]] | None,
    ) -> tuple[list[BallCandidate], list[str]]:
        filtered: list[BallCandidate] = []
        reject_reasons: list[str] = []
        frame_area = max(1.0, float(frame_shape[0] * frame_shape[1]))

        for candidate in candidates:
            width = candidate.width
            height = candidate.height
            area_ratio = candidate.area_ratio
            aspect_ratio = candidate.aspect_ratio
            if width is not None and height is not None:
                if width <= 0 or height <= 0:
                    reject_reasons.append("invalid_box")
                    continue
                area_ratio = area_ratio if area_ratio is not None else (float(width) * float(height)) / frame_area
                aspect_ratio = aspect_ratio if aspect_ratio is not None else max(float(width) / float(height), float(height) / float(width))
            if area_ratio is not None and area_ratio > self.config.max_box_area_ratio:
                reject_reasons.append("box_too_large")
                continue
            if aspect_ratio is not None and aspect_ratio > self.config.max_aspect_ratio:
                reject_reasons.append("aspect_ratio")
                continue
            if not self._point_in_roi(candidate.image_xy, roi_corners):
                reject_reasons.append("outside_roi")
                continue
            filtered.append(
                BallCandidate(
                    image_x=float(candidate.image_x),
                    image_y=float(candidate.image_y),
                    confidence=float(candidate.confidence),
                    width=width,
                    height=height,
                    area_ratio=area_ratio,
                    aspect_ratio=aspect_ratio,
                    diagnostics=dict(candidate.diagnostics),
                )
            )
        return filtered, reject_reasons

    def _select_candidate(self, candidates: Sequence[BallCandidate]) -> BallCandidate | None:
        if not candidates:
            return None
        if not self.trajectory:
            return max(candidates, key=lambda item: item.confidence)
        predicted = self._predict_next_position()

        def score(candidate: BallCandidate) -> float:
            distance = self._distance(candidate.image_xy, predicted)
            size_penalty = float(candidate.area_ratio or 0.0) * 4000.0
            return candidate.confidence * 1000.0 - distance * 1.4 - size_penalty

        return max(candidates, key=score)

    def _point_in_roi(
        self,
        point: Point2D,
        roi_corners: tuple[tuple[int, int], tuple[int, int]] | None,
    ) -> bool:
        if roi_corners is None:
            return True
        x1, y1 = roi_corners[0]
        x2, y2 = roi_corners[1]
        padding = int(max(abs(x2 - x1), abs(y2 - y1)) * self.config.roi_padding_ratio)
        left, right = sorted((x1, x2))
        top, bottom = sorted((y1, y2))
        return (left - padding) <= point[0] <= (right + padding) and (top - padding) <= point[1] <= (bottom + padding)

    def _continuity_reject_reason(self, point: Point2D) -> str | None:
        if not self.trajectory:
            return None
        strict_gate = self.missing_frames <= self.config.max_missing_frames
        if not strict_gate:
            return None
        jump_distance = self._distance(point, self.trajectory[-1])
        if jump_distance > self.config.max_jump_pixels:
            return "jump_distance"
        predicted_distance = self._distance(point, self._predict_next_position())
        if predicted_distance > self.config.prediction_gate_pixels:
            return "prediction_gate"
        return None

    def _predict_next_position(self) -> Point2D:
        if len(self.trajectory) < 2:
            return self.trajectory[-1]
        prev_x, prev_y = self.trajectory[-2]
        last_x, last_y = self.trajectory[-1]
        return (last_x + (last_x - prev_x), last_y + (last_y - prev_y))

    def _append_valid_point(self, point: Point2D) -> None:
        self.trajectory.append(point)
        self.last_valid_position = point
        self.missing_frames = 0

    def _record_missing_detection(self) -> None:
        self.missing_frames += 1
        if self.missing_frames > self.config.max_missing_frames:
            self.last_valid_position = None

    @staticmethod
    def _distance(point_a: Point2D, point_b: Point2D) -> float:
        return float(hypot(point_a[0] - point_b[0], point_a[1] - point_b[1]))

    @staticmethod
    def _sample(**kwargs: object) -> BallFrameSample:
        diagnostics = kwargs.pop("diagnostics", None) or {}
        return BallFrameSample(**kwargs, diagnostics=diagnostics)  # type: ignore[arg-type]
