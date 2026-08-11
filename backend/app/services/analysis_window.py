"""Shared time-window contract for video analysis.

The public clip is a half-open interval on the reference take timeline.
Decoded frames may include a bounded pre/post-roll for tracker warm-up, but
the requested range remains the only range eligible for user-facing metrics.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.frame_timing_provider import FrameTimingProvider


class AnalysisWindowError(ValueError):
    """Raised when a requested analysis window cannot be executed safely."""


@dataclass(frozen=True)
class AnalysisWindow:
    requested_start_ms: int | None
    requested_end_ms: int | None
    decoded_start_ms: int
    decoded_end_ms: int
    source_duration_ms: int
    source_frame_count: int
    fps: float
    requested_start_frame: int | None
    requested_end_frame: int | None
    decoded_start_frame: int
    decoded_end_frame: int
    pre_roll_ms: int
    post_roll_ms: int
    timing_provenance: dict[str, object] | None = None

    @property
    def enabled(self) -> bool:
        return self.requested_start_ms is not None and self.requested_end_ms is not None

    @property
    def planned_frame_count(self) -> int:
        return max(0, self.decoded_end_frame - self.decoded_start_frame)

    @property
    def requested_frame_count(self) -> int:
        if self.requested_start_frame is None or self.requested_end_frame is None:
            return self.source_frame_count
        return max(0, self.requested_end_frame - self.requested_start_frame)

    def is_requested_frame(self, frame_index: int) -> bool:
        if not self.enabled:
            return True
        assert self.requested_start_frame is not None
        assert self.requested_end_frame is not None
        return self.requested_start_frame <= frame_index < self.requested_end_frame

    def metadata(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "enabled": self.enabled,
            "source_frame_count": self.source_frame_count,
            "source_duration_ms": self.source_duration_ms,
            "pre_roll_ms": self.pre_roll_ms,
            "post_roll_ms": self.post_roll_ms,
            "planned_frame_count": self.planned_frame_count,
            "requested_frame_count": self.requested_frame_count,
            "timing_provenance": self.timing_provenance,
        }
        if self.enabled:
            payload.update(
                {
                    "requested_clip": {
                        "start_ms": self.requested_start_ms,
                        "end_ms": self.requested_end_ms,
                    },
                    "decoded_range": {
                        "start_ms": self.decoded_start_ms,
                        "end_ms": self.decoded_end_ms,
                    },
                    "requested_frame_range": {
                        "start": self.requested_start_frame,
                        "end": self.requested_end_frame,
                    },
                    "decoded_frame_range": {
                        "start": self.decoded_start_frame,
                        "end": self.decoded_end_frame,
                    },
                }
            )
        return payload


def resolve_analysis_window(
    *,
    source_duration_ms: int,
    source_frame_count: int,
    fps: float,
    clip_start_ms: int | None,
    clip_end_ms: int | None,
    pre_roll_ms: int = 1500,
    post_roll_ms: int = 500,
    timing_provider: "FrameTimingProvider | None" = None,
) -> AnalysisWindow:
    """Validate and resolve a clip without ever silently falling back to full video."""
    if fps <= 0:
        raise AnalysisWindowError("视频帧率无效，无法解析分析窗口")
    if source_frame_count < 0 or source_duration_ms < 0:
        raise AnalysisWindowError("视频元数据无效，无法解析分析窗口")
    if (clip_start_ms is None) != (clip_end_ms is None):
        raise AnalysisWindowError("clipStartMs 与 clipEndMs 必须同时提供")
    if clip_start_ms is None:
        return AnalysisWindow(
            requested_start_ms=None,
            requested_end_ms=None,
            decoded_start_ms=0,
            decoded_end_ms=source_duration_ms,
            source_duration_ms=source_duration_ms,
            source_frame_count=source_frame_count,
            fps=fps,
            requested_start_frame=None,
            requested_end_frame=None,
            decoded_start_frame=0,
            decoded_end_frame=source_frame_count,
            pre_roll_ms=pre_roll_ms,
            post_roll_ms=post_roll_ms,
            timing_provenance=timing_provider.metadata() if timing_provider is not None else None,
        )

    assert clip_end_ms is not None
    if clip_start_ms < 0 or clip_end_ms <= clip_start_ms:
        raise AnalysisWindowError(f"无效 clip 范围: [{clip_start_ms}, {clip_end_ms})")
    if clip_start_ms >= source_duration_ms or source_frame_count == 0:
        raise AnalysisWindowError(
            f"clip 范围不包含视频有效帧: [{clip_start_ms}, {clip_end_ms}) / duration={source_duration_ms}ms"
        )

    decode_start_ms = max(0, clip_start_ms - max(0, pre_roll_ms))
    decode_end_ms = min(source_duration_ms, clip_end_ms + max(0, post_roll_ms))
    if timing_provider is not None and timing_provider.frames:
        requested_start_frame = timing_provider.frame_index_at_or_after_take_time(clip_start_ms / 1000.0)
        requested_end_frame = timing_provider.frame_index_at_or_after_take_time(clip_end_ms / 1000.0)
        decoded_start_frame = timing_provider.frame_index_at_or_after_take_time(decode_start_ms / 1000.0)
        decoded_end_frame = timing_provider.frame_index_at_or_after_take_time(decode_end_ms / 1000.0)
        requested_start_frame = 0 if requested_start_frame is None else requested_start_frame
        requested_end_frame = source_frame_count if requested_end_frame is None else requested_end_frame
        decoded_start_frame = 0 if decoded_start_frame is None else decoded_start_frame
        decoded_end_frame = source_frame_count if decoded_end_frame is None else decoded_end_frame
    else:
        requested_start_frame = min(source_frame_count, max(0, ceil(clip_start_ms / 1000.0 * fps)))
        requested_end_frame = min(source_frame_count, max(0, ceil(clip_end_ms / 1000.0 * fps)))
        decoded_start_frame = min(source_frame_count, max(0, floor(decode_start_ms / 1000.0 * fps)))
        decoded_end_frame = min(source_frame_count, max(0, ceil(decode_end_ms / 1000.0 * fps)))
    if requested_end_frame <= requested_start_frame or decoded_end_frame <= decoded_start_frame:
        raise AnalysisWindowError(
            f"clip 范围无法映射为正向 frame range: [{clip_start_ms}, {clip_end_ms})"
        )
    return AnalysisWindow(
        requested_start_ms=clip_start_ms,
        requested_end_ms=clip_end_ms,
        decoded_start_ms=decode_start_ms,
        decoded_end_ms=decode_end_ms,
        source_duration_ms=source_duration_ms,
        source_frame_count=source_frame_count,
        fps=fps,
        requested_start_frame=requested_start_frame,
        requested_end_frame=requested_end_frame,
        decoded_start_frame=decoded_start_frame,
        decoded_end_frame=decoded_end_frame,
        pre_roll_ms=max(0, pre_roll_ms),
        post_roll_ms=max(0, post_roll_ms),
        timing_provenance=timing_provider.metadata() if timing_provider is not None else None,
    )
