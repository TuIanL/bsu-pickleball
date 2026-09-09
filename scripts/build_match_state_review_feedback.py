#!/usr/bin/env python3
"""Export reviewed learned candidates as an auditable next-dataset input layer."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build reviewed candidate feedback for the next dataset revision")
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    source_sidecars: list[dict[str, Any]] = []
    counts = {"accepted": 0, "corrected": 0, "rejected": 0}
    for path in sorted(args.candidate_dir.glob("*.reviews.json")):
        review = load(path)
        if review.get("schema_version") != "match-state-candidate-review.v1":
            raise ValueError(f"unsupported review schema: {path}")
        latest: dict[str, dict[str, Any]] = {}
        for item in review.get("history", []):
            if item.get("candidate_id"):
                latest[str(item["candidate_id"])] = item
        for candidate_id, item in sorted(latest.items()):
            decision = str(item.get("decision"))
            if decision not in counts:
                raise ValueError(f"unsupported decision {decision}: {path}")
            counts[decision] += 1
            records.append(
                {
                    "schema_version": "match_state_reviewed_feedback_record.v1",
                    "capture_take_id": review["capture_take_id"],
                    "candidate_id": candidate_id,
                    "decision": decision,
                    "trainable": decision in {"accepted", "corrected"},
                    "label": "rally_active" if decision in {"accepted", "corrected"} else "excluded",
                    "start_ms": item.get("reviewed_start_ms"),
                    "end_ms": item.get("reviewed_end_ms"),
                    "review_revision": item.get("revision"),
                    "reviewed_at": item.get("reviewed_at"),
                    "operation_id": item.get("operation_id"),
                    "output_segment_id": item.get("output_segment_id"),
                    "review_provenance": item.get("provenance", {}),
                    "source_model": review.get("source", {}),
                }
            )
        source_sidecars.append(
            {
                "path": str(path),
                "sha256": sha256(path),
                "capture_take_id": review.get("capture_take_id"),
                "revision": review.get("revision"),
            }
        )
    output = args.output_dir / "feedback.jsonl"
    with output.open("w", encoding="utf-8") as target:
        for record in records:
            target.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    identity = {
        "source_sidecars": source_sidecars,
        "record_count": len(records),
        "decision_counts": counts,
        "feedback_sha256": sha256(output),
    }
    manifest_id = "msrf_" + hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:20]
    manifest = {
        "schema_version": "match_state_reviewed_feedback_manifest.v1",
        "manifest_id": manifest_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "feedback_file": output.name,
        **identity,
        "usage": {
            "accepted_or_corrected": "eligible input labels for a new dataset revision after normal overlap/integrity audit",
            "rejected": "hard-negative/audit evidence; never emitted as rally_active",
            "automatic_authority": False,
        },
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
