import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from app.database import Base
from app.database import get_db
from app.main import app
from app.models.capture_take import CaptureMode, CaptureTake, CaptureTakeStatus, SourceSessionType
from app.models.capture_track import CaptureTrack, CaptureTrackSlot, TrackRole
from app.models.field_session import CaptureMode as FieldCaptureMode
from app.models.field_session import FieldSession, MatchFormat
from app.schemas.scoring_calibration_annotation import (
    AnnotationPackageCreateRequest,
    AnnotationPackageRevisionRequest,
    AnnotationDecision,
    AnnotationUpsertRequest,
    LandingStatus,
    LandingZone,
    OpportunityStatus,
    ShotOutcome,
    ShotStage,
)
from app.services import scoring_calibration_annotation_service as service


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _take(db: Session, *, video_id: str | None = "video-local") -> CaptureTake:
    field_session = FieldSession(
        id="fs_scoring",
        title="评分校准测试",
        capture_mode=FieldCaptureMode.match,
        match_format=MatchFormat.doubles,
    )
    take = CaptureTake(
        id="ct_scoring",
        field_session_id=field_session.id,
        capture_mode=CaptureMode.single,
        source_session_type=SourceSessionType.recording,
        source_session_id="rec_scoring",
        status=CaptureTakeStatus.completed,
        duration_ms=10_000,
        started_at=datetime.now(UTC),
    )
    track = CaptureTrack(
        id="track_scoring",
        capture_take_id=take.id,
        camera_id="cam_1",
        role=TrackRole.primary,
        slot=CaptureTrackSlot.cam_1,
        video_id=video_id,
    )
    db.add_all([field_session, take, track])
    db.commit()
    return take


def _valid_annotation() -> AnnotationUpsertRequest:
    return AnnotationUpsertRequest(
        event_ms=1_000,
        evidence_start_ms=900,
        evidence_end_ms=1_300,
        video_id="video-local",
        stage=ShotStage.serve,
        opportunity_status=OpportunityStatus.eligible,
        outcome=ShotOutcome.in_play,
        landing_status=LandingStatus.measured,
        landing_zone=LandingZone.deep,
        decision=AnnotationDecision.accepted,
    )


def test_package_lifecycle_locks_gold_set_and_requires_new_revision(db):
    take = _take(db)
    package_payload = service.create_package(db, take.id, AnnotationPackageCreateRequest(annotator="教练 A"))
    package = service.get_package(db, package_payload["id"])
    assert package is not None

    service.create_annotation(db, package, _valid_annotation())
    db.commit()
    package = service.get_package(db, package.id)
    assert package is not None

    locked = service.lock_package(db, package)
    db.commit()
    assert locked["status"] == "locked"
    gold = service.get_gold_set(db, package)
    assert gold.status.value == "locked"
    assert len(gold.annotations) == 1

    with pytest.raises(service.ScoringCalibrationError, match="只读"):
        service.create_annotation(db, package, _valid_annotation())

    revision = service.create_revision(db, package, AnnotationPackageRevisionRequest(note="复核版本"))
    assert revision["revision"] == 2
    assert revision["status"] == "draft"
    assert len(revision["annotations"]) == 1


def test_lock_rejects_missing_semantics_and_keeps_draft(db):
    take = _take(db)
    package_payload = service.create_package(db, take.id, AnnotationPackageCreateRequest())
    package = service.get_package(db, package_payload["id"])
    assert package is not None
    service.create_annotation(
        db,
        package,
        AnnotationUpsertRequest(
            event_ms=500,
            evidence_start_ms=400,
            evidence_end_ms=600,
            decision=AnnotationDecision.accepted,
            opportunity_status=OpportunityStatus.eligible,
            outcome=ShotOutcome.net,
            landing_status=LandingStatus.measured,
            landing_zone=LandingZone.deep,
        ),
    )
    with pytest.raises(service.ScoringCalibrationValidationError) as error:
        service.lock_package(db, package)
    assert any(issue.code == "missing_required_fields" for issue in error.value.issues)
    assert package.status == "draft"


def test_package_without_video_is_blocked(db):
    take = _take(db, video_id=None)
    with pytest.raises(service.ScoringCalibrationError, match="没有可播放视频"):
        service.create_package(db, take.id, AnnotationPackageCreateRequest())


