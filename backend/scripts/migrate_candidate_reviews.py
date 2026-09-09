"""Dry-run/apply importer for legacy candidate review sidecars.

The importer is deliberately conservative: a history record without a
verifiable artifact SHA-256 or a live segment reference is reported as
``legacy_unbound`` and is never turned into a new business decision.
"""

from __future__ import annotations

import argparse
import json
import hashlib
from pathlib import Path
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.database import get_session_factory, init_db
from app.models.capture_segment import CaptureSegment
from app.models.segment_edit_operation import SegmentEditOperation
from app.models.match_state_candidate import (
    MatchStateCandidateArtifact,
    MatchStateCandidateDecision,
    MatchStateCandidateReview,
)
from app.services.match_state_candidate_service import _read_candidate_artifact


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="legacy match_state_candidates directory")
    parser.add_argument("--database", type=Path, help="SQLite database path")
    parser.add_argument("--report", type=Path, help="JSON report path")
    parser.add_argument("--apply", action="store_true", help="write proven records; default is dry-run")
    return parser.parse_args()


def _candidate_map(artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("candidate_id")): row
        for row in artifact.get("candidate_segments", [])
        if isinstance(row, dict) and row.get("candidate_id")
    }


def migrate(root: Path, *, apply: bool) -> dict[str, Any]:
    root = root.resolve()
    report: dict[str, Any] = {
        "schema_version": "match-state-candidate-review-migration.v1",
        "mode": "apply" if apply else "dry-run",
        "root": str(root),
        "files": [],
        "summary": {"imported": 0, "skipped": 0, "legacy_unbound": 0, "conflicts": 0, "invalid": 0},
    }
    if not root.is_dir():
        return report

    factory = get_session_factory()
    db = factory() if factory else None
    try:
        for sidecar in sorted(root.glob("*.reviews.json")):
            item: dict[str, Any] = {"path": str(sidecar), "records": []}
            item["sha256"] = hashlib.sha256(sidecar.read_bytes()).hexdigest()
            try:
                review = json.loads(sidecar.read_text(encoding="utf-8"))
                take_id = str(review["capture_take_id"])
                history = review.get("history", [])
                if not isinstance(history, list):
                    raise ValueError("history must be a list")
                _artifact_path, artifact_raw, artifact, artifact_version = _read_candidate_artifact(root, take_id)
                candidates = _candidate_map(artifact)
            except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                item["error"] = str(exc)
                report["summary"]["invalid"] += 1
                report["files"].append(item)
                continue

            for record in history:
                if not isinstance(record, dict):
                    item["records"].append({"status": "invalid", "reason": "record_must_be_object"})
                    report["summary"]["invalid"] += 1
                    continue
                result: dict[str, Any] = {"candidate_id": record.get("candidate_id"), "status": "legacy_unbound"}
                candidate_id = str(record.get("candidate_id") or "")
                supplied_version = record.get("artifact_version") or review.get("artifact_version")
                if supplied_version != artifact_version:
                    result["reason"] = "missing_or_mismatched_artifact_version"
                    report["summary"]["legacy_unbound"] += 1
                    item["records"].append(result)
                    continue
                if candidate_id not in candidates:
                    result["reason"] = "candidate_id_not_in_artifact"
                    report["summary"]["legacy_unbound"] += 1
                    item["records"].append(result)
                    continue
                output_segment_id = record.get("output_segment_id")
                operation = db.get(SegmentEditOperation, record["operation_id"]) if record.get("operation_id") else None
                segment = db.get(CaptureSegment, output_segment_id) if output_segment_id else None
                decision = record.get("decision")
                reason = None
                if decision not in {"accepted", "corrected", "rejected"}:
                    reason = "invalid_decision"
                elif operation is None or operation.capture_take_id != take_id:
                    reason = "operation_reference_missing_or_wrong_take"
                elif decision != "rejected" and (segment is None or segment.capture_take_id != take_id
                        or segment.created_by_operation_id != operation.id):
                    reason = "output_segment_reference_missing_or_wrong_take"
                elif decision == "rejected" and output_segment_id:
                    reason = "rejection_has_output_segment"
                if reason:
                    result["reason"] = reason
                    report["summary"]["legacy_unbound"] += 1
                    item["records"].append(result)
                    continue

                request_id = f"legacy-review-{artifact_version[:16]}-{candidate_id}-{record.get('revision', 0)}"
                if db is not None:
                    existing = db.query(MatchStateCandidateDecision).filter_by(request_id=request_id).one_or_none()
                    if existing is not None:
                        result["status"] = "skipped"
                        result["reason"] = "already_imported"
                        report["summary"]["skipped"] += 1
                        item["records"].append(result)
                        continue
                result["status"] = "imported" if apply else "would_import"
                report["summary"]["imported"] += 1
                item["records"].append(result)
                if not apply:
                    continue

                artifact_row = db.query(MatchStateCandidateArtifact).filter_by(
                    capture_take_id=take_id, artifact_version=artifact_version
                ).one_or_none()
                if artifact_row is None:
                    db.add(
                        MatchStateCandidateArtifact(
                            id=f"msa_{artifact_version[:20]}",
                            capture_take_id=take_id,
                            artifact_version=artifact_version,
                            artifact_json=artifact_raw.decode("utf-8"),
                        )
                    )
                review_row = db.query(MatchStateCandidateReview).filter_by(
                    capture_take_id=take_id, artifact_version=artifact_version
                ).one_or_none()
                if review_row is None:
                    review_row = MatchStateCandidateReview(
                        capture_take_id=take_id, artifact_version=artifact_version, revision=0
                    )
                    db.add(review_row)
                revision = int(record.get("revision") or review_row.revision + 1)
                review_row.revision = max(review_row.revision, revision)
                db.add(
                    MatchStateCandidateDecision(
                        id=f"msd_{hashlib.sha256(request_id.encode()).hexdigest()[:32]}",
                        request_id=request_id,
                        capture_take_id=take_id,
                        artifact_version=artifact_version,
                        candidate_id=candidate_id,
                        decision=str(record.get("decision") or "rejected"),
                        expected_revision=max(0, revision - 1),
                        revision=revision,
                        original_start_ms=int(record.get("original_start_ms", candidates[candidate_id]["start_ms"])),
                        original_end_ms=int(record.get("original_end_ms", candidates[candidate_id]["end_ms"])),
                        reviewed_start_ms=int(record.get("reviewed_start_ms", candidates[candidate_id]["start_ms"])),
                        reviewed_end_ms=int(record.get("reviewed_end_ms", candidates[candidate_id]["end_ms"])),
                        note=record.get("note"),
                        operation_id=record.get("operation_id"),
                        output_segment_id=output_segment_id,
                        provenance_json=json.dumps(record.get("provenance", {}), ensure_ascii=False, sort_keys=True),
                        request_payload_json=json.dumps(
                            {
                                "decision": record.get("decision"),
                                "artifact_version": artifact_version,
                                "candidate_id": candidate_id,
                                "start_ms": record.get("reviewed_start_ms"),
                                "end_ms": record.get("reviewed_end_ms"),
                                "note": record.get("note"),
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                    )
                )
            report["files"].append(item)
        if db is not None and apply:
            db.commit()
    except IntegrityError as exc:
        if db is not None:
            db.rollback()
        report["summary"]["conflicts"] += 1
        report["summary"]["imported"] = 0
        for item in report["files"]:
            for record in item["records"]:
                if record["status"] == "imported":
                    record["status"] = "rolled_back"
        report["error"] = "database conflict; import transaction rolled back"
    finally:
        if db is not None:
            db.close()
    return report


def main() -> int:
    args = _args()
    if args.database:
        import os

        os.environ["PICKLEBALL_DATABASE_PATH"] = str(args.database)
        get_settings.cache_clear()
    if args.apply:
        init_db()
    settings = get_settings()
    report = migrate(args.root or settings.resolved_match_state_candidate_dir, apply=args.apply)
    report_root = args.root or settings.resolved_match_state_candidate_dir
    report_path = args.report
    if report_path is not None or args.apply:
        report_path = report_path or report_root / "candidate-review-migration-report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, sort_keys=True))
    return 0 if not report.get("error") else 2


if __name__ == "__main__":
    raise SystemExit(main())
