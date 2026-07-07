"""Court-view matching, segment state, and calibration-aware ROI helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Sequence

from app.schemas.court_view import (
    CourtViewFrameSample,
    CourtViewRoiArtifact,
    CourtViewSegment,
    CourtViewThresholds,
    DetectionRoiArtifact,
    DetectionRoiBounds,
)
from app.schemas.tracking import Detection

PointLike = tuple[float, float] | list[float]


@dataclass(frozen=True)
class RoiComputationConfig:
    padding_ratio: float = 0.15
    min_padding_px: int = 24


def compute_expanded_detection_roi(
    image_points: Sequence[PointLike] | None,
    frame_width: int,
    frame_height: int,
    *,
    calibration_id: str | None = None,
    config: RoiComputationConfig | None = None,
) -> DetectionRoiArtifact:
    config = config or RoiComputationConfig()
    if frame_width <= 0 or frame_height <= 0:
        return DetectionRoiArtifact(
            status="unavailable",
            detail="缺少有效源视频 frame dimensions，无法推导 detection ROI",
            calibration_id=calibration_id,
            diagnostics={"reason": "invalid_frame_dimensions", "frame_width": frame_width, "frame_height": frame_height},
        )
    if image_points is None or len(image_points) < 4:
        return DetectionRoiArtifact(
            status="unavailable",
            detail="缺少标定四角图像点，使用全帧 detection fallback",
            calibration_id=calibration_id,
            diagnostics={"reason": "missing_calibration_keypoints"},
        )

    try:
        points = [(float(point[0]), float(point[1])) for point in image_points]
    except (TypeError, ValueError, IndexError):
        return DetectionRoiArtifact(
            status="unavailable",
            detail="标定四角图像点格式无效，使用全帧 detection fallback",
            calibration_id=calibration_id,
            diagnostics={"reason": "invalid_calibration_keypoints"},
        )
    if not all(isfinite(x) and isfinite(y) for x, y in points):
        return DetectionRoiArtifact(
            status="unavailable",
            detail="标定四角图像点包含非有限数值，使用全帧 detection fallback",
            calibration_id=calibration_id,
            diagnostics={"reason": "non_finite_calibration_keypoints"},
        )

    min_x = min(x for x, _ in points)
    max_x = max(x for x, _ in points)
    court_width = max_x - min_x
    if court_width <= 1:
        return DetectionRoiArtifact(
            status="unavailable",
            detail="标定四角图像点几何异常，无法推导 detection ROI",
            calibration_id=calibration_id,
            diagnostics={"reason": "degenerate_court_width", "court_width": court_width},
        )

    padding = max(config.min_padding_px, int(round(court_width * config.padding_ratio)))
    raw_x1 = int(round(min_x)) - padding
    raw_x2 = int(round(max_x)) + padding
    x1 = max(0, raw_x1)
    x2 = min(frame_width - 1, raw_x2)
    y1 = 0
    y2 = frame_height - 1
    if x2 <= x1:
        return DetectionRoiArtifact(
            status="unavailable",
            detail="推导的 detection ROI 宽度无效，使用全帧 detection fallback",
            calibration_id=calibration_id,
            diagnostics={"reason": "invalid_roi_width", "x1": x1, "x2": x2},
        )

    clipped = raw_x1 < 0 or raw_x2 > frame_width - 1
    return DetectionRoiArtifact(
        status="available",
        detail="已从标定四角图像点推导 detection ROI",
        calibration_id=calibration_id,
        source="calibration_keypoints",
        bounds=DetectionRoiBounds(
            x1=x1,
            y1=y1,
            x2=x2,
            y2=y2,
            source_width=frame_width,
            source_height=frame_height,
            padding_ratio=config.padding_ratio,
            clipped_to_frame=clipped,
        ),
        diagnostics={
            "reason": "available",
            "court_image_width": round(float(court_width), 3),
            "padding_px": padding,
            "clipped_to_frame": clipped,
        },
    )


def filter_detections_to_roi(
    detections: Sequence[Detection],
    roi: DetectionRoiArtifact | None,
) -> tuple[list[Detection], int]:
    if roi is None or roi.status != "available" or roi.bounds is None:
        return list(detections), 0
    bounds = roi.bounds
    if bounds.x1 <= 0 and bounds.y1 <= 0 and bounds.x2 >= bounds.source_width - 1 and bounds.y2 >= bounds.source_height - 1:
        return list(detections), 0
    kept: list[Detection] = []
    filtered = 0
    for detection in detections:
        x1, y1, x2, y2 = detection.bbox
        center_x = (float(x1) + float(x2)) / 2.0
        foot_y = float(y2)
        if bounds.x1 <= center_x <= bounds.x2 and bounds.y1 <= foot_y <= bounds.y2:
            kept.append(detection)
        else:
            filtered += 1
    return kept, filtered


class CourtViewFrameScorer:
    def __init__(self, match_width: int = 320) -> None:
        self.match_width = max(1, int(match_width))
        self.reference_gray = None
        self.available = False
        self.detail = "未初始化 court-view reference"

    def initialize(self, frame: object) -> None:
        try:
            import cv2  # type: ignore
        except ImportError:
            self.available = False
            self.detail = "OpenCV 不可用，court-view gate skipped"
            return
        try:
            self.reference_gray = self._prepare_gray(frame, cv2)
        except Exception as exc:  # noqa: BLE001
            self.reference_gray = None
            self.available = False
            self.detail = f"无法初始化 court-view reference：{exc}"
            return
        self.available = True
        self.detail = "已使用首个处理帧初始化 court-view reference"

    def score(self, frame: object) -> float | None:
        if not self.available or self.reference_gray is None:
            return None
        try:
            import cv2  # type: ignore
        except ImportError:
            return None
        try:
            gray = self._prepare_gray(frame, cv2)
            result = cv2.matchTemplate(gray, self.reference_gray, cv2.TM_CCOEFF_NORMED)
            return self._clamp_score(float(result.max()))
        except Exception:
            return None

    @staticmethod
    def _clamp_score(score: float) -> float:
        return max(0.0, min(1.0, score))

    def _prepare_gray(self, frame: object, cv2):
        import numpy as np

        array = np.asarray(frame)
        if array.ndim == 3:
            gray = cv2.cvtColor(array, cv2.COLOR_BGR2GRAY)
        else:
            gray = array
        if gray.shape[1] > self.match_width:
            scale = self.match_width / gray.shape[1]
            height = max(1, int(round(gray.shape[0] * scale)))
            gray = cv2.resize(gray, (self.match_width, height), interpolation=cv2.INTER_AREA)
        return gray


@dataclass
class CourtViewStateMachine:
    thresholds: CourtViewThresholds
    segments: list[CourtViewSegment] = field(default_factory=list)
    court_view_frame_count: int = 0
    non_court_view_frame_count: int = 0
    gated_frame_count: int = 0
    _consecutive_court: int = 0
    _consecutive_non_court: int = 0
    _active: bool = False
    _active_start_frame: int | None = None
    _active_start_timestamp: float | None = None
    _active_scores: list[float] = field(default_factory=list)
    _active_low_score_count: int = 0

    def update(self, frame_index: int, timestamp: float, score: float | None) -> CourtViewFrameSample:
        if score is None:
            return CourtViewFrameSample(
                frame_index=frame_index,
                timestamp_seconds=timestamp,
                score=None,
                is_court_view=None,
                reason="gate_unavailable",
            )
        score = CourtViewFrameScorer._clamp_score(float(score))

        is_court = score >= self.thresholds.match_threshold
        if is_court:
            self.court_view_frame_count += 1
            self._consecutive_court += 1
            self._consecutive_non_court = 0
            if self._active:
                self._active_scores.append(score)
            if not self._active and self._consecutive_court >= self.thresholds.start_frames:
                self._active = True
                self._active_start_frame = max(0, frame_index - self.thresholds.start_frames + 1)
                self._active_start_timestamp = max(0.0, timestamp)
                self._active_scores = [score]
                self._active_low_score_count = 0
            reason = "court_view"
        else:
            self.non_court_view_frame_count += 1
            self._consecutive_non_court += 1
            self._consecutive_court = 0
            if self._active:
                self._active_low_score_count += 1
                self._active_scores.append(score)
                if self._consecutive_non_court >= self.thresholds.end_frames:
                    end_frame = max(self._active_start_frame or 0, frame_index - self.thresholds.end_frames)
                    self._close_segment(end_frame, timestamp, "consecutive_non_court_frames")
            if self.thresholds.skip_non_court_frames and not self.thresholds.diagnostic_only:
                self.gated_frame_count += 1
                reason = "gated_non_court_view"
            else:
                reason = "diagnostic_only"

        return CourtViewFrameSample(
            frame_index=frame_index,
            timestamp_seconds=timestamp,
            score=round(float(score), 4),
            is_court_view=is_court,
            reason=reason,
        )

    def finish(self, last_frame_index: int | None = None, last_timestamp: float | None = None) -> None:
        if self._active:
            self._close_segment(
                last_frame_index if last_frame_index is not None else self._active_start_frame or 0,
                last_timestamp if last_timestamp is not None else self._active_start_timestamp or 0.0,
                "end_of_video",
            )

    def _close_segment(self, end_frame: int, end_timestamp: float, end_reason: str) -> None:
        start_frame = self._active_start_frame if self._active_start_frame is not None else end_frame
        start_timestamp = self._active_start_timestamp if self._active_start_timestamp is not None else end_timestamp
        duration = max(0.0, float(end_timestamp) - float(start_timestamp))
        average_score = sum(self._active_scores) / len(self._active_scores) if self._active_scores else None
        self.segments.append(
            CourtViewSegment(
                id=f"court-view-{len(self.segments) + 1}",
                start_frame_index=int(start_frame),
                end_frame_index=int(max(end_frame, start_frame)),
                start_timestamp_seconds=round(float(start_timestamp), 6),
                end_timestamp_seconds=round(float(max(end_timestamp, start_timestamp)), 6),
                duration_seconds=round(duration, 6),
                start_reason="consecutive_court_view_frames",
                end_reason=end_reason,
                low_score_frame_count=self._active_low_score_count,
                average_score=round(float(average_score), 4) if average_score is not None else None,
            )
        )
        self._active = False
        self._active_start_frame = None
        self._active_start_timestamp = None
        self._active_scores = []
        self._active_low_score_count = 0


def build_court_view_roi_artifact(
    *,
    job_id: str,
    video_id: str | None,
    calibration_id: str | None,
    thresholds: CourtViewThresholds,
    roi: DetectionRoiArtifact,
    state_machine: CourtViewStateMachine,
    processed_frame_count: int,
    frame_samples: list[CourtViewFrameSample],
    scorer_detail: str,
    scorer_available: bool,
    roi_filtered_detection_count: int,
    full_frame_fallback_count: int,
) -> CourtViewRoiArtifact:
    if scorer_available and roi.status == "available":
        status = "available"
        detail = "court-view gate 与 detection ROI 已运行；候选片段仅表示连续球场视角，不代表完整回合"
    elif scorer_available or roi.status == "available":
        status = "partial"
        detail = "court-view gate 或 detection ROI 部分可用；候选片段仅表示连续球场视角，不代表完整回合"
    else:
        status = "unavailable"
        detail = "court-view gate 与 detection ROI 均不可用，已使用现有全帧分析降级路径"
    return CourtViewRoiArtifact(
        job_id=job_id,
        video_id=video_id,
        calibration_id=calibration_id,
        status=status,
        detail=detail,
        thresholds=thresholds,
        processed_frame_count=processed_frame_count,
        court_view_frame_count=state_machine.court_view_frame_count,
        non_court_view_frame_count=state_machine.non_court_view_frame_count,
        gated_frame_count=state_machine.gated_frame_count,
        roi_filtered_detection_count=roi_filtered_detection_count,
        full_frame_fallback_count=full_frame_fallback_count,
        candidate_segments=state_machine.segments,
        roi=roi.model_copy(
            update={
                "filtered_detection_count": roi_filtered_detection_count,
                "full_frame_fallback_count": full_frame_fallback_count,
            }
        ),
        frame_samples=frame_samples,
        diagnostics={
            "scorer_detail": scorer_detail,
            "scorer_available": scorer_available,
            "semantic_boundary": "court_view_candidates_are_not_rally_segmentation",
        },
    )
