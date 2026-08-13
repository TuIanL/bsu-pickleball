"""Versioned source timing authority for decoded media.

Frame index remains the seek/provenance address. Elapsed time comes from source
PTS when a sidecar is available; nominal FPS is an explicit compatibility mode.
"""

from __future__ import annotations

import math
from bisect import bisect_left
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.services.dual_camera_sync import FrameTiming, read_frame_timing_sidecar

FRAME_TIMING_PROVIDER_SCHEMA_VERSION = "frame_timing_provider.v1"
TimingAuthority = Literal["source_pts", "legacy_nominal_fps", "missing"]


@dataclass(frozen=True)
class TimingProvenance:
    schema_version: str = FRAME_TIMING_PROVIDER_SCHEMA_VERSION
    authority: TimingAuthority = "missing"
    media_path: str | None = None
    sidecar_path: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "authority": self.authority,
            "media_path": self.media_path,
            "sidecar_path": self.sidecar_path,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class FrameTimingProvider:
    """Immutable lookup table mapping source frames to source/canonical time."""

    frames: tuple[FrameTiming, ...]
    provenance: TimingProvenance
    fps: float | None = None

    @classmethod
    def from_sidecar(
        cls,
        sidecar_path: str | Path,
        *,
        media_path: str | Path | None = None,
    ) -> "FrameTimingProvider":
        sidecar = Path(sidecar_path)
        frames = tuple(_validated_frames(read_frame_timing_sidecar(sidecar)))
        if not frames:
            raise ValueError(f"PTS sidecar contains no usable frames: {sidecar}")
        fps = _estimate_fps(frames)
        return cls(
            frames=frames,
            provenance=TimingProvenance(
                authority="source_pts",
                media_path=str(media_path) if media_path is not None else None,
                sidecar_path=str(sidecar),
            ),
            fps=fps,
        )

    @classmethod
    def nominal(
        cls,
        *,
        frame_count: int,
        fps: float,
        media_path: str | Path | None = None,
        reason: str = "PTS sidecar unavailable; using historical frame_index/fps compatibility",
    ) -> "FrameTimingProvider":
        if frame_count < 0 or fps <= 0:
            raise ValueError("frame_count must be non-negative and fps must be positive")
        frames = tuple(FrameTiming(index, index / fps) for index in range(frame_count))
        authority: TimingAuthority = "legacy_nominal_fps" if frames else "missing"
        return cls(
            frames=frames,
            provenance=TimingProvenance(
                authority=authority,
                media_path=str(media_path) if media_path is not None else None,
                reason=reason,
            ),
            fps=fps,
        )

    @classmethod
    def missing(
        cls,
        *,
        media_path: str | Path | None = None,
        sidecar_path: str | Path | None = None,
        reason: str = "source PTS sidecar unavailable",
    ) -> "FrameTimingProvider":
        """Represent unavailable timing without inventing frame timestamps."""
        return cls(
            frames=(),
            provenance=TimingProvenance(
                authority="missing",
                media_path=str(media_path) if media_path is not None else None,
                sidecar_path=str(sidecar_path) if sidecar_path is not None else None,
                reason=reason,
            ),
            fps=None,
        )

    @classmethod
    def from_media(
        cls,
        media_path: str | Path,
        *,
        frame_count: int,
        fps: float,
        sidecar_path: str | Path | None = None,
        allow_nominal_fallback: bool = True,
    ) -> "FrameTimingProvider":
        media = Path(media_path)
        sidecar = Path(sidecar_path) if sidecar_path is not None else Path(f"{media}.pts.jsonl")
        sidecar_error: str | None = None
        if sidecar.exists():
            try:
                return cls.from_sidecar(sidecar, media_path=media)
            except (OSError, ValueError, TypeError) as exc:
                sidecar_error = f"PTS sidecar unreadable or invalid: {exc}"
        if not allow_nominal_fallback:
            return cls.missing(
                media_path=media,
                sidecar_path=sidecar,
                reason=sidecar_error
                or "PTS sidecar unavailable; nominal FPS fallback disabled for authoritative joint analysis",
            )
        return cls.nominal(
            frame_count=frame_count,
            fps=fps,
            media_path=media,
            reason=sidecar_error
            or "PTS sidecar unavailable; using historical frame_index/fps compatibility",
        )

    @property
    def is_source_pts(self) -> bool:
        return self.provenance.authority == "source_pts"

    @property
    def first_timestamp_seconds(self) -> float | None:
        return self.frames[0].pts_seconds if self.frames else None

    @property
    def last_timestamp_seconds(self) -> float | None:
        return self.frames[-1].pts_seconds if self.frames else None

    @property
    def duration_seconds(self) -> float:
        if not self.frames:
            return 0.0
        if len(self.frames) == 1:
            return 1.0 / self.fps if self.fps and self.fps > 0 else 0.0
        step = self.frames[-1].pts_seconds - self.frames[-2].pts_seconds
        return max(0.0, self.frames[-1].pts_seconds - self.frames[0].pts_seconds + max(0.0, step))

    def timing_for_frame(self, frame_index: int) -> FrameTiming | None:
        for frame in self.frames:
            if frame.frame_index == frame_index:
                return frame
        return None

    def timestamp_for_frame(self, frame_index: int) -> float | None:
        frame = self.timing_for_frame(frame_index)
        return frame.pts_seconds if frame is not None else None

    def take_timestamp_for_frame(self, frame_index: int) -> float | None:
        """Return PTS normalized to the first source frame of this media."""
        timestamp = self.timestamp_for_frame(frame_index)
        first = self.first_timestamp_seconds
        return None if timestamp is None or first is None else timestamp - first

    def frames_with_origin(self, origin_seconds: float | None = None) -> tuple[FrameTiming, ...]:
        """Return timing rows normalized to a shared take origin."""
        origin = self.first_timestamp_seconds if origin_seconds is None else origin_seconds
        if origin is None:
            return self.frames
        return tuple(
            FrameTiming(
                frame_index=frame.frame_index,
                pts_seconds=frame.pts_seconds - origin,
                dts_seconds=None if frame.dts_seconds is None else frame.dts_seconds - origin,
                keyframe=frame.keyframe,
            )
            for frame in self.frames
        )

    def frame_index_at_or_after(self, timestamp_seconds: float) -> int | None:
        if not self.frames:
            return None
        timestamps = [frame.pts_seconds for frame in self.frames]
        position = min(len(self.frames) - 1, bisect_left(timestamps, timestamp_seconds))
        return self.frames[position].frame_index

    def frame_index_at_or_after_take_time(self, timestamp_seconds: float) -> int | None:
        first = self.first_timestamp_seconds
        return self.frame_index_at_or_after(timestamp_seconds + (first or 0.0))

    def nearest_frame(self, timestamp_seconds: float) -> FrameTiming | None:
        if not self.frames:
            return None
        position = bisect_left([frame.pts_seconds for frame in self.frames], timestamp_seconds)
        candidates = self.frames[max(0, position - 1) : min(len(self.frames), position + 1)]
        return min(candidates, key=lambda frame: abs(frame.pts_seconds - timestamp_seconds))

    def nearest_take_frame(self, timestamp_seconds: float) -> FrameTiming | None:
        first = self.first_timestamp_seconds
        return self.nearest_frame(timestamp_seconds + (first or 0.0))

    def metadata(self) -> dict[str, object]:
        return {
            **self.provenance.to_dict(),
            "frame_count": len(self.frames),
            "fps": self.fps,
            "first_pts_seconds": self.first_timestamp_seconds,
            "last_pts_seconds": self.last_timestamp_seconds,
            "duration_seconds": self.duration_seconds,
        }


def _estimate_fps(frames: tuple[FrameTiming, ...]) -> float | None:
    if len(frames) < 2:
        return None
    duration = frames[-1].pts_seconds - frames[0].pts_seconds
    return (len(frames) - 1) / duration if duration > 0 else None


def _validated_frames(frames: list[FrameTiming]) -> list[FrameTiming]:
    """Reject ambiguous sidecars before they become the timing authority."""
    previous_index = -1
    previous_pts: float | None = None
    for frame in frames:
        if frame.frame_index < 0 or frame.frame_index <= previous_index:
            raise ValueError("frame indices must be strictly increasing")
        if not math.isfinite(frame.pts_seconds):
            raise ValueError("PTS values must be finite")
        if frame.dts_seconds is not None and not math.isfinite(frame.dts_seconds):
            raise ValueError("DTS values must be finite")
        if previous_pts is not None and frame.pts_seconds < previous_pts:
            raise ValueError("PTS values must be monotonically non-decreasing")
        previous_index = frame.frame_index
        previous_pts = frame.pts_seconds
    return frames
