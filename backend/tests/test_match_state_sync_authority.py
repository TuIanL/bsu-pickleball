from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.match_state_sync_authority import (  # noqa: E402
    CanonicalFeatureClock,
    SourceTiming,
    feature_timings,
)


def _write_pts(path: Path, *, first_pts: float = 100.0, frame_count: int = 1001) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for index in range(frame_count):
            handle.write(
                json.dumps(
                    {
                        "frame_index": index,
                        "pts_seconds": first_pts + index * 0.01,
                        "dts_seconds": None,
                        "keyframe": index == 0,
                    }
                )
                + "\n"
            )


def _sync_entry() -> dict:
    def mapping(camera_id: str, *, offset_ms: float, valid_start: float | None, valid_end: float | None) -> dict:
        return {
            "reference_camera": "174",
            "camera_id": camera_id,
            "offset_ms": offset_ms,
            "rate": 1.0,
            "drift_ppm": 0.0,
            "residual_rms_ms": 2.0,
            "anchor_count": 3,
            "quality": "good",
            "reason": None,
            "valid_start_seconds": valid_start,
            "valid_end_seconds": valid_end,
        }

    return {
        "reference_camera_id": "174",
        "sync_revision": "syncv2_test",
        "cameras": [
            {
                "camera_role": "cam_1",
                "camera_id": "174",
                "mapping": mapping("174", offset_ms=0.0, valid_start=2.0, valid_end=8.0),
            },
            {
                "camera_role": "cam_2",
                "camera_id": "175",
                "mapping": mapping("175", offset_ms=10.0, valid_start=2.0, valid_end=8.0),
            },
        ],
    }


def test_source_pts_is_normalized_and_feature_records_bind_by_decoded_index(tmp_path: Path):
    path = tmp_path / "cam.pts.jsonl"
    _write_pts(path, first_pts=100.0, frame_count=3)
    timing = SourceTiming.from_sidecar("174", path)
    assert timing.first_timestamp_seconds == 0.0
    assert timing.last_timestamp_seconds == pytest.approx(0.02)

    records = [{"decoded_frame_index": 1, "take_timestamp_ms": 9999}, {"decoded_frame_index": 9}]
    bound = feature_timings(records, timing)
    assert len(bound) == 1
    assert bound[0].source_frame_index == 1
    assert bound[0].timestamp_seconds == pytest.approx(0.01)


def test_canonical_clock_reuses_affine_mapping_and_marks_extrapolation(tmp_path: Path):
    cam1_path = tmp_path / "174.pts.jsonl"
    cam2_path = tmp_path / "175.pts.jsonl"
    _write_pts(cam1_path)
    _write_pts(cam2_path)
    timings = {
        "cam_1": SourceTiming.from_sidecar("174", cam1_path),
        "cam_2": SourceTiming.from_sidecar("175", cam2_path),
    }
    feature_records = {
        role: [{"decoded_frame_index": index, "schema_version": "structured.v1"} for index in range(1001)]
        for role in ("cam_1", "cam_2")
    }
    clock = CanonicalFeatureClock(
        sync_entry=_sync_entry(),
        source_timings=timings,
        feature_timings_by_role={
            role: feature_timings(records, timings[role]) for role, records in feature_records.items()
        },
        max_source_selection_error_ms=11.0,
        max_feature_selection_gap_ms=11.0,
    )

    inside, inside_record = clock.select("cam_2", 3.0)
    assert inside_record is not None
    assert inside.mapping_mode == "affine_mapping"
    assert inside.sync_status == "authoritative"
    assert inside.target_source_pts_seconds == 3.01
    assert inside.source_frame_index == 301
    assert inside.feature_source_frame_index == 301

    outside, outside_record = clock.select("cam_2", 1.0)
    assert outside_record is not None
    assert outside.mapping_mode == "affine_extrapolation"
    assert outside.sync_status == "extrapolated"
    assert outside.target_source_pts_seconds == 1.01

    ticks = clock.canonical_ticks(10.0)
    assert ticks[0] == (0.0, 0)
    assert ticks[-1] == (10.0, 1000)
