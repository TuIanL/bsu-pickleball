from __future__ import annotations

import json
from datetime import UTC, datetime

from app.services.match_state_candidate_service import get_candidate_review


def _artifact(take_id: str) -> dict:
    return {
        "schema_version": "match_state_candidate_timeline.v1",
        "capture_take_id": take_id,
        "source_session_id": "sync_test",
        "model": {"package_id": "pkg", "model_version": "v1"},
        "source_provenance": {"dataset_manifest_sha256": "a" * 64},
        "decoder": {"minimum_confidence": 0.6},
        "windows": [{"state": "unknown"}, {"state": "rally_active"}],
        "candidate_segments": [
            {
                "candidate_id": "candidate_0001",
                "segment_index": 1,
                "start_ms": 1000,
                "end_ms": 5000,
                "duration_ms": 4000,
                "confidence": 0.9,
                "evidence_window_count": 8,
                "status": "unreviewed",
            }
        ],
        "review_status": "unreviewed",
    }


def test_missing_candidate_artifact_fails_open(tmp_path):
    result = get_candidate_review(tmp_path, "ct_missing")
    assert result["status"] == "unavailable"
    assert result["reason"] == "candidate_artifact_missing"
    assert result["candidates"] == []


def test_invalid_candidate_artifact_fails_open(tmp_path):
    (tmp_path / "ct_bad.timeline.json").write_text("{}", encoding="utf-8")
    result = get_candidate_review(tmp_path, "ct_bad")
    assert result["status"] == "unavailable"
    assert result["reason"].startswith("candidate_artifact_invalid:")


def test_review_sidecar_is_merged_without_mutating_artifact(tmp_path):
    take_id = "ct_test"
    artifact = _artifact(take_id)
    artifact_path = tmp_path / f"{take_id}.timeline.json"
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    review = {
        "schema_version": "match-state-candidate-review.v1",
        "capture_take_id": take_id,
        "revision": 1,
        "history": [
            {
                "revision": 1,
                "candidate_id": "candidate_0001",
                "decision": "rejected",
                "reviewed_at": "2026-09-03T00:00:00+00:00",
            }
        ],
    }
    (tmp_path / f"{take_id}.reviews.json").write_text(json.dumps(review), encoding="utf-8")

    result = get_candidate_review(tmp_path, take_id)

    assert result["status"] == "available"
    assert result["revision"] == 1
    assert result["unknown_rate"] == 0.5
    assert result["candidates"][0]["status"] == "rejected"
    assert json.loads(artifact_path.read_text(encoding="utf-8"))["candidate_segments"][0]["status"] == "unreviewed"


def _create_take(db, take_id: str):
    from app.models.capture_take import CaptureMode, CaptureTake, CaptureTakeStatus, SourceSessionType
    from app.models.field_session import CameraSetup, FieldSession, MatchFormat
    from app.models.field_session import CaptureMode as FieldCaptureMode

    now = datetime.now(UTC)
    field = FieldSession(
        id=f"field-{take_id}",
        title="candidate review",
        capture_mode=FieldCaptureMode.match,
        match_format=MatchFormat.singles,
        camera_setup=CameraSetup.single,
    )
    take = CaptureTake(
        id=take_id,
        field_session_id=field.id,
        capture_mode=CaptureMode.single,
        source_session_type=SourceSessionType.recording,
        source_session_id=f"source-{take_id}",
        status=CaptureTakeStatus.completed,
        started_at=now,
        created_at=now,
        updated_at=now,
        duration_ms=20_000,
    )
    db.add_all([field, take])
    db.commit()


def test_decision_rollback_leaves_no_review_or_segment(tmp_path, isolated_database):
    from app.schemas.match_state_candidate import MatchStateCandidateDecisionRequest
    from app.services import match_state_candidate_service

    take_id = "ct-rollback"
    _create_take(isolated_database(), take_id)
    root = tmp_path / "candidates"
    root.mkdir()
    artifact_path = root / f"{take_id}.timeline.json"
    artifact_path.write_text(json.dumps(_artifact(take_id)), encoding="utf-8")
    version = get_candidate_review(root, take_id)["artifact_version"]
    db = isolated_database()
    record, _segment = match_state_candidate_service.decide_candidate(
        db,
        root=root,
        capture_take_id=take_id,
        candidate_id="candidate_0001",
        request=MatchStateCandidateDecisionRequest(
            decision="accepted", expected_revision=0, artifact_version=version, request_id="rollback-request"
        ),
        take_duration_ms=20_000,
        export_sidecar=False,
    )
    assert record["decision"] == "accepted"
    db.rollback()
    assert get_candidate_review(root, take_id, db)["revision"] == 0
    from app.models.capture_segment import CaptureSegment
    from app.models.match_state_candidate import MatchStateCandidateDecision

    assert db.query(CaptureSegment).filter_by(capture_take_id=take_id).count() == 0
    assert db.query(MatchStateCandidateDecision).count() == 0


def test_new_artifact_version_does_not_inherit_decision_and_retry_replays(tmp_path, isolated_database):
    from app.models.capture_segment import CaptureSegment
    from app.schemas.match_state_candidate import MatchStateCandidateDecisionRequest
    from app.services import match_state_candidate_service

    take_id = "ct-versioned"
    _create_take(isolated_database(), take_id)
    root = tmp_path / "candidates"
    root.mkdir()
    artifact_path = root / f"{take_id}.timeline.json"
    artifact_path.write_text(json.dumps(_artifact(take_id)), encoding="utf-8")
    old_version = get_candidate_review(root, take_id)["artifact_version"]
    db = isolated_database()
    request = MatchStateCandidateDecisionRequest(
        decision="accepted", expected_revision=0, artifact_version=old_version, request_id="stable-retry"
    )
    first, first_segment = match_state_candidate_service.decide_candidate(
        db,
        root=root,
        capture_take_id=take_id,
        candidate_id="candidate_0001",
        request=request,
        take_duration_ms=20_000,
        export_sidecar=False,
    )
    db.commit()
    artifact = _artifact(take_id)
    artifact["windows"].append({"state": "rally_active"})
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    current = get_candidate_review(root, take_id, db)
    assert current["artifact_version"] != old_version
    assert current["revision"] == 0
    assert current["candidates"][0]["status"] == "unreviewed"

    replay, replay_segment = match_state_candidate_service.decide_candidate(
        db,
        root=root,
        capture_take_id=take_id,
        candidate_id="candidate_0001",
        request=request,
        take_duration_ms=20_000,
        export_sidecar=False,
    )
    assert replay["revision"] == first["revision"]
    assert replay_segment is not None and replay_segment.id == first_segment.id
    assert db.query(CaptureSegment).filter_by(capture_take_id=take_id).count() == 1
