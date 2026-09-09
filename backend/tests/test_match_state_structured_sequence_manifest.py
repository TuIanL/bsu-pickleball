from __future__ import annotations

import hashlib
import json
import sys
from argparse import Namespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.build_match_state_structured_sequence_manifest import build_manifest  # noqa: E402
from scripts.verify_match_state_structured_sequence_manifest import verify  # noqa: E402


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _feature_record(index: int) -> dict:
    views = {}
    for role in ("cam_1", "cam_2"):
        views[role] = {
            "camera_role": role,
            "camera_id": "174" if role == "cam_1" else "175",
            "source": {
                "source_frame_index": index,
                "source_pts_ms": index * 1000 / 12,
                "mapped_target_pts_ms": index * 1000 / 12,
                "alignment_error_ms": 0.0,
                "feature_source_frame_index": index,
                "feature_pts_ms": index * 1000 / 12,
                "feature_alignment_error_ms": 0.0,
                "timing_authority": "source_pts",
                "sync_quality": "good",
                "sync_status": "authoritative",
                "mapping_mode": "reference",
                "sync_revision": "syncv2_test",
            },
            "structured": {"available": True},
            "court_line": {"available": False},
            "features": {"pose": {}, "ball": {}},
            "quality": {
                "structured_available": True,
                "view_missing": False,
                "pose_usable": False,
                "ball_observed": False,
                "court_line_available": False,
            },
        }
    return {
        "schema_version": "match_state_canonical_sync_feature.v2",
        "feature_schema": "match_state_aligned_feature.v1",
        "capture_take_id": "take-1",
        "source_session_id": "session-1",
        "timebase": "reference_camera_source_pts",
        "canonical_timestamp_ms": round(index * 1000 / 12, 3),
        "reference_source_frame_index": index,
        "sync_revision": "syncv2_test",
        "sync": {
            "reference_camera_id": "174",
            "status": "authoritative",
            "authoritative_joint_eligible": True,
            "camera_status": {"cam_1": "authoritative", "cam_2": "authoritative"},
        },
        "views": views,
        "quality": {
            "dual_view_available": True,
            "authoritative_joint_eligible": True,
            "sync_status": "authoritative",
        },
    }


def _args(tmp_path: Path, feature_path: Path) -> Namespace:
    dataset_path = tmp_path / "dataset.json"
    dataset_path.write_text(
        json.dumps(
            {
                "schema_version": "match_state_dataset_manifest.v1",
                "manifest_id": "dataset-test",
                "takes": [
                    {
                        "capture_take_id": "take-1",
                        "source_session_id": "session-1",
                        "duration_ms": 5000,
                        "labels": [{"segment_id": "rally-1", "start_ms": 2000, "end_ms": 4000}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    label_path = tmp_path / "label.json"
    label_path.write_text(
        json.dumps({"reviewed_boundary_policy": {"uncertain_radius_ms": 250}}), encoding="utf-8"
    )
    split_path = tmp_path / "split.json"
    split_path.write_text(
        json.dumps(
            {
                "schema_version": "match_state_group_split.v1",
                "split_id": "split-test",
                "assignment": {"take-1": "train"},
            }
        ),
        encoding="utf-8",
    )
    canonical_manifest = tmp_path / "canonical-manifest.json"
    canonical_manifest.write_text(
        json.dumps(
            {
                "schema_version": "match_state_canonical_sync_manifest.v2",
                "manifest_id": "canonical-test",
                "entries": [
                    {
                        "capture_take_id": "take-1",
                        "source_session_id": "session-1",
                        "path": feature_path.name,
                        "status": "complete",
                        "record_count": 54,
                        "authoritative_joint_record_count": 54,
                        "sha256": _sha256(feature_path),
                        "size_bytes": feature_path.stat().st_size,
                        "sync_revision": "syncv2_test",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output_root = tmp_path / "sequences"
    return Namespace(
        dataset_manifest=dataset_path,
        label_profile=label_path,
        group_split=split_path,
        canonical_manifest=canonical_manifest,
        canonical_feature_root=tmp_path,
        output_root=output_root,
        dataset_root=tmp_path,
        window_duration_ms=4000,
        fps=12.0,
        frame_count=48,
        stride_frames=6,
        continuity_tolerance_ms=2.0,
        verify_source_hashes=True,
    )


def test_builds_strict_windows_and_masks_uncertain_center(tmp_path: Path):
    feature_path = tmp_path / "take-1.jsonl"
    with feature_path.open("w", encoding="utf-8") as handle:
        for index in range(54):
            handle.write(json.dumps(_feature_record(index)) + "\n")
    args = _args(tmp_path, feature_path)

    manifest = build_manifest(args)
    assert manifest["sequence_count"] == 2
    assert manifest["split_counts"] == {"train": 2}
    assert manifest["center_quality_counts"]["uncertain"] == 1
    assert manifest["center_quality_counts"]["high_confidence"] == 1

    sequence_lines = (args.output_root / "sequences.jsonl").read_text(encoding="utf-8").splitlines()
    sequences = [json.loads(line) for line in sequence_lines]
    assert sequences[0]["record_count"] == 48
    assert sequences[0]["strict_gate"]["sync_status_counts"] == {"authoritative": 48}
    assert sequences[0]["label"]["center_loss_mask"] == 0
    assert sequences[1]["label"]["center_loss_mask"] == 1
    assert len(sequences[0]["label"]["timeline_labels"]) == 48

    report = verify(args.output_root / "manifest.json", tmp_path, verify_source=True)
    assert report["status"] == "passed", report


def test_non_authoritative_record_is_not_included(tmp_path: Path):
    feature_path = tmp_path / "take-1.jsonl"
    records = [_feature_record(index) for index in range(54)]
    records[30]["sync"]["status"] = "extrapolated"
    records[30]["sync"]["authoritative_joint_eligible"] = False
    records[30]["quality"]["authoritative_joint_eligible"] = False
    records[30]["views"]["cam_2"]["source"]["sync_status"] = "extrapolated"
    with feature_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")
    args = _args(tmp_path, feature_path)
    manifest = build_manifest(args)
    assert manifest["sequence_count"] == 0
