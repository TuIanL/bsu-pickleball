"""Helpers for source FPS normalization and time-window conversion."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

DEFAULT_ANALYSIS_FPS = 30.0


@dataclass(frozen=True)
class EffectiveFps:
    effective_fps: float
    fps_source: str
    user_source_fps: float | None = None
    metadata_fps: float | None = None

    def diagnostics(self) -> dict[str, float | str | None]:
        return {
            "effective_fps": self.effective_fps,
            "fps_source": self.fps_source,
            "user_source_fps": self.user_source_fps,
            "metadata_fps": self.metadata_fps,
        }


def valid_fps(value: float | int | None) -> float | None:
    if value is None:
        return None
    try:
        fps = float(value)
    except (TypeError, ValueError):
        return None
    return fps if isfinite(fps) and fps > 0 else None


def resolve_effective_fps(user_source_fps: float | int | None, metadata_fps: float | int | None) -> EffectiveFps:
    user_fps = valid_fps(user_source_fps)
    meta_fps = valid_fps(metadata_fps)
    if user_fps is not None:
        return EffectiveFps(user_fps, "user_override", user_source_fps=user_fps, metadata_fps=meta_fps)
    if meta_fps is not None:
        return EffectiveFps(meta_fps, "metadata", user_source_fps=None, metadata_fps=meta_fps)
    return EffectiveFps(DEFAULT_ANALYSIS_FPS, "fallback", user_source_fps=None, metadata_fps=None)


def frames_for_seconds(seconds: float | int | None, fps: float | int | None, *, minimum: int = 1) -> int:
    try:
        seconds_value = float(seconds if seconds is not None else 0.0)
    except (TypeError, ValueError):
        seconds_value = 0.0
    fps_value = valid_fps(fps) or DEFAULT_ANALYSIS_FPS
    return max(int(minimum), int(round(max(0.0, seconds_value) * fps_value)))
