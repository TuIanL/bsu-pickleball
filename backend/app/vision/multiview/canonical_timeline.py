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

from app.services.dual_camera_sync import FrameTiming, build_frame_map
from app.vision.multiview.court_frame import CourtOrientation, local_to_canonical
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

        # 用既有 build_frame_map 一次完成 secondary 配对（reference 时间 → secondary 时间）。
        ref_times = [obs.timestamp_seconds for obs in reference_observations]
        sec_frames = [
            FrameTiming(frame_index=obs.source_frame_index, pts_seconds=obs.timestamp_seconds)
            for obs in secondary_observations
        ]
        sec_mapping = sync.mapping_for(secondary_camera_id) if sync is not None else None
        # 无 sync authority 或缺失该 camera 映射时，禁止假装对齐：secondary 一律 unavailable。
        sec_by_frame: dict[int, ViewObservation] = {}
        selections = []
        if sec_mapping is not None:
            selections = build_frame_map(
                ref_times,
                sec_frames,
                calibration=sec_mapping,
                max_selection_error_seconds=self.max_pairing_error_ms / 1000.0,
            )
            sec_by_frame = {obs.source_frame_index: obs for obs in secondary_observations}

        ticks: list[CanonicalTimelineTick] = []
        for index, ref_obs in enumerate(reference_observations):
            ref_cx, ref_cy = local_to_canonical(ref_obs.local_x_ft, ref_obs.local_y_ft, ref_orientation)
            reference_obs = CanonicalObservation(
                view_id=reference_view_id,
                view_status="available",
                source_frame_index=ref_obs.source_frame_index,
                source_timestamp_ms=ref_obs.timestamp_seconds * 1000.0,
                mapped_take_timestamp_ms=ref_obs.timestamp_seconds * 1000.0,
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
            if selections:
                selection = selections[index]
                if selection.status == "ok" and selection.source_frame_index is not None:
                    matched = sec_by_frame.get(selection.source_frame_index)
                    if matched is not None:
                        sec_cx, sec_cy = local_to_canonical(
                            matched.local_x_ft, matched.local_y_ft, sec_orientation
                        )
                        secondary_obs = CanonicalObservation(
                            view_id=secondary_view_id,
                            view_status="available",
                            source_frame_index=matched.source_frame_index,
                            source_timestamp_ms=matched.timestamp_seconds * 1000.0,
                            mapped_take_timestamp_ms=ref_obs.timestamp_seconds * 1000.0,
                            selection_error_ms=(
                                None
                                if selection.selection_error_seconds is None
                                else selection.selection_error_seconds * 1000.0
                            ),
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
                    take_timestamp_ms=ref_obs.timestamp_seconds * 1000.0,
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
