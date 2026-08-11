"""Canonical Timeline（canonical_timeline）—— 融合时刻来源与跨视角 pairing。

契约：
- **Canonical timeline = reference track 的 analysis-frame timeline**。
- 对每个 reference 时刻 `take_timestamp_ms`，用 sync mapping 为另一视角找最近真实
  source sample，要求 `abs(selection_error_ms) <= max_pairing_error_ms`，否则该视角
  该时刻 `view_status = unavailable`。

复用 `app.services.dual_camera_sync.build_frame_map` 完成配对与误差计算。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from app.vision.multiview.court_frame import CourtOrientation, local_to_canonical
from app.vision.multiview.pairing import (
    FramePairingPlan,
    build_frame_pairing_plan,
    observations_by_source_frame,
)
from app.vision.multiview.sync import MultiViewSyncCalibration
from app.vision.multiview.types import CanonicalObservation, CanonicalTimelineTick, ViewObservation


@dataclass
class CanonicalTimelineBuilder:
    """把两路真实观测（含 sync mapping）构建为统一 canonical 时间轴。"""

    max_pairing_error_ms: float = field(default=1000.0 / 30.0)

    def build(
        self,
        *,
        reference_view_id: str,
        reference_observations: Sequence[ViewObservation],
        secondary_view_id: str,
        secondary_observations: Sequence[ViewObservation],
        sync: MultiViewSyncCalibration | None,
        secondary_camera_id: str,
        orientations: dict[str, CourtOrientation],
        pairing_plan: FramePairingPlan | None = None,
    ) -> list[CanonicalTimelineTick]:
        """构建 canonical timeline。

        需要 reference 与 secondary 两路 `court_orientation` 均已知；任一缺失直接抛错
        （run 的 job-level 校验应在此之前拦截，这里保持严格）。
        """
        ref_orientation = orientations.get(reference_view_id)
        sec_orientation = orientations.get(secondary_view_id)
        if ref_orientation is None or sec_orientation is None:
            raise ValueError(
                "canonical timeline requires both view orientations declared; got "
                f"reference={ref_orientation!r} secondary={sec_orientation!r}"
            )

        if not reference_observations:
            return []

        # 兼容直接调用 builder 的旧消费者；正式 pipeline 会把同一份 plan 传进来。
        pairing_plan = pairing_plan or build_frame_pairing_plan(
            reference_view_id=reference_view_id,
            reference_observations=reference_observations,
            secondary_view_id=secondary_view_id,
            secondary_observations=secondary_observations,
            sync=sync,
            secondary_camera_id=secondary_camera_id,
            max_pairing_error_ms=self.max_pairing_error_ms,
        )
        sec_by_frame = observations_by_source_frame(secondary_observations)

        ticks: list[CanonicalTimelineTick] = []
        for ref_obs in reference_observations:
            ref_cx, ref_cy = local_to_canonical(ref_obs.local_x_ft, ref_obs.local_y_ft, ref_orientation)
            reference_obs = CanonicalObservation(
                view_id=reference_view_id,
                view_status="available",
                source_frame_index=ref_obs.source_frame_index,
                source_timestamp_ms=_observation_time(ref_obs) * 1000.0,
                mapped_take_timestamp_ms=_observation_time(ref_obs) * 1000.0,
                selection_error_ms=0.0,
                canonical_x_ft=ref_cx,
                canonical_y_ft=ref_cy,
                view_player_id=ref_obs.view_player_id,
                detector_confidence=ref_obs.confidence,
                projection_confidence=ref_obs.projection_confidence,
                footpoint_method=ref_obs.footpoint_method,
                tracking_status="detected",
                is_interpolated=False,
            )

            secondary_obs: CanonicalObservation = self._unavailable(secondary_view_id)
            decision = pairing_plan.decision_for(ref_obs.source_frame_index)
            if decision is not None and decision.available:
                matched_observations = sec_by_frame.get(
                    decision.secondary_frame_index
                    if decision.secondary_frame_index is not None
                    else -1,
                    [],
                )
                matched = matched_observations[0] if matched_observations else None
                if matched is not None:
                    sec_cx, sec_cy = local_to_canonical(
                        matched.local_x_ft, matched.local_y_ft, sec_orientation
                    )
                    secondary_obs = CanonicalObservation(
                        view_id=secondary_view_id,
                        view_status="available",
                        source_frame_index=matched.source_frame_index,
                        source_timestamp_ms=_observation_time(matched) * 1000.0,
                        mapped_take_timestamp_ms=_observation_time(ref_obs) * 1000.0,
                        selection_error_ms=decision.selection_error_ms,
                        canonical_x_ft=sec_cx,
                        canonical_y_ft=sec_cy,
                        view_player_id=matched.view_player_id,
                        detector_confidence=matched.confidence,
                        projection_confidence=matched.projection_confidence,
                        footpoint_method=matched.footpoint_method,
                        tracking_status="detected",
                        is_interpolated=False,
                    )

            ticks.append(
                CanonicalTimelineTick(
                    take_timestamp_ms=_observation_time(ref_obs) * 1000.0,
                    reference_frame_index=ref_obs.source_frame_index,
                    observations={
                        reference_view_id: reference_obs,
                        secondary_view_id: secondary_obs,
                    },
                )
            )
        return ticks

    @staticmethod
    def _unavailable(view_id: str) -> CanonicalObservation:
        return CanonicalObservation(
            view_id=view_id,
            view_status="unavailable",
            source_frame_index=None,
            source_timestamp_ms=None,
            mapped_take_timestamp_ms=None,
            selection_error_ms=None,
            canonical_x_ft=None,
            canonical_y_ft=None,
        )


def _observation_time(observation: ViewObservation) -> float:
    return (
        observation.source_pts_seconds
        if observation.source_pts_seconds is not None
        else observation.timestamp_seconds
    )
