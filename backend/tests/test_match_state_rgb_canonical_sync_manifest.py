from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.build_match_state_rgb_canonical_sync_manifest import build_manifest  # noqa: E402


def _mapping(camera_id: str, offset_ms: float) -> dict:
    return {
        "reference_camera": "174",
        "camera_id": camera_id,
        "offset_ms": offset_ms,
        "rate": 0.999,
        "drift_ppm": -1000.0,
        "residual_rms_ms": 2.0,
        "anchor_count": 3,
        "quality": "good",
        "reason": None,
        "valid_start_seconds": 2.0,
        "valid_end_seconds": 8.0,
    }


def test_rgb_manifest_contains_per_view_affine_binding(tmp_path: Path):
    base_path = tmp_path / "base.json"
    clips_path = tmp_path / "base.clips.jsonl"
    output_path = tmp_path / "v2.json"
    clip = {
        "schema_version": "match_state_rgb_clip.v1",
        "clip_id": "clip-1",
        "dataset_manifest_id": "dataset-1",
        "capture_take_id": "take-1",
        "source_session_id": "session-1",
        "timebase": "capture_take_relative_ms",
        "requested_start_ms": 3000,
        "requested_end_ms": 7000,
        "take_start_ms": 3000,
        "take_end_ms": 7000,
        "center_ms": 5000,
        "center_label": "rally_active",
        "center_quality": "high_confidence",
        "views": [
            {"camera_role": "cam_1", "logical_media_uri": "uri-1", "take_end_ms": 10000},
            {"camera_role": "cam_2", "logical_media_uri": "uri-2", "take_end_ms": 10000},
        ],
    }
    clips_path.write_text(json.dumps(clip) + "\n", encoding="utf-8")
    base_path.write_text(
        json.dumps(
            {
                "manifest_id": "rgb-v1",
                "clips_file": clips_path.name,
                "split_status": "complete",
            }
        ),
        encoding="utf-8",
    )
    sync_path = tmp_path / "sync.json"
    sync_path.write_text(
        json.dumps(
            {
                "manifest_id": "sync-v2",
                "identity": {"sync_core_sha256": "a" * 64},
                "entries": [
                    {
                        "source_session_id": "session-1",
                        "reference_camera_id": "174",
                        "sync_revision": "revision-1",
                        "calibration": {"sha256": "b" * 64},
                        "cameras": [
                            {
                                "camera_role": "cam_1",
                                "camera_id": "174",
                                "mapping": _mapping("174", 0.0),
                                "timing": {"sha256": "c" * 64, "duration_seconds": 10.0},
                            },
                            {
                                "camera_role": "cam_2",
                                "camera_id": "175",
                                "mapping": _mapping("175", 100.0),
                                "timing": {"sha256": "d" * 64, "duration_seconds": 10.0},
                            },
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = build_manifest(base_path, sync_path, output_path)
    written_clip = json.loads((tmp_path / "v2.clips.jsonl").read_text(encoding="utf-8"))
    cam2 = next(view for view in written_clip["views"] if view["camera_role"] == "cam_2")
    assert result["schema_version"] == "match_state_rgb_canonical_sync_manifest.v2"
    assert cam2["mapped_start_ms"] == 3097.0
    assert cam2["mapped_end_ms"] == 7093.0
    assert cam2["canonical_to_local_rate"] == 0.999
    assert cam2["sync_status"] == "authoritative"
    assert cam2["timing_authority"] == "source_pts"
    assert written_clip["sync"]["authoritative_joint_eligible"] is True
