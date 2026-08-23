"""Explainable clothing appearance descriptors for player identity soft evidence."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Literal, Protocol, Sequence

import cv2
import numpy as np


EXTRACTOR_VERSION = "clothing-hsv-lab.v1"
AppearanceStatus = Literal["available", "low_quality", "unavailable"]


@dataclass(frozen=True)
class AppearanceRegionFeature:
    histogram: tuple[float, ...]
    moments: tuple[float, ...]
    texture: tuple[float, ...] = ()

    def vector(self) -> np.ndarray:
        return np.asarray(self.histogram + self.moments + self.texture, dtype=np.float32)


@dataclass(frozen=True)
class AppearanceQuality:
    clipping_ratio: float
    valid_pixels: int
    blur_score: float
    brightness: float
    saturation: float
    occlusion_ratio: float
    score: float
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlayerAppearanceDescriptor:
    upper: AppearanceRegionFeature | None
    lower: AppearanceRegionFeature | None
    quality: AppearanceQuality
    status: AppearanceStatus
    extractor_version: str = EXTRACTOR_VERSION
    provenance: Literal["base", "roi_recovery"] = "base"
    partition_method: Literal["pose", "bbox_relative"] = "bbox_relative"

    def vector(self) -> np.ndarray | None:
        if self.status != "available" or self.upper is None or self.lower is None:
            return None
        return np.concatenate([self.upper.vector(), self.lower.vector()])


class PlayerAppearanceExtractor(Protocol):
    version: str

    def extract(
        self,
        frame: np.ndarray,
        bbox: Sequence[float],
        *,
        provenance: Literal["base", "roi_recovery"],
        keypoints: Sequence[Sequence[float]] | None = None,
    ) -> PlayerAppearanceDescriptor: ...


@dataclass(frozen=True)
class AppearanceExtractorConfig:
    min_bbox_width: int = 18
    min_bbox_height: int = 48
    min_valid_pixels_per_region: int = 80
    min_blur_variance: float = 12.0
    min_brightness: float = 18.0
    max_brightness: float = 242.0
    edge_inset_ratio: float = 0.10
    skin_mask_enabled: bool = True
    texture_enabled: bool = True


class ClothingAppearanceExtractor:
    version = EXTRACTOR_VERSION

    def __init__(self, config: AppearanceExtractorConfig | None = None) -> None:
        self.config = config or AppearanceExtractorConfig()

    def extract(
        self,
        frame: np.ndarray,
        bbox: Sequence[float],
        *,
        provenance: Literal["base", "roi_recovery"],
        keypoints: Sequence[Sequence[float]] | None = None,
    ) -> PlayerAppearanceDescriptor:
        if provenance not in {"base", "roi_recovery"}:
            return _unavailable("non_detector_provenance", provenance="base")
        if not isinstance(frame, np.ndarray) or frame.ndim != 3 or frame.shape[2] < 3 or len(bbox) < 4:
            return _unavailable("invalid_frame_or_bbox", provenance=provenance)
        height, width = frame.shape[:2]
        raw_x1, raw_y1, raw_x2, raw_y2 = (float(value) for value in bbox[:4])
        raw_area = max(1.0, (raw_x2 - raw_x1) * (raw_y2 - raw_y1))
        x1, y1 = max(0, round(raw_x1)), max(0, round(raw_y1))
        x2, y2 = min(width, round(raw_x2)), min(height, round(raw_y2))
        clipped_area = max(0, x2 - x1) * max(0, y2 - y1)
        clipping_ratio = max(0.0, min(1.0, 1.0 - clipped_area / raw_area))
        if x2 - x1 < self.config.min_bbox_width or y2 - y1 < self.config.min_bbox_height:
            return _unavailable("bbox_too_small", clipping_ratio=clipping_ratio, provenance=provenance)

        partition_method: Literal["pose", "bbox_relative"] = "bbox_relative"
        pose_regions = _pose_regions(keypoints, (x1, y1, x2, y2))
        if pose_regions is not None:
            upper_box, lower_box = pose_regions
            partition_method = "pose"
        else:
            box_height = y2 - y1
            inset = round((x2 - x1) * self.config.edge_inset_ratio)
            upper_box = (x1 + inset, round(y1 + 0.20 * box_height), x2 - inset, round(y1 + 0.55 * box_height))
            lower_box = (x1 + inset, round(y1 + 0.55 * box_height), x2 - inset, round(y1 + 0.90 * box_height))

        upper_feature, upper_stats = self._region(frame, upper_box)
        lower_feature, lower_stats = self._region(frame, lower_box)
        valid_pixels = upper_stats["valid_pixels"] + lower_stats["valid_pixels"]
        blur = min(upper_stats["blur"], lower_stats["blur"])
        brightness = (upper_stats["brightness"] + lower_stats["brightness"]) / 2.0
        saturation = (upper_stats["saturation"] + lower_stats["saturation"]) / 2.0
        reasons: list[str] = []
        if clipping_ratio > 0.25:
            reasons.append("bbox_clipped")
        if upper_feature is None or lower_feature is None:
            reasons.append("insufficient_valid_pixels")
        if blur < self.config.min_blur_variance:
            reasons.append("blurred")
        if brightness < self.config.min_brightness:
            reasons.append("too_dark")
        if brightness > self.config.max_brightness:
            reasons.append("overexposed")
        pixel_score = min(1.0, valid_pixels / (4.0 * self.config.min_valid_pixels_per_region))
        blur_score = (
            1.0
            if self.config.min_blur_variance <= 0
            else min(1.0, blur / (self.config.min_blur_variance * 4.0))
        )
        exposure_score = 1.0 if self.config.min_brightness <= brightness <= self.config.max_brightness else 0.0
        score = max(0.0, min(1.0, pixel_score * blur_score * exposure_score * (1.0 - clipping_ratio)))
        quality = AppearanceQuality(
            clipping_ratio=clipping_ratio,
            valid_pixels=valid_pixels,
            blur_score=blur,
            brightness=brightness,
            saturation=saturation,
            occlusion_ratio=0.0,
            score=score,
            reasons=tuple(reasons),
        )
        status: AppearanceStatus = "available" if not reasons and score >= 0.25 else "low_quality"
        return PlayerAppearanceDescriptor(
            upper=upper_feature,
            lower=lower_feature,
            quality=quality,
            status=status,
            provenance=provenance,
            partition_method=partition_method,
        )

    def _region(
        self,
        frame: np.ndarray,
        box: tuple[int, int, int, int],
    ) -> tuple[AppearanceRegionFeature | None, dict[str, float | int]]:
        x1, y1, x2, y2 = box
        crop = frame[max(0, y1):max(0, y2), max(0, x1):max(0, x2), :3]
        if crop.size == 0:
            return None, {"valid_pixels": 0, "blur": 0.0, "brightness": 0.0, "saturation": 0.0}
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB)
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        valid = np.ones(crop.shape[:2], dtype=np.uint8) * 255
        if self.config.skin_mask_enabled:
            ycrcb = cv2.cvtColor(crop, cv2.COLOR_BGR2YCrCb)
            skin = cv2.inRange(ycrcb, np.array([0, 133, 77]), np.array([255, 173, 127]))
            valid[skin > 0] = 0
        valid_pixels = int(np.count_nonzero(valid))
        stats = {
            "valid_pixels": valid_pixels,
            "blur": float(cv2.Laplacian(gray, cv2.CV_64F).var()),
            "brightness": float(np.mean(hsv[..., 2])),
            "saturation": float(np.mean(hsv[..., 1])),
        }
        if valid_pixels < self.config.min_valid_pixels_per_region:
            return None, stats
        histograms: list[float] = []
        for image, channel, bins, value_range in (
            (hsv, 0, 12, [0, 180]),
            (hsv, 1, 8, [0, 256]),
            (lab, 1, 8, [0, 256]),
            (lab, 2, 8, [0, 256]),
        ):
            histogram = cv2.calcHist([image], [channel], valid, [bins], value_range).reshape(-1)
            histogram /= max(float(histogram.sum()), 1e-6)
            histograms.extend(float(value) for value in histogram)
        pixels = lab[valid > 0].astype(np.float32)
        means = pixels.mean(axis=0)
        stds = pixels.std(axis=0)
        moments = tuple(float(value / 255.0) for value in np.concatenate([means, stds]))
        texture: tuple[float, ...] = ()
        if self.config.texture_enabled:
            edges = cv2.Canny(gray, 60, 120)
            texture = (float(np.mean(edges > 0)),)
        return AppearanceRegionFeature(tuple(histograms), moments, texture), stats


def appearance_distance(
    left: PlayerAppearanceDescriptor | None,
    right: PlayerAppearanceDescriptor | None,
) -> float | None:
    if left is None or right is None:
        return None
    a, b = left.vector(), right.vector()
    if a is None or b is None or a.shape != b.shape:
        return None
    denominator = a + b + 1e-6
    chi_square = 0.5 * float(np.sum(((a - b) ** 2) / denominator)) / max(1, a.size)
    return max(0.0, min(1.0, chi_square * 8.0))


@dataclass
class AppearanceTemplateGallery:
    max_samples: int = 20
    max_update_step: float = 0.15
    descriptors: deque[PlayerAppearanceDescriptor] = field(default_factory=deque)
    accepted_updates: int = 0
    frozen_updates: int = 0
    reset_count: int = 0
    _template: np.ndarray | None = None

    @property
    def template_age(self) -> int:
        return self.accepted_updates

    def update(self, descriptor: PlayerAppearanceDescriptor | None, *, confirmed_observed: bool) -> bool:
        if descriptor is None or descriptor.status != "available" or not confirmed_observed:
            self.frozen_updates += 1
            return False
        vector = descriptor.vector()
        if vector is None:
            self.frozen_updates += 1
            return False
        if self._template is None:
            self._template = vector.copy()
        else:
            distance = float(np.linalg.norm(vector - self._template) / max(1.0, np.sqrt(vector.size)))
            step = min(self.max_update_step, max(0.02, descriptor.quality.score * 0.10))
            if distance > 0.35:
                self.frozen_updates += 1
                return False
            self._template = (1.0 - step) * self._template + step * vector
        self.descriptors.append(descriptor)
        while len(self.descriptors) > self.max_samples:
            self.descriptors.popleft()
        self.accepted_updates += 1
        return True

    def descriptor(self) -> PlayerAppearanceDescriptor | None:
        if not self.descriptors:
            return None
        # The most recent real descriptor carries the schema/quality metadata;
        # matching uses the robust numeric template through distance_to().
        return self.descriptors[-1]

    def distance_to(self, descriptor: PlayerAppearanceDescriptor | None) -> float | None:
        if self._template is None or descriptor is None:
            return None
        vector = descriptor.vector()
        if vector is None or vector.shape != self._template.shape:
            return None
        return max(0.0, min(1.0, float(np.linalg.norm(vector - self._template) / np.sqrt(vector.size))))

    def reset(self) -> None:
        self.descriptors.clear()
        self._template = None
        self.accepted_updates = 0
        self.reset_count += 1


def discriminative_margin(descriptors: Sequence[PlayerAppearanceDescriptor | None]) -> float:
    distances = [
        distance
        for index, left in enumerate(descriptors)
        for right in descriptors[index + 1:]
        if (distance := appearance_distance(left, right)) is not None
    ]
    return min(distances, default=0.0)


def _pose_regions(
    keypoints: Sequence[Sequence[float]] | None,
    bbox: tuple[int, int, int, int],
) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]] | None:
    # COCO-style shoulders/hips/knees when present and confident.
    if keypoints is None or len(keypoints) < 15:
        return None
    try:
        shoulders = [keypoints[5], keypoints[6]]
        hips = [keypoints[11], keypoints[12]]
        knees = [keypoints[13], keypoints[14]]
        if any(len(point) < 2 for point in shoulders + hips + knees):
            return None
        x1, _y1, x2, _y2 = bbox
        shoulder_y = round(sum(float(point[1]) for point in shoulders) / 2.0)
        hip_y = round(sum(float(point[1]) for point in hips) / 2.0)
        knee_y = round(sum(float(point[1]) for point in knees) / 2.0)
        inset = round((x2 - x1) * 0.1)
        if not shoulder_y < hip_y < knee_y:
            return None
        return (x1 + inset, shoulder_y, x2 - inset, hip_y), (x1 + inset, hip_y, x2 - inset, knee_y)
    except (TypeError, ValueError):
        return None


def _unavailable(
    reason: str,
    *,
    clipping_ratio: float = 0.0,
    provenance: Literal["base", "roi_recovery"] = "base",
) -> PlayerAppearanceDescriptor:
    return PlayerAppearanceDescriptor(
        upper=None,
        lower=None,
        quality=AppearanceQuality(
            clipping_ratio=clipping_ratio,
            valid_pixels=0,
            blur_score=0.0,
            brightness=0.0,
            saturation=0.0,
            occlusion_ratio=0.0,
            score=0.0,
            reasons=(reason,),
        ),
        status="unavailable",
        provenance=provenance,
    )
