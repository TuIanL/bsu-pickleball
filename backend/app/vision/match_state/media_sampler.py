"""Production RGB sampling from CaptureTrack media on the canonical take clock.

This module is deliberately independent from the training/candidate scripts.
It only turns authoritative frame timing plus a measured affine sync mapping
into model-ready ``[camera, time, channel, height, width]`` samples.  The
runtime can still accept a signed probability sidecar for restart-safe replay,
but raw production inference uses this sampler instead of an RGB JPEG cache.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from collections import Counter
from typing import Any, Iterator

from app.services.dual_camera_sync import SyncCalibration
from app.services.frame_timing_provider import FrameTimingProvider

from .sampler import MatchStateSynchronizedSampler


@dataclass(frozen=True)
class RGBMediaSamplingConfig:
    sampling_fps: float = 2.0
    # ``sampling_fps`` describes the frame rate inside each encoder clip.
    # Timeline inference uses a separate stride so a 12 FPS model does not
    # accidentally trigger 12 full R3D evaluations per second of video.
    timeline_stride_ms: int = 500
    clip_duration_ms: int = 4000
    encoder_frame_count: int = 16
    height: int = 112
    width: int = 112
    mean: tuple[float, float, float] = (0.43216, 0.394666, 0.37645)
    std: tuple[float, float, float] = (0.22803, 0.22145, 0.216989)

    @classmethod
    def from_contract(cls, contract: dict[str, Any]) -> "RGBMediaSamplingConfig":
        normalization = contract.get("normalization")
        normalization = normalization if isinstance(normalization, dict) else {}
        mean = normalization.get("mean", cls.mean)
        std = normalization.get("std", cls.std)
        if not isinstance(mean, (list, tuple)) or len(mean) != 3:
            mean = cls.mean
        if not isinstance(std, (list, tuple)) or len(std) != 3:
            std = cls.std
        return cls(
            sampling_fps=max(0.1, float(contract.get("sampling_fps", cls.sampling_fps))),
            timeline_stride_ms=max(1, int(contract.get("timeline_stride_ms", cls.timeline_stride_ms))),
            clip_duration_ms=max(1, int(contract.get("clip_duration_ms", cls.clip_duration_ms))),
            encoder_frame_count=max(1, int(contract.get("encoder_frame_count", cls.encoder_frame_count))),
            height=max(1, int(contract.get("height", cls.height))),
            width=max(1, int(contract.get("width", cls.width))),
            mean=tuple(float(value) for value in mean),
            std=tuple(float(value) for value in std),
        )

    @property
    def stride_ms(self) -> int:
        return self.timeline_stride_ms


def sample_capture_take_media(
    *,
    reference_media_path: str | Path,
    secondary_media_path: str | Path,
    reference_timing: FrameTimingProvider,
    secondary_timing: FrameTimingProvider,
    sync_calibration: SyncCalibration,
    start_ms: int,
    end_ms: int,
    sync_calibration_revision: int,
    config: RGBMediaSamplingConfig | None = None,
    max_gap_ms: int = 250,
) -> tuple[dict[str, Any], ...]:
    """Materialize the production stream for callers that need a finite tuple.

    The formal executor uses :func:`iter_capture_take_media` directly so a
    long CaptureTake never accumulates every RGB tensor in RAM.  Keeping this
    wrapper preserves the small, convenient API used by tests and offline
    tooling.
    """
    return tuple(
        iter_capture_take_media(
            reference_media_path=reference_media_path,
            secondary_media_path=secondary_media_path,
            reference_timing=reference_timing,
            secondary_timing=secondary_timing,
            sync_calibration=sync_calibration,
            start_ms=start_ms,
            end_ms=end_ms,
            sync_calibration_revision=sync_calibration_revision,
            config=config,
            max_gap_ms=max_gap_ms,
        )
    )


def iter_capture_take_media(
    *,
    reference_media_path: str | Path,
    secondary_media_path: str | Path,
    reference_timing: FrameTimingProvider,
    secondary_timing: FrameTimingProvider,
    sync_calibration: SyncCalibration,
    start_ms: int,
    end_ms: int,
    sync_calibration_revision: int,
    config: RGBMediaSamplingConfig | None = None,
    max_gap_ms: int = 250,
) -> Iterator[dict[str, Any]]:
    """Yield model-ready rows while decoding one CaptureTake sequentially.

    Only the bounded clip cache lives at any point in time.  The caller can
    feed each yielded row to a small inference batch and release its tensor
    before the next rows are decoded.
    """
    """Read both CaptureTrack streams using measured PTS/sync calibration.

    Missing frames are retained as low-coverage rows for diagnostics; the
    formal runtime's evidence gate decides whether the run is publishable.
    """
    if end_ms <= start_ms:
        return
    config = config or RGBMediaSamplingConfig()
    sampler = MatchStateSynchronizedSampler(
        reference_timing,
        secondary_timing,
        sync_calibration_revision=sync_calibration_revision,
        secondary_offset_ms=int(round(sync_calibration.offset_ms)),
        secondary_rate=sync_calibration.rate,
        max_gap_ms=max_gap_ms,
    )
    ticks = sampler.sample(start_ms=start_ms, end_ms=end_ms, stride_ms=config.stride_ms)
    try:
        import cv2  # type: ignore
        import numpy as np
    except Exception as exc:  # pragma: no cover - deployment dependency
        raise RuntimeError(f"RGB media sampler dependencies unavailable: {exc}") from exc

    captures = [cv2.VideoCapture(str(reference_media_path)), cv2.VideoCapture(str(secondary_media_path))]
    # ``VideoCapture.set(POS_FRAMES, ...)`` for every frame in every clip is
    # prohibitively expensive on long MP4 files: each seek may decode a large
    # GOP again.  Keep one sequential reader per camera and a bounded cache of
    # resized frames.  The 4-second clip window means the next timeline tick
    # only needs roughly ``clip_duration * fps`` frames from the previous tick;
    # older frames can be evicted without changing the sampled PTS or model
    # tensor contract.
    readers = [
        _SequentialFrameReader(capture, config, cv2, np, timing, requested_indices=requests)
        for capture, timing, requests in zip(
            captures,
            (reference_timing, secondary_timing),
            (_requested_clip_frames(ticks, "reference_frame", config, reference_timing, np),
             _requested_clip_frames(ticks, "secondary_frame", config, secondary_timing, np)),
            strict=True,
        )
    ]
    try:
        if not all(capture.isOpened() for capture in captures):
            raise OSError("无法打开双摄 CaptureTrack 媒体")
        for tick in ticks:
            row: dict[str, Any] = tick.to_dict()
            row["center_ms"] = tick.timestamp_ms
            if tick.reference_frame is None or tick.secondary_frame is None:
                yield row
                continue
            reference_clip = readers[0].read_clip(tick.reference_frame)
            secondary_clip = readers[1].read_clip(tick.secondary_frame)
            if reference_clip is None or secondary_clip is None:
                yield row
                continue
            row["model_input"] = np.stack([reference_clip, secondary_clip], axis=0)
            row["coverage"] = 1.0
            yield row
    finally:
        for capture in captures:
            capture.release()


class _SequentialFrameReader:
    """Sequential MP4 decoder with a small preprocessed-frame ring buffer."""

    def __init__(self, capture, config: RGBMediaSamplingConfig, cv2, np, timing, *, requested_indices: Counter) -> None:
        self.capture = capture
        self.config = config
        self.cv2 = cv2
        self.np = np
        self.fps = float(timing.fps or 0.0)
        self.current_frame = -1
        half_frames = max(0, int(round(config.clip_duration_ms / 1000.0 * self.fps / 2.0)))
        self.cache_limit = max(32, half_frames * 2 + 32)
        self.cache: dict[int, Any] = {}
        # Number of future clip references for each source-frame index.  This
        # lets the sequential decoder preprocess only requested frames and
        # release each cached tensor immediately after its final use.
        self.requested_indices = requested_indices
        self.mean = np.asarray(config.mean, dtype=np.float32)
        self.std = np.asarray(config.std, dtype=np.float32)

    def read_clip(self, center_frame: int) -> Any | None:
        if self.fps <= 0:
            return None
        half_frames = max(0, int(round(self.config.clip_duration_ms / 1000.0 * self.fps / 2.0)))
        start = max(0, int(center_frame) - half_frames)
        stop = int(center_frame) + half_frames
        frame_indices = self.np.linspace(start, stop, self.config.encoder_frame_count).round().astype(int)
        if not self._advance_to(int(frame_indices.max())):
            return None
        frames = [self.cache.get(int(frame_index)) for frame_index in frame_indices]
        if any(frame is None for frame in frames):
            # This should only happen when a source has a large discontinuity;
            # report an unusable sample instead of silently seeking by seconds.
            return None
        for frame_index in frame_indices:
            index = int(frame_index)
            remaining = int(self.requested_indices.get(index, 0)) - 1
            if remaining > 0:
                self.requested_indices[index] = remaining
            else:
                self.requested_indices.pop(index, None)
                self.cache.pop(index, None)
        return self.np.stack(frames, axis=0).astype(self.np.float32, copy=False)

    def _advance_to(self, target_frame: int) -> bool:
        if target_frame <= self.current_frame:
            return True
        while self.current_frame < target_frame:
            ok, frame = self.capture.read()
            self.current_frame += 1
            if not ok or frame is None:
                return False
            if self.current_frame not in self.requested_indices:
                continue
            frame = self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2RGB)
            frame = self.cv2.resize(
                frame,
                (self.config.width, self.config.height),
                interpolation=self.cv2.INTER_AREA,
            )
            value = frame.astype(self.np.float32) / 255.0
            value = (value - self.mean) / self.std
            self.cache[self.current_frame] = self.np.transpose(value, (2, 0, 1)).astype(
                self.np.float32,
                copy=False,
            )
            evict_before = self.current_frame - self.cache_limit
            if evict_before > 0:
                for index in tuple(self.cache):
                    if index < evict_before:
                        del self.cache[index]
        return True


def _requested_clip_frames(ticks, frame_key: str, config: RGBMediaSamplingConfig, timing, np) -> Counter:
    """Count every source-frame index needed by the complete tick sequence."""
    fps = float(timing.fps or 0.0)
    requests: Counter = Counter()
    if fps <= 0:
        return requests
    half_frames = max(0, int(round(config.clip_duration_ms / 1000.0 * fps / 2.0)))
    for tick in ticks:
        center = getattr(tick, frame_key)
        if center is None:
            continue
        start = max(0, int(center) - half_frames)
        stop = int(center) + half_frames
        frame_indices = np.linspace(start, stop, config.encoder_frame_count).round().astype(int)
        requests.update(int(index) for index in frame_indices)
    return requests
