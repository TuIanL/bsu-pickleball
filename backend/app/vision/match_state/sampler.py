"""Canonical-time sampler for the two CaptureTrack streams."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.frame_timing_provider import FrameTimingProvider


@dataclass(frozen=True)
class SynchronizedSample:
    timestamp_ms: int
    reference_frame: int | None
    secondary_frame: int | None
    view_mask: tuple[str, ...]
    coverage: float
    sync_calibration_revision: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp_ms": self.timestamp_ms,
            "reference_frame": self.reference_frame,
            "secondary_frame": self.secondary_frame,
            "view_mask": list(self.view_mask),
            "coverage": self.coverage,
            "sync_calibration_revision": self.sync_calibration_revision,
        }


class MatchStateSynchronizedSampler:
    """Map public take timestamps to both camera frame addresses.

    ``secondary_offset_ms`` is intentionally explicit and is only a fallback
    for a previously measured calibration.  Callers must pass a revision;
    missing calibration is rejected instead of assuming equal wall-clock time.
    """

    def __init__(
        self,
        reference: FrameTimingProvider,
        secondary: FrameTimingProvider,
        *,
        sync_calibration_revision: int | None,
        secondary_offset_ms: int = 0,
        secondary_rate: float = 1.0,
        max_gap_ms: int = 250,
    ) -> None:
        if sync_calibration_revision is None:
            raise ValueError("sync_calibration_revision is required for formal dual-camera sampling")
        if secondary_rate <= 0:
            raise ValueError("secondary_rate must be positive")
        if max_gap_ms < 0:
            raise ValueError("max_gap_ms must be non-negative")
        self.reference = reference
        self.secondary = secondary
        self.sync_calibration_revision = sync_calibration_revision
        self.secondary_offset_ms = secondary_offset_ms
        self.secondary_rate = float(secondary_rate)
        self.max_gap_ms = max_gap_ms

    def sample(self, *, start_ms: int, end_ms: int, stride_ms: int) -> tuple[SynchronizedSample, ...]:
        if end_ms <= start_ms or stride_ms <= 0:
            raise ValueError("sampling range and stride must be positive")
        result: list[SynchronizedSample] = []
        for timestamp_ms in range(start_ms, end_ms, stride_ms):
            reference_time = timestamp_ms / 1000.0
            # CaptureTake sync calibration is camera_time = offset + rate *
            # reference_time. Applying the measured rate here prevents long
            # takes from accumulating PTS drift between the two views.
            secondary_timestamp_ms = self.secondary_offset_ms + self.secondary_rate * timestamp_ms
            secondary_time = secondary_timestamp_ms / 1000.0
            ref = self.reference.nearest_take_frame(reference_time)
            sec = self.secondary.nearest_take_frame(secondary_time)
            view_mask: list[str] = []
            if ref is not None and abs((self.reference.take_timestamp_for_frame(ref.frame_index) or 0) * 1000 - timestamp_ms) <= self.max_gap_ms:
                view_mask.append("cam_1")
            else:
                ref = None
            if sec is not None and abs((self.secondary.take_timestamp_for_frame(sec.frame_index) or 0) * 1000 - secondary_timestamp_ms) <= self.max_gap_ms:
                view_mask.append("cam_2")
            else:
                sec = None
            result.append(
                SynchronizedSample(
                    timestamp_ms=timestamp_ms,
                    reference_frame=ref.frame_index if ref is not None else None,
                    secondary_frame=sec.frame_index if sec is not None else None,
                    view_mask=tuple(view_mask),
                    coverage=len(view_mask) / 2.0,
                    sync_calibration_revision=self.sync_calibration_revision,
                )
            )
        return tuple(result)
