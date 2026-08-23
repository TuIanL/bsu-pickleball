import numpy as np

from app.vision.multiview.camera_color_profile import (
    calibrated_descriptor_distance,
    estimate_camera_color_profile,
)
from app.vision.player_tracking_engine.player_appearance import (
    AppearanceExtractorConfig,
    ClothingAppearanceExtractor,
)


EXTRACTOR = ClothingAppearanceExtractor(
    AppearanceExtractorConfig(min_blur_variance=0.0, min_valid_pixels_per_region=20)
)


def _descriptor(bgr, shift=0):
    frame = np.full((160, 100, 3), 30, dtype=np.uint8)
    for y in range(20, 145):
        delta = 8 if (y // 4) % 2 else 0
        frame[y, 20:80] = np.clip(np.asarray(bgr) + shift + delta, 0, 255)
    return EXTRACTOR.extract(frame, [20, 10, 80, 150], provenance="base")


def test_profile_requires_enough_pairs_before_cross_camera_use():
    pair = (_descriptor((180, 50, 30)), _descriptor((180, 50, 30), shift=15))
    profile = estimate_camera_color_profile(
        source_view="cam_2", target_view="cam_1", paired_descriptors=[pair] * 3
    )
    assert profile.available is False
    assert calibrated_descriptor_distance(pair[0], pair[1], profile) is None


def test_profile_records_version_samples_residual_and_confidence():
    pairs = [
        (_descriptor((160 + index, 45, 25)), _descriptor((160 + index, 45, 25), shift=12))
        for index in range(12)
    ]
    profile = estimate_camera_color_profile(
        source_view="cam_2", target_view="cam_1", paired_descriptors=pairs
    )
    assert profile.sample_count == 12
    assert profile.version == "descriptor-affine.v1"
    assert profile.available is True
    assert calibrated_descriptor_distance(pairs[0][0], pairs[0][1], profile) is not None


def test_bad_residual_disables_profile():
    pairs = [
        (_descriptor((180, 40, 20)), _descriptor((20, (index * 31) % 255, 220)))
        for index in range(12)
    ]
    profile = estimate_camera_color_profile(
        source_view="cam_2", target_view="cam_1", paired_descriptors=pairs
    )
    assert profile.available is False or profile.residual > 0.1
