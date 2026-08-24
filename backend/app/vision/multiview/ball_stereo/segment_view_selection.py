"""飞行段级视角质量计算与确定性主视角选择。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import hypot

import numpy as np

from app.vision.pickleball_game_analysis.schemas import TrajectoryPoint


@dataclass(frozen=True)
class ViewSegmentMetrics:
    view_id: str
    observation_coverage: float
    continuity: float
    mean_detection_confidence: float
    fit_residual_px: float
    predicted_ratio: float
    static_false_positive_ratio: float
    visibility_score: float

    def score(self) -> float:
        residual_quality = max(0.0, 1.0 - self.fit_residual_px / 45.0)
        return round(
            0.25 * self.observation_coverage
            + 0.20 * self.continuity
            + 0.14 * self.mean_detection_confidence
            + 0.14 * residual_quality
            + 0.11 * (1.0 - self.predicted_ratio)
            + 0.08 * (1.0 - self.static_false_positive_ratio)
            + 0.08 * self.visibility_score,
            4,
        )

    def to_dict(self) -> dict:
        return {**asdict(self), "score": self.score()}


@dataclass(frozen=True)
class MainViewSelection:
    primary_view_id: str
    secondary_view_id: str | None
    reason: str
    score_margin: float
    metrics_by_view: dict[str, ViewSegmentMetrics]


def compute_view_segment_metrics(view_id: str, points: list[TrajectoryPoint]) -> ViewSegmentMetrics:
    total = max(1, len(points))
    valid = [point for point in points if point.image_xy is not None]
    coverage = len(valid) / total
    longest = 0
    run = 0
    for point in points:
        if point.image_xy is not None:
            run += 1
            longest = max(longest, run)
        else:
            run = 0
    continuity = longest / total
    confidences = [float(point.confidence) for point in valid if point.confidence is not None]
    mean_confidence = float(np.mean(confidences)) if confidences else 0.0
    predicted = sum(point.source in {"predicted", "interpolated"} for point in points)
    static = sum(
        point.diagnostics.get("reject_reason") in {"stationary_candidate", "stationary_blacklisted", "static_false_positive"}
        for point in points
    )
    residual = _linear_fit_residual(valid)
    # 可见性使用已接受观测的位移与覆盖率；持续静止不会因框大而获高分。
    displacement = 0.0
    for left, right in zip(valid[:-1], valid[1:], strict=False):
        displacement += hypot(right.image_xy[0] - left.image_xy[0], right.image_xy[1] - left.image_xy[1])
    visibility = min(1.0, coverage * 0.7 + min(1.0, displacement / 120.0) * 0.3)
    return ViewSegmentMetrics(
        view_id=view_id,
        observation_coverage=round(coverage, 4),
        continuity=round(continuity, 4),
        mean_detection_confidence=round(mean_confidence, 4),
        fit_residual_px=round(residual, 4),
        predicted_ratio=round(predicted / total, 4),
        static_false_positive_ratio=round(static / total, 4),
        visibility_score=round(visibility, 4),
    )


def select_main_view(
    metrics_by_view: dict[str, ViewSegmentMetrics],
    *,
    previous_primary_view_id: str | None = None,
    hysteresis_margin: float = 0.06,
) -> MainViewSelection:
    if not metrics_by_view:
        raise ValueError("at least one view metric is required")
    ranked = sorted(metrics_by_view.values(), key=lambda metric: (-metric.score(), metric.view_id))
    best = ranked[0]
    reason = "highest_segment_quality"
    if previous_primary_view_id in metrics_by_view:
        previous = metrics_by_view[previous_primary_view_id]
        if best.view_id != previous.view_id and best.score() - previous.score() < hysteresis_margin:
            best = previous
            reason = "hysteresis_kept_previous_primary"
    secondary = next((metric.view_id for metric in ranked if metric.view_id != best.view_id), None)
    runner_up_score = metrics_by_view[secondary].score() if secondary is not None else 0.0
    return MainViewSelection(
        primary_view_id=best.view_id,
        secondary_view_id=secondary,
        reason=reason,
        score_margin=round(best.score() - runner_up_score, 4),
        metrics_by_view=metrics_by_view,
    )


def _linear_fit_residual(points: list[TrajectoryPoint]) -> float:
    if len(points) < 3:
        return 45.0
    ts = np.asarray([point.timestamp_sec for point in points], dtype=np.float64)
    ts = ts - ts[0]
    xy = np.asarray([point.image_xy for point in points], dtype=np.float64)
    design = np.column_stack([ts, np.ones_like(ts)])
    fitted_x = design @ np.linalg.lstsq(design, xy[:, 0], rcond=None)[0]
    fitted_y = design @ np.linalg.lstsq(design, xy[:, 1], rcond=None)[0]
    return float(np.sqrt(np.mean((xy[:, 0] - fitted_x) ** 2 + (xy[:, 1] - fitted_y) ** 2)))
