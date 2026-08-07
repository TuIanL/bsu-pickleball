"""融合管线（pipeline）—— predict → associate → quality → pair → conflict → fusion → update 循环。

把两路 per-player 观测经关联、canonical timeline、质量、成对一致性、位置融合与
全局时间滤波，产出每个 global player 的 `FusionMeasurement` 序列。

- global prediction 统一来自 `GlobalTrackFilter.predict(t)`（单一来源）；
- `PlayerPositionFusion` 无观测时返回 None，由 `GlobalTrackFilter` 决定是否输出
  `predicted` 样本（metric_eligible=False，不回灌滤波器）；
- 只把 `metric_eligible=True` 的测量回灌滤波器，避免预测自我喂养。
"""

from __future__ import annotations

import bisect
from collections.abc import Sequence
from dataclasses import dataclass

from app.services.dual_camera_sync import map_reference_time
from app.vision.multiview.association import CrossViewPlayerAssociator, PlayerAssociation
from app.vision.multiview.canonical_timeline import CanonicalTimelineBuilder
from app.vision.multiview.court_frame import CourtOrientation
from app.vision.multiview.fusion import FusionConfig, FusionMeasurement, fuse_observation
from app.vision.multiview.global_filter import GlobalTrackFilter
from app.vision.multiview.quality import (
    intrinsic_from_canonical,
    pair_consistency,
    view_intrinsic_quality,
)
from app.vision.multiview.sync import MultiViewSyncCalibration
from app.vision.multiview.types import ViewObservation


@dataclass
class FusionPipelineResult:
    """一次融合管线运行的结果。"""

    measurements: list[FusionMeasurement]
    global_players: list[PlayerAssociation]


def run_fusion_pipeline(
    *,
    reference_view_id: str,
    reference_observations: Sequence[ViewObservation],
    secondary_view_id: str,
    secondary_observations: Sequence[ViewObservation],
    reference_orientation: CourtOrientation | None,
    secondary_orientation: CourtOrientation | None,
    sync: MultiViewSyncCalibration | None,
    secondary_camera_id: str,
    max_pairing_error_ms: float,
    config: FusionConfig,
    associator: CrossViewPlayerAssociator | None = None,
    filter_: GlobalTrackFilter | None = None,
    global_players: Sequence[PlayerAssociation] | None = None,
) -> FusionPipelineResult:
    """执行完整融合管线。

    若未提供 `global_players`，先内部运行关联器建立跨视角映射。
    """
    reference_orientation = reference_orientation or CourtOrientation.identity
    secondary_orientation = secondary_orientation or CourtOrientation.identity

    if global_players is None:
        associator = associator or CrossViewPlayerAssociator()
        _run_association_pass(
            associator=associator,
            reference_view_id=reference_view_id,
            reference_observations=reference_observations,
            secondary_view_id=secondary_view_id,
            secondary_observations=secondary_observations,
            reference_orientation=reference_orientation,
            secondary_orientation=secondary_orientation,
            sync=sync,
            secondary_camera_id=secondary_camera_id,
            max_pairing_error_ms=max_pairing_error_ms,
        )
        global_players = associator.snapshot_global_players(reference_view_id, secondary_view_id)

    filter_ = filter_ or GlobalTrackFilter()
    timeline_builder = CanonicalTimelineBuilder(max_pairing_error_ms=max_pairing_error_ms)
    ref_by_player = _group_by_view_player(reference_observations)
    sec_by_player = _group_by_view_player(secondary_observations)
    measurements: list[FusionMeasurement] = []

    for association in global_players:
        ref_pid = association.reference_view_player_id
        sec_pid = association.secondary_view_player_id
        ref_obs = ref_by_player.get(ref_pid, []) if ref_pid else []
        sec_obs = sec_by_player.get(sec_pid, []) if sec_pid else []
        if not ref_obs:
            continue

        ticks = timeline_builder.build(
            reference_view_id=reference_view_id,
            reference_observations=ref_obs,
            secondary_view_id=secondary_view_id,
            secondary_observations=sec_obs,
            sync=sync,
            secondary_camera_id=secondary_camera_id,
            orientations={reference_view_id: reference_orientation, secondary_view_id: secondary_orientation},
        )
        for tick in ticks:
            ref_canonical = tick.observations[reference_view_id]
            sec_canonical = tick.observations[secondary_view_id]
            timestamp_s = tick.take_timestamp_ms / 1000.0

            predicted = filter_.predict(timestamp_s).get(association.global_player_id)

            ref_intrinsic = view_intrinsic_quality(intrinsic_from_canonical(ref_canonical))
            sec_intrinsic = view_intrinsic_quality(intrinsic_from_canonical(sec_canonical))
            pair = pair_consistency(
                (
                    (ref_canonical.canonical_x_ft, ref_canonical.canonical_y_ft)
                    if ref_canonical.view_status == "available" and ref_canonical.canonical_x_ft is not None
                    else None
                ),
                (
                    (sec_canonical.canonical_x_ft, sec_canonical.canonical_y_ft)
                    if sec_canonical.view_status == "available" and sec_canonical.canonical_x_ft is not None
                    else None
                ),
                predicted,
                max_plausible_distance_ft=config.max_plausible_distance_ft,
            )

            measurement = fuse_observation(
                global_player_id=association.global_player_id,
                timestamp_seconds=timestamp_s,
                take_timestamp_ms=tick.take_timestamp_ms,
                reference_frame_index=tick.reference_frame_index,
                reference_obs=ref_canonical,
                secondary_obs=sec_canonical,
                reference_intrinsic=ref_intrinsic,
                secondary_intrinsic=sec_intrinsic,
                pair=pair,
                predicted=predicted,
                sync_quality=sync.worst_quality() if sync else "unknown",
                config=config,
            )

            if measurement is not None and measurement.metric_eligible:
                filter_.update(
                    association.global_player_id,
                    measurement.x_ft,
                    measurement.y_ft,
                    timestamp_s,
                )
            elif measurement is None and predicted is not None:
                # 无观测 → 由 GlobalTrackFilter 输出预测样本（metric_eligible=False）。
                measurements.append(
                    FusionMeasurement(
                        global_player_id=association.global_player_id,
                        timestamp_seconds=timestamp_s,
                        take_timestamp_ms=tick.take_timestamp_ms,
                        reference_frame_index=tick.reference_frame_index,
                        x_ft=predicted[0],
                        y_ft=predicted[1],
                        fusion_status="predicted",
                        fusion_confidence=0.0,
                        contributing_views=(),
                        selected_view="prediction",
                        sync_quality=sync.worst_quality() if sync else "unknown",
                        court_frame_version=config.court_frame_version,
                        measurement_source="none",
                        metric_eligible=False,
                    )
                )

            if measurement is not None:
                measurements.append(measurement)

    measurements.sort(key=lambda m: (m.take_timestamp_ms, m.global_player_id))
    return FusionPipelineResult(measurements=measurements, global_players=list(global_players))


