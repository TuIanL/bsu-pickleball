"""多维轨迹质量评分（trajectory_quality_evaluator）。

评分维度（设计 D4 / S2）：
  - observation_coverage：观测覆盖率；
  - detection_score：平均检测置信度；
  - fit_score：图像拟合残差（RMSE px）换算；
  - continuity_score：1 - 推算比例；
  - physical_plausibility：过网/弹地软诊断；
  - overall：加权汇总。

高度可信度独立评估（因全局低可信先验而受限）；single_anchor_warp 段质量上限受限。
过网只作软诊断，不硬门控。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.vision.courtvision_calibration_engine.court_geometry import PickleballCourtGeometry, standard_court
from app.vision.pickleball_game_analysis.image_space_trajectory_fitter import FitResult
from app.vision.pickleball_game_analysis.reconstruction_schemas import (
    NetCrossingStatus,
    ReconstructionConfig,
    ReconstructionMode,
    ReconstructedSegment,
    SampleSource,
    TrajectoryEvent,
    TrajectoryEventType,
)


@dataclass(frozen=True)
class QualityConfig:
    """质量评分超参数。"""

    max_rmse_px: float = 20.0              # 残差满分对应的像素上限
    single_anchor_cap: float = 0.75        # single_anchor_warp 总体质量上限
    height_prior_confidence: float = 0.25  # 全局接触高度先验的可信度
    low_confidence_threshold: float = 0.40  # image_only 段质量硬上限基准


class TrajectoryQualityEvaluator:
    """计算重建段的展示质量与物理软诊断。"""

    def __init__(
        self,
        config: QualityConfig | None = None,
        court: PickleballCourtGeometry | None = None,
    ) -> None:
        self.config = config or QualityConfig()
        self.court = court or standard_court()

    def evaluate(
        self,
        segment: ReconstructedSegment,
        fit: FitResult | None,
        events_by_id: dict[str, TrajectoryEvent],
    ) -> dict:
        """返回段质量字典（含 overall 与各维度）。"""
        samples = segment.samples
        total = len(samples)
        detected = [s for s in samples if s.source in (
            SampleSource.DETECTED.value,
            SampleSource.ANCHOR.value,
        )]
        interpolated = [s for s in samples if s.source == SampleSource.INTERPOLATED.value]
        predicted = [s for s in samples if s.source == SampleSource.MODEL_PREDICTED.value]

        coverage = round(len(detected) / total, 4) if total else 0.0
        predicted_ratio = round(len(predicted) / total, 4) if total else 0.0

        confidences = [c for c in (s.confidence for s in detected) if c is not None]
        detection_score = round(sum(confidences) / len(confidences), 4) if confidences else 0.0

        if fit is not None and fit.converged:
            fit_score = round(max(0.0, min(1.0, 1.0 - fit.residual_rmse_px / self.config.max_rmse_px)), 4)
            image_rmse_px = fit.residual_rmse_px
        else:
            fit_score = 0.0
            image_rmse_px = None

        continuity_score = round(max(0.0, 1.0 - predicted_ratio * 2.0), 4)

        anchor_confidences = [a["confidence"] for a in segment.anchors if a.get("confidence") is not None]
        anchor_confidence = round(sum(anchor_confidences) / len(anchor_confidences), 4) if anchor_confidences else 0.0

        # 事件置信度：起止边界事件
        event_confidences = []
        for event_id in (segment.start_event_id, segment.end_event_id):
            event = events_by_id.get(event_id or "")
            if event is not None:
                event_confidences.append(event.confidence)
        event_confidence = round(sum(event_confidences) / len(event_confidences), 4) if event_confidences else 0.0

        # 物理软诊断
        net_status, net_score = self._net_crossing_diagnostics(segment)
        bounce_score = self._bounce_consistency(segment)
        physics_score = round(0.7 * net_score + 0.3 * bounce_score, 4)

        overall = round(
            0.25 * coverage
            + 0.15 * detection_score
            + 0.25 * fit_score
            + 0.15 * continuity_score
            + 0.20 * physics_score,
            4,
        )

        # single_anchor_warp 质量上限
        mode = segment.reconstruction_mode
        if mode == ReconstructionMode.SINGLE_ANCHOR_WARP.value:
            overall = round(min(overall, self.config.single_anchor_cap), 4)
        if mode == ReconstructionMode.IMAGE_ONLY.value or segment.status == "insufficient_spatial_anchors":
            overall = round(min(overall, self.config.low_confidence_threshold * 0.9), 4)

        # 高度可信度（独立维度）
        height_confidence = self._height_confidence(segment)

        return {
            "observation_coverage": coverage,
            "detection_score": detection_score,
            "image_fit_rmse_px": image_rmse_px,
            "fit_score": fit_score,
            "predicted_ratio": predicted_ratio,
            "continuity_score": continuity_score,
            "anchor_confidence": anchor_confidence,
            "event_confidence": event_confidence,
            "physical_plausibility": physics_score,
            "net_crossing_status": net_status.value,
            "height_confidence": height_confidence,
            "overall": overall,
            "display_level": self._display_level(overall),
        }

    def _net_crossing_diagnostics(self, segment: ReconstructedSegment) -> tuple[NetCrossingStatus, float]:
        """过网软诊断：起止锚点是否分居网两侧、路径是否跨网、跨网高度是否可疑。"""
        anchors = {a["anchor_type"]: a for a in segment.anchors}
        ys = []
        for a in segment.anchors:
            court = a.get("court_xy")
            if court is not None and len(court) >= 2:
                ys.append(float(court[1]))
        if len(ys) < 2:
            return NetCrossingStatus.UNKNOWN, 0.5
        net_y = self.court.net_y_ft
        sides = {("above" if y < net_y else "below") for y in ys}
        if len(sides) == 1:
            return NetCrossingStatus.NOT_EXPECTED, 1.0

        # 跨越球网：检查跨网处估算高度是否低于网带（约 3 英尺）
        net_cross_height = self._height_at_net(segment, net_y)
        if net_cross_height is None:
            return NetCrossingStatus.EXPECTED, 0.7
        if net_cross_height < 1.0:
            return NetCrossingStatus.IMPLAUSIBLE, 0.3
        return NetCrossingStatus.ESTIMATED, 0.6

    def _height_at_net(self, segment: ReconstructedSegment, net_y: float) -> float | None:
        """在球场路径跨越网线处的估算高度；未跨网或无高度返回 None。"""
        crossing = None
        for left, right in zip(segment.samples[:-1], segment.samples[1:]):
            ly = left.court_xy[1] if left.court_xy else None
            ry = right.court_xy[1] if right.court_xy else None
            if ly is None or ry is None:
                continue
            if (ly - net_y) * (ry - net_y) <= 0 and left.estimated_height_ft is not None:
                crossing = left.estimated_height_ft
                break
        return crossing

    def _bounce_consistency(self, segment: ReconstructedSegment) -> float:
        """弹地一致性：有弹地锚点的段，边界高度严格为 0 → 满分。"""
        anchor_types = {a["anchor_type"] for a in segment.anchors}
        if "bounce" in anchor_types:
            return 1.0
        return 0.8

    def _height_confidence(self, segment: ReconstructedSegment) -> float:
        """高度可信度：取决于是否使用全局接触高度先验 / 弹地 / 估算。"""
        samples = segment.samples
        if not samples:
            return 0.0
        # 有弹地锚点且多数样本高度确定 → 中等；含先验 → 低
        anchor_types = {a["anchor_type"] for a in segment.anchors}
        has_bounce = "bounce" in anchor_types
        has_contact = "contact" in anchor_types
        if has_bounce and not has_contact:
            base = 0.55
        elif has_contact:
            base = self.config.height_prior_confidence
        else:
            base = 0.3
        known = [s for s in samples if s.estimated_height_ft is not None]
        coverage = len(known) / len(samples) if samples else 0.0
        return round(base * coverage, 3)

    def _display_level(self, overall: float) -> str:
        """展示阈值分级（设计建议初值）。"""
        if overall >= 0.80:
            return "high"
        if overall >= 0.60:
            return "medium"
        if overall >= 0.40:
            return "low"
        return "none"
