"""位置融合（fusion）—— PlayerPositionFusion 状态机与 conflict gate。

状态只包括 `dual_observed / single_view_fallback / conflict / unavailable`，
**不含 `predicted`**：是否在无观测时刻输出预测点由 `GlobalTrackFilter` 决定。

- 双观测：按观测质量加权（禁止固定 50/50 平均）；
- 单观测：该路观测（sample-level fallback）；
- 冲突：两路 canonical 距离超阈值且无法由运动预测合理解释 → `conflict`，
  不平均出不存在的中间位置，按高质量单视角或全局预测选择；
- 无观测：`unavailable`（不产出 measurement，由 orchestration 决定是否预测）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.vision.multiview.quality import PairConsistencyResult, fusion_weights
from app.vision.multiview.types import CanonicalObservation

# PlayerPositionFusion 的状态只含 dual_observed / single_view_fallback / conflict /
# unavailable；`predicted` 是融合管线在无观测时经 GlobalTrackFilter 预测产出的 pipeline 级状态，
# fuse_observation 本身永不返回它。
FusionStatus = Literal[
    "dual_observed",
    "single_view_fallback",
    "conflict",
    "unavailable",
    "predicted",
]
MeasurementSource = Literal["dual", "reference", "secondary", "none"]

# 融合后各视角观测的明细（Phase 7 会原样序列化进 artifact）。
ViewObservationDetail = dict[str, object]


@dataclass(frozen=True)
class FusionConfig:
    """融合参数（算法参数，Spike/A-B 后冻结）。"""

    conflict_distance_ft: float = 3.0
    max_plausible_distance_ft: float = 3.0
    degraded_sync: bool = False
    # 两路 intrinsic 均低于该阈值时，冲突场景优先采用全局预测（metric_eligible=False）。
    prediction_floor: float = 0.2
    court_frame_version: str = "canonical_court_frame.v1"


@dataclass(frozen=True)
class FusionMeasurement:
    """一次融合的结果（Phase 7 序列化为 fused_player_trajectory.v1 sample）。"""

    global_player_id: str
    timestamp_seconds: float
    take_timestamp_ms: float
    reference_frame_index: int
    x_ft: float | None
    y_ft: float | None
    fusion_status: FusionStatus
    fusion_confidence: float
    contributing_views: tuple[str, ...]
    selected_view: str | None
    view_observations: dict[str, ViewObservationDetail] = field(default_factory=dict)
    association_confidence: float = 0.0
    sync_quality: str = "unknown"
    court_frame_version: str = "canonical_court_frame.v1"
    measurement_source: MeasurementSource = "none"
    metric_eligible: bool = False


def _obs_detail(
    obs: CanonicalObservation | None,
    intrinsic: float,
) -> ViewObservationDetail | None:
    if obs is None or obs.view_status != "available":
        return None
    return {
        "view_id": obs.view_id,
        "view_status": obs.view_status,
        "source_frame_index": obs.source_frame_index,
        "source_timestamp_ms": obs.source_timestamp_ms,
        "mapped_take_timestamp_ms": obs.mapped_take_timestamp_ms,
        "selection_error_ms": obs.selection_error_ms,
        "timing_authority": obs.timing_authority,
        "sync_quality": obs.sync_quality,
        "x_ft": obs.canonical_x_ft,
        "y_ft": obs.canonical_y_ft,
        "quality": intrinsic,
        "observation_origin": obs.observation_origin,
        "donor_view": obs.donor_view,
        "residual_ft": obs.residual_ft,
    }


def fuse_observation(
    *,
    global_player_id: str,
    timestamp_seconds: float,
    take_timestamp_ms: float,
    reference_frame_index: int,
    reference_obs: CanonicalObservation | None,
    secondary_obs: CanonicalObservation | None,
    reference_intrinsic: float,
    secondary_intrinsic: float,
    pair: PairConsistencyResult,
    predicted: tuple[float, float] | None,
    sync_quality: str,
    config: FusionConfig,
    reference_label: str = "reference",
    secondary_label: str = "secondary",
) -> FusionMeasurement | None:
    """融合一个 canonical tick 的两路观测，返回 measurement；无观测返回 None。"""

    ref_available = (
        reference_obs is not None
        and reference_obs.view_status == "available"
        and reference_obs.canonical_x_ft is not None
        and reference_obs.canonical_y_ft is not None
    )
    sec_available = (
        secondary_obs is not None
        and secondary_obs.view_status == "available"
        and secondary_obs.canonical_x_ft is not None
        and secondary_obs.canonical_y_ft is not None
    )
    ref_xy = (reference_obs.canonical_x_ft, reference_obs.canonical_y_ft) if ref_available else None
    sec_xy = (secondary_obs.canonical_x_ft, secondary_obs.canonical_y_ft) if sec_available else None

    details: dict[str, ViewObservationDetail] = {}
    if ref_available:
        details[reference_label] = _obs_detail(reference_obs, reference_intrinsic)
    if sec_available:
        details[secondary_label] = _obs_detail(secondary_obs, secondary_intrinsic)

    # 双观测：冲突检测 or 加权融合。
    if ref_available and sec_available:
        assert ref_xy is not None and sec_xy is not None
        inter_view = pair.inter_view_distance_ft
        in_conflict = inter_view is not None and inter_view > config.conflict_distance_ft

        if not in_conflict:
            ref_w, sec_w = fusion_weights(
                reference_intrinsic,
                secondary_intrinsic,
                pair.consistency,
                degraded_sync=config.degraded_sync,
            )
            x = ref_w * ref_xy[0] + sec_w * sec_xy[0]
            y = ref_w * ref_xy[1] + sec_w * sec_xy[1]
            confidence = min(pair.consistency, max(reference_intrinsic, secondary_intrinsic))
            return FusionMeasurement(
                global_player_id=global_player_id,
                timestamp_seconds=timestamp_seconds,
                take_timestamp_ms=take_timestamp_ms,
                reference_frame_index=reference_frame_index,
                x_ft=x,
                y_ft=y,
                fusion_status="dual_observed",
                fusion_confidence=confidence,
                contributing_views=(reference_label, secondary_label),
                selected_view=None,
                view_observations=details,
                sync_quality=sync_quality,
                court_frame_version=config.court_frame_version,
                measurement_source="dual",
                metric_eligible=True,
            )

        # 冲突：不平均中间点。
        choose_reference = reference_intrinsic >= secondary_intrinsic
        chosen_xy = ref_xy if choose_reference else sec_xy
        chosen_view = reference_label if choose_reference else secondary_label
        if (
            predicted is not None
            and reference_intrinsic < config.prediction_floor
            and secondary_intrinsic < config.prediction_floor
        ):
            # 两路都不可信 → 用全局预测（非真实观测，metric_eligible=False）。
            return FusionMeasurement(
                global_player_id=global_player_id,
                timestamp_seconds=timestamp_seconds,
                take_timestamp_ms=take_timestamp_ms,
                reference_frame_index=reference_frame_index,
                x_ft=predicted[0],
                y_ft=predicted[1],
                fusion_status="conflict",
                fusion_confidence=max(reference_intrinsic, secondary_intrinsic) * 0.3,
                contributing_views=(reference_label, secondary_label),
                selected_view="prediction",
                view_observations=details,
                sync_quality=sync_quality,
                court_frame_version=config.court_frame_version,
                measurement_source="none",
                metric_eligible=False,
            )
        return FusionMeasurement(
            global_player_id=global_player_id,
            timestamp_seconds=timestamp_seconds,
            take_timestamp_ms=take_timestamp_ms,
            reference_frame_index=reference_frame_index,
            x_ft=chosen_xy[0],
            y_ft=chosen_xy[1],
            fusion_status="conflict",
            fusion_confidence=max(reference_intrinsic, secondary_intrinsic) * 0.3,
            contributing_views=(reference_label, secondary_label),
            selected_view=chosen_view,
            view_observations=details,
            sync_quality=sync_quality,
            court_frame_version=config.court_frame_version,
            measurement_source=(
                "reference" if choose_reference and reference_label == "reference" else
                "secondary" if not choose_reference and secondary_label == "secondary" else
                "dual"
            ),
            metric_eligible=True,
        )

    # 单观测：sample-level fallback。
    if ref_available:
        assert ref_xy is not None
        return FusionMeasurement(
            global_player_id=global_player_id,
            timestamp_seconds=timestamp_seconds,
            take_timestamp_ms=take_timestamp_ms,
            reference_frame_index=reference_frame_index,
            x_ft=ref_xy[0],
            y_ft=ref_xy[1],
            fusion_status="single_view_fallback",
            fusion_confidence=reference_intrinsic,
            contributing_views=(reference_label,),
            selected_view=reference_label,
            view_observations=details,
            sync_quality=sync_quality,
            court_frame_version=config.court_frame_version,
            measurement_source="reference" if reference_label == "reference" else "dual",
            metric_eligible=True,
        )
    if sec_available:
        assert sec_xy is not None
        return FusionMeasurement(
            global_player_id=global_player_id,
            timestamp_seconds=timestamp_seconds,
            take_timestamp_ms=take_timestamp_ms,
            reference_frame_index=reference_frame_index,
            x_ft=sec_xy[0],
            y_ft=sec_xy[1],
            fusion_status="single_view_fallback",
            fusion_confidence=secondary_intrinsic,
            contributing_views=(secondary_label,),
            selected_view=secondary_label,
            view_observations=details,
            sync_quality=sync_quality,
            court_frame_version=config.court_frame_version,
            measurement_source="secondary" if secondary_label == "secondary" else "dual",
            metric_eligible=True,
        )

    # 无观测：unavailable（不产出 measurement）。
    return None