def _run_association_pass(
    *,
    associator: CrossViewPlayerAssociator,
    reference_view_id: str,
    reference_observations: Sequence[ViewObservation],
    secondary_view_id: str,
    secondary_observations: Sequence[ViewObservation],
    reference_orientation: CourtOrientation,
    secondary_orientation: CourtOrientation,
    sync: MultiViewSyncCalibration | None,
    secondary_camera_id: str,
    max_pairing_error_ms: float,
) -> None:
    """在 reference 时间轴逐 tick 运行关联器，建立跨视角映射。"""
    ref_by_frame: dict[int, list[ViewObservation]] = {}
    for obs in reference_observations:
        ref_by_frame.setdefault(obs.source_frame_index, []).append(obs)

    # 每个 reference tick 取 nearest secondary obs（按 timestamp，容差内）。
    # secondary 时间经 sync mapping 换算（ref_time → secondary_time）。
    sec_sorted = sorted(secondary_observations, key=lambda o: o.timestamp_seconds)
    sec_times = [o.timestamp_seconds for o in sec_sorted]
    sec_calibration = sync.mapping_for(secondary_camera_id) if sync is not None else None

    tolerance_s = max_pairing_error_ms / 1000.0
    for frame_index in sorted(ref_by_frame):
        ref_obs_at_tick = ref_by_frame[frame_index]
        if not ref_obs_at_tick:
            continue
        ref_t0 = ref_obs_at_tick[0].timestamp_seconds
        sec_target = ref_t0
        if sec_calibration is not None:
            sec_target = map_reference_time(sec_calibration, ref_t0)
        # nearest secondary observations within tolerance per player.
        sec_at_tick: list[ViewObservation] = []
        if sec_sorted:
            lo = max(0, bisect.bisect_left(sec_times, sec_target - tolerance_s))
            hi = bisect.bisect_right(sec_times, sec_target + tolerance_s)
            for obs in sec_sorted[lo:hi]:
                if abs(obs.timestamp_seconds - sec_target) <= tolerance_s:
                    sec_at_tick.append(obs)
        associator.process_tick(
            reference_view_id=reference_view_id,
            reference_observations=ref_obs_at_tick,
            secondary_view_id=secondary_view_id,
            secondary_observations=sec_at_tick,
            reference_orientation=reference_orientation,
            secondary_orientation=secondary_orientation,
        )


def _group_by_view_player(
    observations: Sequence[ViewObservation],
) -> dict[str, list[ViewObservation]]:
    grouped: dict[str, list[ViewObservation]] = {}
    for obs in observations:
        grouped.setdefault(obs.view_player_id, []).append(obs)
    return grouped
