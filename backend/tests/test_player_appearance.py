import numpy as np

from app.schemas.tracking import Detection
from app.vision.player_tracking_engine.multi_object_tracker import MultiObjectTracker
from app.vision.player_tracking_engine.player_appearance import (
    AppearanceExtractorConfig,
    AppearanceTemplateGallery,
    ClothingAppearanceExtractor,
    appearance_distance,
    discriminative_margin,
)


def _frame(upper_bgr, lower_bgr, *, brightness_scale=1.0):
    frame = np.full((160, 100, 3), 30, dtype=np.uint8)
    for y in range(20, 145):
        base = upper_bgr if y < 85 else lower_bgr
        delta = 12 if (y // 4) % 2 else 0
        frame[y, 20:80] = np.clip((np.asarray(base) + delta) * brightness_scale, 0, 255)
    return frame


def _extract(frame, bbox=(20, 10, 80, 150), provenance="base"):
    extractor = ClothingAppearanceExtractor(
        AppearanceExtractorConfig(min_blur_variance=0.0, min_valid_pixels_per_region=20)
    )
    return extractor.extract(frame, bbox, provenance=provenance)


def test_extracts_versioned_upper_lower_hsv_lab_descriptor():
    descriptor = _extract(_frame((220, 30, 30), (30, 30, 220)))
    assert descriptor.status == "available"
    assert descriptor.upper is not None and descriptor.lower is not None
    assert descriptor.extractor_version == "clothing-hsv-lab.v1"
    assert descriptor.partition_method == "bbox_relative"
    assert descriptor.quality.valid_pixels > 0


def test_upper_lower_combination_distinguishes_players():
    blue_red = _extract(_frame((220, 30, 30), (30, 30, 220)))
    blue_white = _extract(_frame((220, 30, 30), (230, 230, 230)))
    same = _extract(_frame((220, 30, 30), (30, 30, 220)))
    assert appearance_distance(blue_red, same) < appearance_distance(blue_red, blue_white)


def test_low_light_and_clipped_bbox_fail_closed():
    low_light = _extract(_frame((40, 20, 20), (20, 20, 40), brightness_scale=0.1))
    clipped = _extract(_frame((220, 30, 30), (30, 30, 220)), bbox=(-40, 10, 80, 150))
    assert low_light.status == "low_quality"
    assert "too_dark" in low_light.quality.reasons
    assert clipped.status == "low_quality"
    assert "bbox_clipped" in clipped.quality.reasons


def test_projected_provenance_cannot_be_extracted():
    descriptor = _extract(_frame((220, 30, 30), (30, 30, 220)), provenance="cross_view_projected")
    assert descriptor.status == "unavailable"
    assert "non_detector_provenance" in descriptor.quality.reasons


def test_template_freezes_on_ambiguous_or_large_change_and_can_reset():
    gallery = AppearanceTemplateGallery()
    incumbent = _extract(_frame((220, 30, 30), (30, 30, 220)))
    challenger = _extract(_frame((30, 220, 30), (230, 230, 230)))
    assert gallery.update(incumbent, confirmed_observed=True) is True
    assert gallery.update(challenger, confirmed_observed=False) is False
    assert gallery.accepted_updates == 1
    assert gallery.frozen_updates == 1
    gallery.reset()
    assert gallery.template_age == 0
    assert gallery.reset_count == 1


def test_same_color_descriptors_are_non_discriminative():
    first = _extract(_frame((20, 20, 20), (25, 25, 25)))
    second = _extract(_frame((20, 20, 20), (25, 25, 25)))
    assert discriminative_margin([first, second]) < 0.08


def test_appearance_disabled_path_matches_geometry_only():
    sequence = [
        [Detection(bbox=[0, 0, 20, 100], confidence=0.9), Detection(bbox=[80, 0, 100, 100], confidence=0.9)],
        [Detection(bbox=[10, 0, 30, 100], confidence=0.9), Detection(bbox=[70, 0, 90, 100], confidence=0.9)],
    ]
    plain = MultiObjectTracker(algorithm="motion", appearance_enabled=False)
    weighted_but_disabled = MultiObjectTracker(algorithm="motion", appearance_enabled=False, appearance_weight=99)
    assert [plain.update_with_assignments(frame).detection_to_track for frame in sequence] == [
        weighted_but_disabled.update_with_assignments(frame).detection_to_track for frame in sequence
    ]
