"""Versioned cross-camera appearance normalization with fail-closed confidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from app.vision.player_tracking_engine.player_appearance import PlayerAppearanceDescriptor


PROFILE_VERSION = "descriptor-affine.v1"


@dataclass(frozen=True)
class CameraColorProfile:
    source_view: str
    target_view: str
    scale: tuple[float, ...]
    bias: tuple[float, ...]
    sample_count: int
    residual: float
    confidence: float
    version: str = PROFILE_VERSION

    @property
    def available(self) -> bool:
        return self.sample_count >= 4 and self.confidence >= 0.55 and self.residual <= 0.25

    def transform(self, vector: np.ndarray) -> np.ndarray | None:
        if not self.available or vector.size != len(self.scale):
            return None
        return vector * np.asarray(self.scale, dtype=np.float32) + np.asarray(self.bias, dtype=np.float32)

    def diagnostics(self) -> dict[str, object]:
        return {
            "version": self.version,
            "source_view": self.source_view,
            "target_view": self.target_view,
            "sample_count": self.sample_count,
            "residual": self.residual,
            "confidence": self.confidence,
            "available": self.available,
        }


def estimate_camera_color_profile(
    *,
    source_view: str,
    target_view: str,
    paired_descriptors: Sequence[tuple[PlayerAppearanceDescriptor, PlayerAppearanceDescriptor]],
) -> CameraColorProfile:
    source_vectors: list[np.ndarray] = []
    target_vectors: list[np.ndarray] = []
    for source, target in paired_descriptors:
        source_vector, target_vector = source.vector(), target.vector()
        if source_vector is None or target_vector is None or source_vector.shape != target_vector.shape:
            continue
        if source.quality.score < 0.25 or target.quality.score < 0.25:
            continue
        source_vectors.append(source_vector)
        target_vectors.append(target_vector)
    if not source_vectors:
        return CameraColorProfile(source_view, target_view, (), (), 0, 1.0, 0.0)
    source_matrix = np.stack(source_vectors)
    target_matrix = np.stack(target_vectors)
    source_mean = np.median(source_matrix, axis=0)
    target_mean = np.median(target_matrix, axis=0)
    source_scale = np.std(source_matrix, axis=0)
    target_scale = np.std(target_matrix, axis=0)
    affine_scale = np.clip(target_scale / np.maximum(source_scale, 1e-3), 0.5, 2.0)
    affine_bias = target_mean - source_mean * affine_scale
    transformed = source_matrix * affine_scale + affine_bias
    residual = float(np.mean(np.linalg.norm(transformed - target_matrix, axis=1) / np.sqrt(source_matrix.shape[1])))
    sample_factor = min(1.0, len(source_vectors) / 12.0)
    confidence = max(0.0, min(1.0, sample_factor * (1.0 - residual / 0.35)))
    return CameraColorProfile(
        source_view=source_view,
        target_view=target_view,
        scale=tuple(float(value) for value in affine_scale),
        bias=tuple(float(value) for value in affine_bias),
        sample_count=len(source_vectors),
        residual=residual,
        confidence=confidence,
    )


def calibrated_descriptor_distance(
    source: PlayerAppearanceDescriptor | None,
    target: PlayerAppearanceDescriptor | None,
    profile: CameraColorProfile | None,
) -> float | None:
    if source is None or target is None or profile is None or not profile.available:
        return None
    source_vector, target_vector = source.vector(), target.vector()
    if source_vector is None or target_vector is None:
        return None
    transformed = profile.transform(source_vector)
    if transformed is None or transformed.shape != target_vector.shape:
        return None
    return max(0.0, min(1.0, float(np.linalg.norm(transformed - target_vector) / np.sqrt(transformed.size))))
