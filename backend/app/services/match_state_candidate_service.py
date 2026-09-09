"""Read learned candidates and persist review decisions separately from authoritative labels."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.capture_segment import CaptureSegment
from app.models.match_state_candidate import (
    MatchStateCandidateArtifact,
    MatchStateCandidateDecision,
    MatchStateCandidateReview,
)
from app.schemas.match_state_candidate import CandidateDecision, MatchStateCandidateDecisionRequest
from app.services import segment_edit_service

REVIEW_SCHEMA_VERSION = "match-state-candidate-review.v1"


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("candidate artifact root must be an object")
    return value


def _artifact_path(root: Path, capture_take_id: str) -> Path | None:
    direct = root / f"{capture_take_id}.timeline.json"
    if direct.is_file():
        return direct
    if not root.is_dir():
        return None
    for path in sorted(root.glob("*.timeline.json")):
        try:
            if _load(path).get("capture_take_id") == capture_take_id:
                return path
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    return None


def _review_path(root: Path, capture_take_id: str) -> Path:
    return root / f"{capture_take_id}.reviews.json"


def _read_candidate_artifact(root: Path, capture_take_id: str) -> tuple[Path, bytes, dict[str, Any], str]:
    path = _artifact_path(root, capture_take_id)
    if path is None:
        raise ValueError("candidate artifact unavailable")
    raw = path.read_bytes()
    artifact = json.loads(raw.decode("utf-8"))
    if not isinstance(artifact, dict):
        raise ValueError("candidate artifact root must be an object")
    if artifact.get("schema_version") != "match_state_candidate_timeline.v1":
        raise ValueError("candidate artifact schema mismatch")
    if artifact.get("capture_take_id") != capture_take_id:
        raise ValueError("candidate artifact take identity mismatch")
    candidates = artifact.get("candidate_segments", [])
    if not isinstance(candidates, list):
        raise ValueError("candidate_segments must be a list")
    candidate_ids: list[str] = []
    for row in candidates:
        if not isinstance(row, dict):
            raise ValueError("candidate segment must be an object")
        candidate_id = str(row.get("candidate_id") or "").strip()
        if not candidate_id:
            raise ValueError("candidate_id is required")
        candidate_ids.append(candidate_id)
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("candidate_id must be unique")
    for row in candidates:
        try:
            values = [row["start_ms"], row["end_ms"]]
            if any(isinstance(value, bool) or not isinstance(value, (int, float))
                   or not math.isfinite(value) for value in values):
                raise ValueError("candidate bounds must be finite numbers")
            start, end = (int(round(value)) for value in values)
        except (KeyError, TypeError, OverflowError) as exc:
            raise ValueError("candidate bounds are missing or invalid") from exc
        if start < 0 or end <= start:
            raise ValueError("candidate segment bounds are invalid")
    return path, raw, artifact, hashlib.sha256(raw).hexdigest()


def _empty_reviews(capture_take_id: str, artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "capture_take_id": capture_take_id,
        "source": {
            "package_id": artifact.get("model", {}).get("package_id"),
            "model_version": artifact.get("model", {}).get("model_version"),
            "source_provenance": artifact.get("source_provenance", {}),
        },
        "revision": 0,
        "history": [],
    }


def _read_reviews(root: Path, capture_take_id: str, artifact: dict[str, Any]) -> dict[str, Any]:
    path = _review_path(root, capture_take_id)
    if not path.is_file():
        return _empty_reviews(capture_take_id, artifact)
    value = _load(path)
    if value.get("schema_version") != REVIEW_SCHEMA_VERSION or value.get("capture_take_id") != capture_take_id:
        raise ValueError("candidate review sidecar identity mismatch")
    return value


def _write_reviews(root: Path, capture_take_id: str, reviews: dict[str, Any]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    target = _review_path(root, capture_take_id)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(reviews, ensure_ascii=False, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def get_candidate_review(root: Path, capture_take_id: str, db: Session | None = None) -> dict[str, Any]:
    try:
        _path, raw, artifact, artifact_version = _read_candidate_artifact(root, capture_take_id)
        reviews = _read_reviews(root, capture_take_id, artifact) if db is None else {}
        if db is not None:
            rows = (
                db.query(MatchStateCandidateDecision)
                .filter(
                    MatchStateCandidateDecision.capture_take_id == capture_take_id,
                    MatchStateCandidateDecision.artifact_version == artifact_version,
                )
                .order_by(MatchStateCandidateDecision.revision.asc())
                .all()
            )
            reviews = {
                "schema_version": REVIEW_SCHEMA_VERSION,
                "capture_take_id": capture_take_id,
                "revision": db.query(MatchStateCandidateReview)
                .filter(
                    MatchStateCandidateReview.capture_take_id == capture_take_id,
                    MatchStateCandidateReview.artifact_version == artifact_version,
                )
                .with_entities(MatchStateCandidateReview.revision)
                .scalar()
                or 0,
                "history": [
                    {
                        "revision": row.revision,
                        "artifact_version": row.artifact_version,
                        "candidate_id": row.candidate_id,
                        "decision": row.decision,
                        "original_start_ms": row.original_start_ms,
                        "original_end_ms": row.original_end_ms,
                        "reviewed_start_ms": row.reviewed_start_ms,
                        "reviewed_end_ms": row.reviewed_end_ms,
                        "note": row.note,
                        "operation_id": row.operation_id,
                        "output_segment_id": row.output_segment_id,
                        "reviewed_at": row.created_at.isoformat() if row.created_at else None,
                        "provenance": json.loads(row.provenance_json or "{}"),
                    }
                    for row in rows
                ],
            }
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        reason = "candidate_artifact_missing" if str(exc) == "candidate artifact unavailable" else f"candidate_artifact_invalid:{exc}"
        return {
            "schema_version": REVIEW_SCHEMA_VERSION,
            "status": "unavailable",
            "reason": reason,
            "capture_take_id": capture_take_id,
            "revision": 0,
            "candidates": [],
        }
    latest = {str(row["candidate_id"]): row for row in reviews.get("history", []) if row.get("candidate_id")}
    candidates = []
    for candidate in artifact.get("candidate_segments", []):
        decision = latest.get(str(candidate.get("candidate_id")))
        candidates.append(
            {
                **candidate,
                "status": decision.get("decision") if decision else "unreviewed",
                "review": decision,
            }
        )
    return {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "status": "available",
        "reason": None,
        "capture_take_id": capture_take_id,
        "artifact_version": artifact_version,
        "source_session_id": artifact.get("source_session_id"),
        "revision": int(reviews.get("revision", 0)),
        "model": artifact.get("model", {}),
        "source_provenance": artifact.get("source_provenance", {}),
        "decoder": artifact.get("decoder", {}),
        "unknown_rate": (
            sum(row.get("state") == "unknown" for row in artifact.get("windows", []))
            / max(len(artifact.get("windows", [])), 1)
        ),
        "candidates": candidates,
    }


def decide_candidate(
    db: Session,
    *,
    root: Path,
    capture_take_id: str,
    candidate_id: str,
    request: MatchStateCandidateDecisionRequest,
    take_duration_ms: int,
    export_sidecar: bool = False,
) -> tuple[dict[str, Any], CaptureSegment | None]:
    existing_request = (
        db.query(MatchStateCandidateDecision)
        .filter(MatchStateCandidateDecision.request_id == request.request_id)
        .one_or_none()
    )
    if existing_request is not None:
        stored_payload = json.loads(existing_request.request_payload_json or "{}")
        same_request = all(
            stored_payload.get(key) == value
            for key, value in {
                "decision": request.decision.value,
                "candidate_id": candidate_id,
                "start_ms": request.start_ms,
                "end_ms": request.end_ms,
                "note": request.note,
            }.items()
        ) and (
            request.artifact_version in {None, stored_payload.get("artifact_version")}
        )
        if not same_request or existing_request.capture_take_id != capture_take_id:
            raise RuntimeError("request_id_conflict")
        segment = (
            db.query(CaptureSegment).filter(CaptureSegment.id == existing_request.output_segment_id).one_or_none()
            if existing_request.output_segment_id
            else None
        )
        return _decision_record(existing_request), segment

    _path, raw, artifact, artifact_version = _read_candidate_artifact(root, capture_take_id)
    if request.artifact_version and request.artifact_version != artifact_version:
        raise RuntimeError("candidate_version_conflict")

    payload_for_request = {
        "decision": request.decision.value,
        "artifact_version": artifact_version,
        "candidate_id": candidate_id,
        "start_ms": request.start_ms,
        "end_ms": request.end_ms,
        "note": request.note,
    }

    artifact_row = (
        db.query(MatchStateCandidateArtifact)
        .filter(
            MatchStateCandidateArtifact.capture_take_id == capture_take_id,
            MatchStateCandidateArtifact.artifact_version == artifact_version,
        )
        .one_or_none()
    )
    if artifact_row is None:
        artifact_row = MatchStateCandidateArtifact(
            id=f"msa_{artifact_version[:20]}",
            capture_take_id=capture_take_id,
            artifact_version=artifact_version,
            artifact_json=raw.decode("utf-8"),
        )
        db.add(artifact_row)
        db.flush()
    review = (
        db.query(MatchStateCandidateReview)
        .filter(
            MatchStateCandidateReview.capture_take_id == capture_take_id,
            MatchStateCandidateReview.artifact_version == artifact_version,
        )
        .with_for_update()
        .one_or_none()
    )
    if review is None:
        review = MatchStateCandidateReview(
            capture_take_id=capture_take_id,
            artifact_version=artifact_version,
            revision=0,
        )
        db.add(review)
        db.flush()
    current_revision = int(review.revision)
    if request.expected_revision != current_revision:
        raise RuntimeError(f"revision conflict: expected {request.expected_revision}, current {current_revision}")
    claimed = db.execute(
        update(MatchStateCandidateReview)
        .where(
            MatchStateCandidateReview.capture_take_id == capture_take_id,
            MatchStateCandidateReview.artifact_version == artifact_version,
            MatchStateCandidateReview.revision == request.expected_revision,
        )
        .values(revision=current_revision + 1, updated_at=datetime.now(UTC))
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        raise RuntimeError("candidate_revision_conflict")
    candidate = next(
        (row for row in artifact.get("candidate_segments", []) if row.get("candidate_id") == candidate_id),
        None,
    )
    if candidate is None:
        raise ValueError("candidate does not exist")
    already_decided = (
        db.query(MatchStateCandidateDecision)
        .filter(
            MatchStateCandidateDecision.capture_take_id == capture_take_id,
            MatchStateCandidateDecision.artifact_version == artifact_version,
            MatchStateCandidateDecision.candidate_id == candidate_id,
        )
        .one_or_none()
    )
    if already_decided is not None:
        raise RuntimeError("candidate_already_reviewed")
    original_start = int(round(float(candidate["start_ms"])))
    original_end = int(round(float(candidate["end_ms"])))
    reviewed_start = request.start_ms if request.decision == CandidateDecision.corrected else original_start
    reviewed_end = request.end_ms if request.decision == CandidateDecision.corrected else original_end
    provenance = {
        "artifact_version": artifact_version,
        "candidate_id": candidate_id,
        "candidate_start_ms": original_start,
        "candidate_end_ms": original_end,
        "candidate_confidence": candidate.get("confidence"),
        "model": artifact.get("model", {}),
        "source_provenance": artifact.get("source_provenance", {}),
        "decoder": artifact.get("decoder", {}),
        "review_revision": current_revision + 1,
    }
    segment: CaptureSegment | None = None
    if request.decision in {CandidateDecision.accepted, CandidateDecision.corrected}:
        segment = segment_edit_service.create_manual_rally(
            db,
            capture_take_id=capture_take_id,
            start_ms=int(reviewed_start),
            end_ms=int(reviewed_end),
            take_duration_ms=take_duration_ms,
            provenance={**provenance, "decision": request.decision.value},
        )
        operation_id = segment.created_by_operation_id
    else:
        operation_id = segment_edit_service.record_candidate_rejection(
            db,
            capture_take_id=capture_take_id,
            candidate_id=candidate_id,
            provenance=provenance,
            note=request.note,
        )
    decision_row = MatchStateCandidateDecision(
        id=f"msd_{uuid4().hex[:20]}",
        request_id=request.request_id,
        capture_take_id=capture_take_id,
        artifact_version=artifact_version,
        candidate_id=candidate_id,
        decision=request.decision.value,
        expected_revision=current_revision,
        revision=current_revision + 1,
        original_start_ms=original_start,
        original_end_ms=original_end,
        reviewed_start_ms=int(reviewed_start),
        reviewed_end_ms=int(reviewed_end),
        note=request.note,
        operation_id=operation_id,
        output_segment_id=segment.id if segment else None,
        provenance_json=json.dumps(provenance, ensure_ascii=False, sort_keys=True),
        request_payload_json=json.dumps(payload_for_request, ensure_ascii=False, sort_keys=True),
    )
    db.add(decision_row)
    db.flush()
    # Export is performed by the caller after commit, never inside this transaction.
    return _decision_record(decision_row), segment


def _decision_record(row: MatchStateCandidateDecision) -> dict[str, Any]:
    return {
        "revision": row.revision,
        "artifact_version": row.artifact_version,
        "candidate_id": row.candidate_id,
        "decision": row.decision,
        "original_start_ms": row.original_start_ms,
        "original_end_ms": row.original_end_ms,
        "reviewed_start_ms": row.reviewed_start_ms,
        "reviewed_end_ms": row.reviewed_end_ms,
        "note": row.note,
        "operation_id": row.operation_id,
        "output_segment_id": row.output_segment_id,
        "reviewed_at": row.created_at.replace(tzinfo=UTC).isoformat() if row.created_at else None,
        "provenance": json.loads(row.provenance_json or "{}"),
    }


def export_review_record(root: Path, capture_take_id: str, record: dict[str, Any], db: Session | None = None) -> None:
    """Best-effort compatibility export after the database transaction commits."""
    if db is not None:
        rows = db.query(MatchStateCandidateDecision).filter_by(capture_take_id=capture_take_id).order_by(
            MatchStateCandidateDecision.created_at, MatchStateCandidateDecision.revision
        ).all()
        _write_reviews(root, capture_take_id, {
            "schema_version": REVIEW_SCHEMA_VERSION,
            "capture_take_id": capture_take_id,
            "revision": record["revision"],
            "artifact_version": record["artifact_version"],
            "history": [_decision_record(row) for row in rows],
        })
        return
    _path, _raw, artifact, _version = _read_candidate_artifact(root, capture_take_id)
    reviews = _read_reviews(root, capture_take_id, artifact)
    if any(
        row.get("candidate_id") == record.get("candidate_id") and row.get("revision") == record.get("revision")
        and row.get("artifact_version") == record.get("artifact_version")
        for row in reviews.get("history", [])
    ):
        return
    reviews.setdefault("history", []).append(record)
    reviews["revision"] = max(int(reviews.get("revision", 0)), int(record.get("revision", 0)))
    _write_reviews(root, capture_take_id, reviews)
