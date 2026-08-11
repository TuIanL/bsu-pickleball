"""多视角权威帧配对计划。

一个 canonical tick 只选择一张 secondary source frame；association 和 fusion
必须消费同一份计划，避免两个阶段分别 nearest-select 产生不一致证据。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from app.services.dual_camera_sync import FrameTiming, build_frame_map, map_reference_time
from app.vision.multiview.sync import MultiViewSyncCalibration
from app.vision.multiview.types import ViewObservation

PairingStatus = Literal["ok", "unavailable", "out_of_tolerance", "non_monotonic"]


@dataclass(frozen=True)
class FramePairingDecision:
    """一个 reference frame 对应的唯一 secondary source frame 决策。"""

    reference_frame_index: int
    reference_timestamp_seconds: float
    secondary_frame_index: int | None
    secondary_timestamp_seconds: float | None
    mapped_secondary_timestamp_seconds: float | None
    selection_error_ms: float | None
    status: PairingStatus
    reason: str | None = None

    @property
    def available(self) -> bool:
        return self.status == "ok" and self.secondary_frame_index is not None


@dataclass(frozen=True)
class FramePairingPlan:
    """一次运行共享的完整 reference→secondary 帧配对计划。"""

    reference_view_id: str
    secondary_view_id: str
    secondary_camera_id: str
    max_pairing_error_ms: float
    decisions: tuple[FramePairingDecision, ...]

    def by_reference_frame(self) -> dict[int, FramePairingDecision]:
        return {decision.reference_frame_index: decision for decision in self.decisions}

    def decision_for(self, reference_frame_index: int) -> FramePairingDecision | None:
        for decision in self.decisions:
            if decision.reference_frame_index == reference_frame_index:
                return decision
        return None

    @property
    def available_count(self) -> int:
        return sum(1 for decision in self.decisions if decision.available)


def build_frame_pairing_plan(
    *,
    reference_view_id: str,
    reference_observations: Sequence[ViewObservation],
    secondary_view_id: str,
    secondary_observations: Sequence[ViewObservation],
    sync: MultiViewSyncCalibration | None,
    secondary_camera_id: str,
    max_pairing_error_ms: float,
) -> FramePairingPlan:
    """按 reference 时间轴一次性选择副摄 source frame。

    输入 observations 可能包含同一 source frame 的多个球员，因此先按 frame 去重，
    再做 frame-level pairing。无 sync 或无 secondary mapping 时显式生成 unavailable
    decision，而不是隐式按 offset=0 配对。
    """

    reference_frames = _unique_frame_timings(reference_observations)
    secondary_frames = _unique_frame_timings(secondary_observations)
    tolerance_s = max_pairing_error_ms / 1000.0
    calibration = sync.mapping_for(secondary_camera_id) if sync is not None else None

    decisions: list[FramePairingDecision] = []
    previous_secondary_index: int | None = None
    if calibration is None:
        for frame in reference_frames:
            decisions.append(
                FramePairingDecision(
                    reference_frame_index=frame.frame_index,
                    reference_timestamp_seconds=frame.pts_seconds,
                    secondary_frame_index=None,
                    secondary_timestamp_seconds=None,
                    mapped_secondary_timestamp_seconds=None,
                    selection_error_ms=None,
                    status="unavailable",
                    reason="secondary sync mapping unavailable",
                )
            )
        return FramePairingPlan(
            reference_view_id=reference_view_id,
            secondary_view_id=secondary_view_id,
            secondary_camera_id=secondary_camera_id,
            max_pairing_error_ms=max_pairing_error_ms,
            decisions=tuple(decisions),
        )

    selections = build_frame_map(
        [frame.pts_seconds for frame in reference_frames],
        secondary_frames,
        calibration=calibration,
        max_selection_error_seconds=tolerance_s,
    )
    for reference_frame, selection in zip(reference_frames, selections, strict=False):
        mapped_target = map_reference_time(calibration, reference_frame.pts_seconds)
        status: PairingStatus = selection.status  # type: ignore[assignment]
        reason: str | None = None
        if status == "ok" and selection.source_frame_index is not None:
            if previous_secondary_index is not None and selection.source_frame_index < previous_secondary_index:
                status = "non_monotonic"
                reason = "secondary source frame index moved backwards"
                selection_error_ms = None
                secondary_timestamp = None
                secondary_index = None
            else:
                previous_secondary_index = selection.source_frame_index
                selection_error_ms = (
                    None
                    if selection.selection_error_seconds is None
                    else selection.selection_error_seconds * 1000.0
                )
                secondary_timestamp = selection.source_pts_seconds
                secondary_index = selection.source_frame_index
        else:
            secondary_index = None
            secondary_timestamp = None
            selection_error_ms = (
                None
                if selection.selection_error_seconds is None
                else selection.selection_error_seconds * 1000.0
            )
            reason = f"secondary frame pairing status: {selection.status}"
        decisions.append(
            FramePairingDecision(
                reference_frame_index=reference_frame.frame_index,
                reference_timestamp_seconds=reference_frame.pts_seconds,
                secondary_frame_index=secondary_index,
                secondary_timestamp_seconds=secondary_timestamp,
                mapped_secondary_timestamp_seconds=mapped_target,
                selection_error_ms=selection_error_ms,
                status=status,
                reason=reason,
            )
        )

    return FramePairingPlan(
        reference_view_id=reference_view_id,
        secondary_view_id=secondary_view_id,
        secondary_camera_id=secondary_camera_id,
        max_pairing_error_ms=max_pairing_error_ms,
        decisions=tuple(decisions),
    )


def observations_by_source_frame(
    observations: Sequence[ViewObservation],
) -> dict[int, list[ViewObservation]]:
    """按 source frame 分组，保证一个 pairing decision 消费整帧观测。"""

    grouped: dict[int, list[ViewObservation]] = {}
    for observation in observations:
        grouped.setdefault(observation.source_frame_index, []).append(observation)
    return grouped


def _unique_frame_timings(observations: Sequence[ViewObservation]) -> list[FrameTiming]:
    by_frame: dict[int, float] = {}
    for observation in observations:
        by_frame.setdefault(
            observation.source_frame_index,
            observation.source_pts_seconds
            if observation.source_pts_seconds is not None
            else observation.timestamp_seconds,
        )
    return [FrameTiming(frame_index, timestamp) for frame_index, timestamp in sorted(by_frame.items(), key=lambda item: item[1])]
