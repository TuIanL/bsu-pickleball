#!/usr/bin/env python3
"""Validate candidate timeline structure and safety invariants without third-party dependencies."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON root must be an object")
    return value


def validate(path: Path) -> list[str]:
    errors: list[str] = []
    artifact = load(path)
    required = {
        "schema_version",
        "capture_take_id",
        "source_session_id",
        "duration_ms",
        "model",
        "source_provenance",
        "decoder",
        "windows",
        "candidate_segments",
        "review_status",
    }
    missing = sorted(required - artifact.keys())
    if missing:
        errors.append(f"missing top-level fields: {missing}")
        return errors
    if artifact["schema_version"] != "match_state_candidate_timeline.v1":
        errors.append("unsupported schema_version")
    if artifact["review_status"] not in {"unreviewed", "in_review", "reviewed"}:
        errors.append("invalid review_status")
    provenance = artifact.get("source_provenance", {})
    for name in ("dataset_manifest_sha256", "timeline_generator_revision"):
        value = provenance.get(name)
        if not isinstance(value, str) or (name.endswith("sha256") and len(value) != 64):
            errors.append(f"invalid provenance hash: {name}")
    modalities = {
        str(value).lower()
        for value in artifact.get("model", {}).get("modalities", [])
        if isinstance(value, str)
    }
    # 结构化/融合候选必须携带结构化特征链；RGB-only 候选不应被迫伪造
    # 并不存在的 pose/ball/tensor manifest 哈希。
    if modalities - {"rgb"}:
        for name in (
            "group_split_sha256",
            "canonical_feature_manifest_sha256",
            "structured_sequence_manifest_sha256",
            "structured_tensor_manifest_sha256",
        ):
            value = provenance.get(name)
            if not isinstance(value, str) or len(value) != 64:
                errors.append(f"invalid provenance hash: {name}")
    windows = artifact.get("windows")
    if not isinstance(windows, list):
        errors.append("windows must be a list")
        windows = []
    previous_center = -1.0
    for index, window in enumerate(windows):
        center = float(window.get("center_ms", -1))
        if center < previous_center:
            errors.append(f"windows not ordered at index {index}")
        previous_center = center
        if window.get("state") not in {"rally_active", "non_play", "unknown"}:
            errors.append(f"invalid state at window {index}")
        probabilities = window.get("state_probabilities", {})
        for state in ("rally_active", "non_play"):
            probability = probabilities.get(state)
            if not isinstance(probability, (int, float)) or not 0 <= float(probability) <= 1:
                errors.append(f"invalid {state} probability at window {index}")
        coverage = window.get("coverage")
        if not isinstance(coverage, (int, float)) or not 0 <= float(coverage) <= 1:
            errors.append(f"invalid coverage at window {index}")
    candidates = artifact.get("candidate_segments")
    if not isinstance(candidates, list):
        errors.append("candidate_segments must be a list")
        candidates = []
    previous_end = -1.0
    candidate_ids: set[str] = set()
    for index, candidate in enumerate(candidates):
        candidate_id = candidate.get("candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id or candidate_id in candidate_ids:
            errors.append(f"invalid or duplicate candidate_id at segment {index}")
        candidate_ids.add(str(candidate_id))
        start = float(candidate.get("start_ms", -1))
        end = float(candidate.get("end_ms", -1))
        if start < 0 or end <= start:
            errors.append(f"invalid boundary at segment {index}")
        if start < previous_end:
            errors.append(f"overlapping or unordered segment at index {index}")
        previous_end = end
        if candidate.get("status") not in {"unreviewed", "accepted", "corrected", "rejected"}:
            errors.append(f"invalid status at segment {index}")
        if not isinstance(candidate.get("boundary_evidence"), dict):
            errors.append(f"missing boundary_evidence at segment {index}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify match-state candidate timeline artifacts")
    parser.add_argument("paths", type=Path, nargs="+")
    args = parser.parse_args()
    checked = 0
    failures: dict[str, list[str]] = {}
    for source in args.paths:
        paths = sorted(source.glob("*.timeline.json")) if source.is_dir() else [source]
        for path in paths:
            checked += 1
            errors = validate(path)
            if errors:
                failures[str(path)] = errors
    report = {
        "schema_version": "match_state_candidate_timeline_integrity.v1",
        "status": "passed" if checked and not failures else "failed",
        "checked_count": checked,
        "failures": failures,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
