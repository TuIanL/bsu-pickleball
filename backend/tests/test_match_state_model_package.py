from __future__ import annotations

import json

from scripts.verify_match_state_model_package import validate_package


def _write_package(root, checksums=True):
    files = {
        "model.pt": b"weights",
        "training_profile.json": b"{}\n",
        "evaluation_report.json": b"{}\n",
    }
    for name, content in files.items():
        (root / name).write_bytes(content)
    import hashlib

    artifact_checksums = {
        name: {"sha256": hashlib.sha256(content).hexdigest(), "size_bytes": len(content)}
        for name, content in files.items()
    }
    package = {
        "schema_version": "match_state_model_package.v1",
        "package_id": "test-package",
        "model_name": "test-model",
        "model_version": "test-v1",
        "task": "match_state_temporal_segmentation",
        "classes": ["rally_active", "non_play", "unknown"],
        "input_contract": {
            "modalities": ["rgb"],
            "sampling_fps": 12.0,
            "clip_duration_ms": 4000,
            "feature_schema": "test.v1",
        },
        "thresholds": {
            "minimum_confidence": 0.65,
            "minimum_coverage": 0.75,
            "minimum_duration_ms": 500,
            "hysteresis": 0.1,
            "unknown_on_insufficient_evidence": True,
        },
        "provenance": {
            key: "a" * 64
            for key in (
                "dataset_manifest_sha256",
                "rgb_clip_manifest_sha256",
                "group_split_sha256",
                "structured_feature_profile_sha256",
                "config_sha256",
            )
        },
        "artifacts": {
            "weights": "model.pt",
            "training_config": "training_profile.json",
            "evaluation_report": "evaluation_report.json",
        },
        "runtime": {"status": "ready", "device": "cpu", "fallback": "preserve_existing_analysis"},
        "source_dataset_manifest_id": "dataset-v1",
        "source_rgb_manifest_id": "rgb-v1",
        "structured_feature_profile_schema": "structured.v1",
    }
    if checksums:
        package["artifacts"]["checksums"] = artifact_checksums
    (root / "model_package.json").write_text(json.dumps(package), encoding="utf-8")


def test_model_package_verifier_checks_artifact_hashes(tmp_path):
    _write_package(tmp_path)
    result = validate_package(tmp_path, strict=True)
    assert result["status"] == "passed"
    assert result["artifacts"]["model.pt"]["size_bytes"] == len(b"weights")


def test_model_package_verifier_rejects_missing_strict_checksums(tmp_path):
    _write_package(tmp_path, checksums=False)
    result = validate_package(tmp_path, strict=True)
    assert result["status"] == "failed"
    assert any("checksums" in error for error in result["errors"])
