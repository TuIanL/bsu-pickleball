from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.train_match_state_rgb import experiment_id_for_manifest, sample_timestamp_ms  # noqa: E402


def test_rgb_loader_uses_per_view_mapped_time_and_rate():
    clip = {"requested_start_ms": 1000}
    view = {"mapped_start_ms": 1050, "canonical_to_local_rate": 0.999}
    assert sample_timestamp_ms(clip, view, 0, 12) == 1050
    assert sample_timestamp_ms(clip, view, 12, 12) == 2049.0


def test_rgb_loader_preserves_v1_nominal_fallback():
    assert sample_timestamp_ms({"requested_start_ms": -2000}, {}, 12, 12) == -1000


def test_rgb_training_variant_is_versioned_by_manifest_timebase():
    assert experiment_id_for_manifest({"schema_version": "match_state_rgb_clip_manifest.v1"}) == "rgb_only_v1"
    assert (
        experiment_id_for_manifest({"schema_version": "match_state_rgb_canonical_sync_manifest.v2"})
        == "rgb_only_v2_canonical_sync"
    )