def test_persisted_candidates_are_filtered_by_registered_video_and_keep_provenance(db, tmp_path):
    take = _take(db)
    take.session_dir = str(tmp_path)
    analysis = tmp_path / "analysis"
    good_job = analysis / "job-good"
    bad_job = analysis / "job-bad"
    good_job.mkdir(parents=True)
    bad_job.mkdir(parents=True)
    for job_dir, video_id in ((good_job, "video-local"), (bad_job, "video-not-this-take")):
        (job_dir / "result.json").write_text(json.dumps({"video_id": video_id}), encoding="utf-8")
        (job_dir / "serve_events.json").write_text(json.dumps({
            "detector_version": "serve-v2",
            "coverage": {"warnings": ["镜头遮挡"]},
            "events": [{"id": f"serve-{video_id}", "timestamp_ms": 1200, "score": 0.82}],
        }), encoding="utf-8")

    candidates = service._load_algorithm_candidates(take.id, db=db)

    assert len(candidates) == 1
    assert candidates[0].source_job_id == "job-good"
    assert candidates[0].artifact_name == "job-good/serve_events.json"
    assert candidates[0].detector_version == "serve-v2"
    assert candidates[0].coverage_warning == "镜头遮挡"
    assert candidates[0].confidence == pytest.approx(0.82)


def test_candidate_source_explains_empty_matching_artifacts(db, tmp_path):
    take = _take(db)
    take.session_dir = str(tmp_path)
    job_dir = tmp_path / "analysis" / "job-other"
    job_dir.mkdir(parents=True)
    (job_dir / "result.json").write_text(json.dumps({"video_id": "video-other"}), encoding="utf-8")
    (job_dir / "serve_events.json").write_text(json.dumps({"events": [{"timestamp_ms": 800}]}), encoding="utf-8")
    package_payload = service.create_package(db, take.id, AnnotationPackageCreateRequest())
    package = service.get_package(db, package_payload["id"])
    assert package is not None

    summary = service._package_summary(db, package)

    assert summary["candidates"] == []
    assert summary["candidate_status"] == "empty"
    assert "没有与当前 CaptureTake 视频匹配" in summary["candidate_message"]


def test_annotation_api_covers_lock_and_revision_lifecycle(db):
    take = _take(db)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            created = client.post(
                f"/api/capture-takes/{take.id}/scoring-calibration/packages",
                json={"annotator": "API 测试"},
            )
            assert created.status_code == 201
            revision_id = created.json()["id"]
            listed = client.get(f"/api/capture-takes/{take.id}/scoring-calibration/packages")
            assert listed.status_code == 200
            assert [item["id"] for item in listed.json()] == [revision_id]
            not_ready = client.get(f"/api/capture-takes/{take.id}/scoring-calibration/gold-set-status")
            assert not_ready.status_code == 200
            assert not_ready.json()["status"] == "not_ready"
            annotation = client.post(
                f"/api/scoring-calibration/packages/{revision_id}/annotations",
                json={
                    "event_ms": 1000,
                    "evidence_start_ms": 900,
                    "evidence_end_ms": 1200,
                    "video_id": "video-local",
                    "stage": "serve",
                    "opportunity_status": "eligible",
                    "outcome": "in_play",
                    "landing_status": "measured",
                    "landing_zone": "deep",
                    "decision": "accepted",
                },
            )
            assert annotation.status_code == 201
            locked = client.post(f"/api/scoring-calibration/packages/{revision_id}/lock")
            assert locked.status_code == 200
            gold = client.get(f"/api/scoring-calibration/packages/{revision_id}/gold-set")
            assert gold.status_code == 200
            assert gold.json()["status"] == "locked"
            available = client.get(f"/api/capture-takes/{take.id}/scoring-calibration/gold-set-status")
            assert available.json()["status"] == "available"
            blocked = client.post(
                f"/api/scoring-calibration/packages/{revision_id}/annotations",
                json={
                    "event_ms": 1500,
                    "evidence_start_ms": 1400,
                    "evidence_end_ms": 1600,
                    "stage": "return",
                    "opportunity_status": "unobservable",
                    "outcome": "unknown",
                    "landing_status": "unobservable",
                    "landing_zone": "unknown",
                    "decision": "accepted",
                },
            )
            assert blocked.status_code == 409
            next_revision = client.post(f"/api/scoring-calibration/packages/{revision_id}/revisions", json={"note": "复核"})
            assert next_revision.status_code == 201
            assert next_revision.json()["revision"] == 2
    finally:
        app.dependency_overrides.pop(get_db, None)
