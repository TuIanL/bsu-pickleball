"""Persistence boundary for formal match-state segmentation runs."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.capture_segment import CaptureSegment, EditStatus, SegmentSource, SegmentStatus, SegmentType
from app.models.match_state_segmentation import MatchStateSegmentationRun, MatchStateSegmentationRunStatus
from app.services.storage_service import StorageService
from app.vision.match_state.artifact import SegmentationArtifact


def _run_id() -> str:
    return f"seg_{uuid4().hex[:16]}"


def _artifact_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def persist_segmentation_result(
    db: Session,
    *,
    artifact: SegmentationArtifact,
    storage: StorageService,
    package_sha256: str | None = None,
    weights_sha256: str | None = None,
    decoder_sha256: str | None = None,
) -> MatchStateSegmentationRun:
    """Write an artifact and switch active algorithm segments atomically.

    The caller owns the surrounding transaction.  No manual segment is ever
    selected by the supersede query.
    """
    payload = artifact.to_dict()
    run = db.get(MatchStateSegmentationRun, artifact.run_id)
    if run is None:
        run = MatchStateSegmentationRun(
            id=artifact.run_id,
            capture_take_id=artifact.capture_take_id,
            planning_job_id=artifact.planning_job_id,
            status=MatchStateSegmentationRunStatus(artifact.status),
            profile=str(artifact.model.get("profile") or "match_default"),
            model_package_id=str(artifact.model.get("package_id")) if artifact.model.get("package_id") else None,
            model_package_version=str(artifact.model.get("model_version")) if artifact.model.get("model_version") else None,
            package_sha256=package_sha256 or artifact.model.get("package_sha256"),
            weights_sha256=weights_sha256 or artifact.model.get("weights_sha256"),
            decoder_sha256=decoder_sha256 or artifact.model.get("decoder_sha256"),
            input_fingerprint=str(artifact.input_provenance.get("input_fingerprint")) if artifact.input_provenance.get("input_fingerprint") else None,
            sync_calibration_revision=artifact.input_provenance.get("sync_calibration_revision"),
            timing_authority=str(artifact.input_provenance.get("timing_authority")) if artifact.input_provenance.get("timing_authority") else None,
            window_plan_hash=artifact.window_plan.plan_hash,
            unknown_rate=float(artifact.state_summary.get("unknown_rate", 0.0)),
            segment_count=len(artifact.algorithm_segments),
            diagnostics_json=json.dumps({}, ensure_ascii=False),
            plan_json=json.dumps(artifact.window_plan.to_dict(), ensure_ascii=False, sort_keys=True),
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
        )
        db.add(run)
        db.flush()
    if run.status not in {MatchStateSegmentationRunStatus.succeeded, MatchStateSegmentationRunStatus.valid_no_rallies}:
        run.status = MatchStateSegmentationRunStatus(artifact.status)
    if artifact.status in {"succeeded", "valid_no_rallies"}:
        previous = (
            db.query(MatchStateSegmentationRun)
            .filter(
                MatchStateSegmentationRun.capture_take_id == artifact.capture_take_id,
                MatchStateSegmentationRun.id != artifact.run_id,
                MatchStateSegmentationRun.status.in_([
                    MatchStateSegmentationRunStatus.succeeded,
                    MatchStateSegmentationRunStatus.valid_no_rallies,
                ]),
            )
            .order_by(MatchStateSegmentationRun.finished_at.desc())
            .first()
        )
        if previous is not None:
            previous.status = MatchStateSegmentationRunStatus.superseded
            run.supersedes_run_id = previous.id
            db.query(CaptureSegment).filter(
                CaptureSegment.capture_take_id == artifact.capture_take_id,
                CaptureSegment.segmentation_run_id == previous.id,
                CaptureSegment.source == SegmentSource.algorithm,
                CaptureSegment.edit_status == EditStatus.active,
            ).update({"edit_status": EditStatus.superseded}, synchronize_session=False)
        for index, item in enumerate(artifact.algorithm_segments, start=1):
            segment_id = str(item.get("segment_id") or f"sg_{uuid4().hex[:16]}")
            if db.get(CaptureSegment, segment_id) is not None:
                continue
            db.add(
                CaptureSegment(
                    id=segment_id,
                    capture_take_id=artifact.capture_take_id,
                    segment_type=SegmentType.rally,
                    ordinal=int(item.get("ordinal", index)),
                    label=f"第{int(item.get('ordinal', index))}回合",
                    start_ms=int(item["start_ms"]),
                    end_ms=int(item["end_ms"]),
                    status=SegmentStatus.inferred,
                    source=SegmentSource.algorithm,
                    edit_status=EditStatus.active,
                    segmentation_run_id=artifact.run_id,
                    close_reason="match_state_segmentation",
                )
            )
    db.flush()
    artifact_path = storage.formal_segmentation_artifact_path(artifact.planning_job_id, artifact.capture_take_id)
    storage.write_json_atomic(artifact_path, payload)
    run.artifact_path = storage.logical_artifact_reference(artifact.planning_job_id, artifact_path)
    run.artifact_sha256 = _artifact_hash(payload)
    db.flush()
    return run


def persist_segmentation_failure(
    db: Session,
    *,
    planning_job_id: str,
    capture_take_id: str,
    status: str,
    profile: str,
    input_fingerprint: str | None = None,
    sync_calibration_revision: int | None = None,
    timing_authority: str | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> MatchStateSegmentationRun:
    """Record a failed prerequisite without touching a prior successful run.

    Failure runs are deliberately artifact-less: they remain auditable while
    the last published algorithm segments and immutable plan stay intact.
    """
    try:
        run_status = MatchStateSegmentationRunStatus(status)
    except ValueError as exc:
        raise ValueError(f"unsupported segmentation failure status: {status}") from exc
    if run_status in {
        MatchStateSegmentationRunStatus.succeeded,
        MatchStateSegmentationRunStatus.valid_no_rallies,
        MatchStateSegmentationRunStatus.superseded,
    }:
        raise ValueError(f"status is not a failure status: {status}")
    run_id = _run_id()
    run = MatchStateSegmentationRun(
        id=run_id,
        capture_take_id=capture_take_id,
        planning_job_id=planning_job_id,
        status=run_status,
        profile=profile,
        input_fingerprint=input_fingerprint,
        sync_calibration_revision=sync_calibration_revision,
        timing_authority=timing_authority,
        diagnostics_json=json.dumps(diagnostics or {}, ensure_ascii=False, sort_keys=True),
        plan_json=json.dumps({}, ensure_ascii=False),
        segment_count=0,
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
    )
    db.add(run)
    db.flush()
    return run


def get_bound_formal_artifact(storage: StorageService, *, job_id: str, capture_take_id: str | None) -> dict[str, Any] | None:
    if not capture_take_id:
        return None
    path = storage.formal_segmentation_artifact_path(job_id, capture_take_id, create_root=False)
    if not path.is_file():
        return None
    try:
        payload = storage.read_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if payload.get("planning_job_id") != job_id or payload.get("capture_take_id") != capture_take_id:
        return None
    return payload
