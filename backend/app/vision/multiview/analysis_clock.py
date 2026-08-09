"""CanonicalAnalysisClock —— reference 视频的 analysis-frame clock。

与是否检测到人无关：每个 tick 都存在；缺源帧的视角标记为 unavailable / no_new_frame。

关键不变量（design D2 / invariant 8）：同一 ViewTrackingSession 的 `source_frame_index`
必须严格单调、不重复消费。若某 tick 映射到的 secondary source frame 已被前一 tick 消费,
则该 tick 该 view 标记为 `no_new_frame`,调用方 SHALL NOT 再次 `session.step()`。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from app.services.dual_camera_sync import FrameTiming, build_frame_map
from app.vision.multiview.sync import MultiViewSyncCalibration


@dataclass(frozen=True)
class FrameSample:
    """某视角在某 tick 的源帧样本。"""

    source_frame_index: int
    source_timestamp_ms: float
    mapped_take_timestamp_ms: float
    selection_error_ms: float | None = None
    frame: Any | None = None


@dataclass
class SynchronizedFrameBundle:
    """一次 canonical tick 的同步帧捆绑。"""

    take_timestamp_ms: float
    views: dict[str, FrameSample | None]  # view_id -> FrameSample | None(无源帧)
    frame_status: dict[str, str]  # available | unavailable | no_new_frame
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
    ) -> None:
        self.reference_view_id = reference_view_id
        self.secondary_view_id = secondary_view_id
        self._sec_calibration = sync.mapping_for(secondary_camera_id) if sync is not None else None
        self._sec_frames = list(secondary_frames)
        self._max_pairing_error_s = max_pairing_error_ms / 1000.0
        self._frame_provider = frame_provider
        # view_id -> 最近已消费的 source_frame_index（单调不重复的依据）
        self.last_consumed_source_frame_index: dict[str, int] = {}

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
            source_timestamp_ms=take_ms,
            mapped_take_timestamp_ms=take_ms,
            selection_error_ms=0.0,
            frame=self._frame_provider(reference_frame_index) if self._frame_provider else None,
        )
        views: dict[str, FrameSample | None] = {self.reference_view_id: ref_sample}
        frame_status: dict[str, str] = {self.reference_view_id: "available"}

        # ---- secondary 视角：nearest mapping + 单调不重复 ----
        diag: dict[str, Any] = {}
        if self._sec_calibration is None or not self._sec_frames:
            views[self.secondary_view_id] = None
            frame_status[self.secondary_view_id] = "unavailable"
            diag["secondary_selection_status"] = "unavailable_no_sync_or_frames"
        else:
            selection = build_frame_map(
                [take_ms / 1000.0],
                self._sec_frames,
                calibration=self._sec_calibration,
                max_selection_error_seconds=self._max_pairing_error_s,
            )[0]
            diag["secondary_selection_status"] = selection.status
            if selection.status == "ok" and selection.source_frame_index is not None:
                last = self.last_consumed_source_frame_index.get(self.secondary_view_id)
                if last is not None and selection.source_frame_index <= last:
                    # 已消费或倒退 → no_new_frame,不重复喂给有状态 tracker
                    views[self.secondary_view_id] = None
                    frame_status[self.secondary_view_id] = "no_new_frame"
                    diag["secondary_selection_error_ms"] = None
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
                        frame=(
                            self._frame_provider(selection.source_frame_index)
                            if self._frame_provider
                            else None
                        ),
                    )
                    frame_status[self.secondary_view_id] = "available"
            else:
                views[self.secondary_view_id] = None
                frame_status[self.secondary_view_id] = "unavailable"

        return SynchronizedFrameBundle(
            take_timestamp_ms=take_ms,
            views=views,
            frame_status=frame_status,
            mapping_diagnostics=diag,
        )
