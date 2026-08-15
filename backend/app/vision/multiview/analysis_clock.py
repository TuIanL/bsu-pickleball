"""CanonicalAnalysisClock —— reference 视频的 analysis-frame clock。

与是否检测到人无关：每个 tick 都存在；缺源帧的视角标记为 unavailable / no_new_frame。

关键不变量（design D2 / invariant 8）：同一 ViewTrackingSession 的 `source_frame_index`
必须严格单调、不重复消费。若某 tick 映射到的 secondary source frame 已被前一 tick 消费,
则该 tick 该 view 标记为 `no_new_frame`,调用方 SHALL NOT 再次 `session.step()`。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from app.services.dual_camera_sync import FrameTiming, build_frame_map, map_reference_time
from app.services.frame_timing_provider import FrameTimingProvider
from app.vision.multiview.sync import MultiViewSyncCalibration


@dataclass(frozen=True)
class FrameSample:
    """某视角在某 tick 的源帧样本。"""

    source_frame_index: int
    source_timestamp_ms: float
    mapped_take_timestamp_ms: float
    selection_error_ms: float | None = None
    timing_authority: str = "source_pts"
    sync_quality: str = "unknown"
    frame: Any | None = None


@dataclass
class SynchronizedFrameBundle:
    """一次 canonical tick 的同步帧捆绑。"""

    take_timestamp_ms: float
    views: dict[str, FrameSample | None]  # view_id -> FrameSample | None(无源帧)
    frame_status: dict[str, str]
    mapping_diagnostics: dict[str, Any] = field(default_factory=dict)


class CanonicalAnalysisClock:
    """以 reference 视频的 analysis-frame 为 tick,为各 view 解析源帧。"""

    def __init__(
        self,
        *,
        reference_view_id: str,
        secondary_view_id: str,
        secondary_frames: list[FrameTiming],
        sync: MultiViewSyncCalibration | None,
        secondary_camera_id: str,
        max_pairing_error_ms: float = 1000.0 / 30.0,
        frame_provider: Callable[[int], Any] | None = None,
        reference_timing_provider: FrameTimingProvider | None = None,
        secondary_timing_provider: FrameTimingProvider | None = None,
        reference_timing_authority: str = "source_pts",
        secondary_timing_authority: str = "source_pts",
    ) -> None:
        self.reference_view_id = reference_view_id
        self.secondary_view_id = secondary_view_id
        self._sec_calibration = sync.mapping_for(secondary_camera_id) if sync is not None else None
        self._sec_frames = list(secondary_frames)
        self._max_pairing_error_s = max_pairing_error_ms / 1000.0
        self.max_pairing_error_ms = max_pairing_error_ms
        self._frame_provider = frame_provider
        self._reference_timing_provider = reference_timing_provider
        self._secondary_timing_provider = secondary_timing_provider
        self._reference_timing_authority = reference_timing_authority
        self._secondary_timing_authority = secondary_timing_authority
        self._sync_quality = self._sec_calibration.quality if self._sec_calibration is not None else "unknown"
        # view_id -> 最近已消费的 source_frame_index（单调不重复的依据）
        self.last_consumed_source_frame_index: dict[str, int] = {}
        self.status_counts: dict[str, int] = {}

    def _record_status(self, status: str) -> None:
        self.status_counts[status] = self.status_counts.get(status, 0) + 1

    def tick(
        self,
        *,
        reference_frame_index: int,
        reference_timestamp_seconds: float,
    ) -> SynchronizedFrameBundle:
        """推进一个 canonical tick。reference 视角始终 available;secondary 按 sync 配对。"""
        take_ms = reference_timestamp_seconds * 1000.0

        # ---- reference 视角：永远是当前分析帧 ----
        ref_sample = FrameSample(
            source_frame_index=reference_frame_index,
            source_timestamp_ms=(
                self._reference_timing_provider.timestamp_for_frame(reference_frame_index) * 1000.0
                if self._reference_timing_provider is not None
                and self._reference_timing_provider.timestamp_for_frame(reference_frame_index) is not None
                else take_ms
            ),
            mapped_take_timestamp_ms=take_ms,
            selection_error_ms=0.0,
            timing_authority=self._reference_timing_authority,
            sync_quality=self._sync_quality,
            frame=self._frame_provider(reference_frame_index) if self._frame_provider else None,
        )
        views: dict[str, FrameSample | None] = {self.reference_view_id: ref_sample}
        frame_status: dict[str, str] = {self.reference_view_id: "available"}
        self._record_status("available")

        # ---- secondary 视角：nearest mapping + 单调不重复 ----
        diag: dict[str, Any] = {}
        if self._sec_calibration is None or not self._sec_frames:
            views[self.secondary_view_id] = None
            status = "unavailable_no_sync" if self._sec_calibration is None else "unavailable_out_of_media_range"
            frame_status[self.secondary_view_id] = status
            diag["secondary_selection_status"] = status
            diag["reason"] = status
            self._record_status(status)
        else:
            selection = build_frame_map(
                [take_ms / 1000.0],
                self._sec_frames,
                calibration=self._sec_calibration,
                max_selection_error_seconds=self._max_pairing_error_s,
            )[0]
            diag["secondary_selection_status"] = selection.status
            diag["selection_error_ms"] = (
                selection.selection_error_seconds * 1000.0
                if selection.selection_error_seconds is not None
                else None
            )
            diag["timing_authority"] = self._secondary_timing_authority
            diag["sync_quality"] = self._sync_quality
            if selection.status == "ok" and selection.source_frame_index is not None:
                last = self.last_consumed_source_frame_index.get(self.secondary_view_id)
                if last is not None and selection.source_frame_index <= last:
                    # 已消费或倒退 → no_new_frame,不重复喂给有状态 tracker
                    views[self.secondary_view_id] = None
                    frame_status[self.secondary_view_id] = "no_new_frame"
                    diag["secondary_selection_error_ms"] = None
                    diag["reason"] = "source_frame_already_consumed"
                    self._record_status("no_new_frame")
                else:
                    self.last_consumed_source_frame_index[self.secondary_view_id] = selection.source_frame_index
                    views[self.secondary_view_id] = FrameSample(
                        source_frame_index=selection.source_frame_index,
                        source_timestamp_ms=(
                            selection.source_pts_seconds * 1000.0
                            if selection.source_pts_seconds is not None
                            else take_ms
                        ),
                        mapped_take_timestamp_ms=take_ms,
                        selection_error_ms=(
                            selection.selection_error_seconds * 1000.0
                            if selection.selection_error_seconds is not None
                            else None
                        ),
                        timing_authority=self._secondary_timing_authority,
                        sync_quality=self._sync_quality,
                        frame=(
                            self._frame_provider(selection.source_frame_index)
                            if self._frame_provider
                            else None
                        ),
                    )
                    frame_status[self.secondary_view_id] = "available"
                    self._record_status("available")
            else:
                views[self.secondary_view_id] = None
                status = selection.status if selection.status in {
                    "unavailable_outside_valid_interval",
                    "unavailable_out_of_media_range",
                    "unavailable_selection_error",
                } else "unavailable_no_sync"
                # 2026-08-13: 窗口开头（canonical 早于 valid_start，如 clipStart=0）回退到
                # 有效起点附近的帧，status 标记 fallback_valid_start。fallback 帧不消费 tracker
                # （MultiViewJointRun 只 step status=available），因此不违反单调不重复不变量；
                # 其价值是让 debug replay 前段有副摄画面 + 结构化 fallback 状态。
                fallback = (
                    self._fallback_valid_start_frame(take_ms)
                    if status == "unavailable_outside_valid_interval"
                    else None
                )
                if fallback is not None:
                    views[self.secondary_view_id] = fallback
                    frame_status[self.secondary_view_id] = "fallback_valid_start"
                    diag["reason"] = "fallback_valid_start"
                    diag["fallback_selection_error_ms"] = fallback.selection_error_ms
                    self._record_status("fallback_valid_start")
                else:
                    frame_status[self.secondary_view_id] = status
                    diag["reason"] = status
                    self._record_status(status)

        diag["frame_status_counts"] = dict(self.status_counts)

        return SynchronizedFrameBundle(
            take_timestamp_ms=take_ms,
            views=views,
            frame_status=frame_status,
            mapping_diagnostics=diag,
        )

    def _fallback_valid_start_frame(self, take_ms: float) -> FrameSample | None:
        """窗口开头的回退帧：把目标时间钳制到 valid_start 并映射最近的 secondary 帧。

        仅在 canonical 时间早于有效区间起点（selection 报 unavailable_outside_valid_interval）
        时被调用；media 范围外或无法映射时返回 None（调用方保持细分不可用）。
        """
        calibration = self._sec_calibration
        if calibration is None or calibration.valid_start_seconds is None or not self._sec_frames:
            return None
        seed_target = max(take_ms / 1000.0, calibration.valid_start_seconds)
        try:
            local = map_reference_time(calibration, seed_target)
        except Exception:  # noqa: BLE001 - 映射异常时放弃回退
            return None
        ordered = sorted(self._sec_frames, key=lambda frame: frame.pts_seconds)
        if local < ordered[0].pts_seconds or local > ordered[-1].pts_seconds:
            return None
        nearest = min(ordered, key=lambda frame: abs(frame.pts_seconds - local))
        error_seconds = nearest.pts_seconds - local
        return FrameSample(
            source_frame_index=nearest.frame_index,
            source_timestamp_ms=nearest.pts_seconds * 1000.0,
            mapped_take_timestamp_ms=take_ms,
            selection_error_ms=error_seconds * 1000.0,
            timing_authority=self._secondary_timing_authority,
            sync_quality=self._sync_quality,
            frame=self._frame_provider(nearest.frame_index) if self._frame_provider else None,
        )
