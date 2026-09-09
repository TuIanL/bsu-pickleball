"""Real SQLite transactions exercised through the candidate HTTP boundary."""
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.api.routes_segment_editing import router2
from app.core import config
from app.database import get_db
from app.models.capture_segment import CaptureSegment
from app.models.match_state_candidate import MatchStateCandidateDecision, MatchStateCandidateReview
from app.models.segment_edit_operation import SegmentEditOperation
from app.services import match_state_candidate_service as service
from test_match_state_candidate_service import _artifact, _create_take


@pytest.fixture
def candidate_api(tmp_path, monkeypatch, isolated_database):
    root = tmp_path / "candidates"
    root.mkdir()
    monkeypatch.setenv("PICKLEBALL_MATCH_STATE_CANDIDATE_DIR", str(root))
    config.get_settings.cache_clear()
    with isolated_database() as db:
        _create_take(db, "api-take")
    artifact = _artifact("api-take")
    artifact["candidate_segments"] += [
        {"candidate_id": "second", "start_ms": 6000, "end_ms": 9000},
        {"candidate_id": "third", "start_ms": 11000, "end_ms": 14000},
    ]
    path = root / "api-take.timeline.json"
    path.write_text(json.dumps(artifact))
    app = FastAPI()
    app.include_router(router2)

    def sessions():
        with isolated_database() as db:
            yield db

    app.dependency_overrides[get_db] = sessions
    client = TestClient(app)
    base = "/api/capture-takes/api-take/match-state-candidates"
    version = client.get(base).json()["artifact_version"]
    return client, base, version, path, isolated_database


def test_accept_correct_reject_replay_and_broken_export(candidate_api, monkeypatch):
    client, base, version, path, factory = candidate_api

    def broken(*args, **kwargs):
        raise OSError("injected export failure")

    monkeypatch.setattr(service, "export_review_record", broken)
    for revision, (candidate, decision) in enumerate([
        ("candidate_0001", "accepted"), ("second", "corrected"), ("third", "rejected")
    ]):
        payload = dict(decision=decision, expected_revision=revision, artifact_version=version,
                       request_id=f"api-request-{revision}")
        if decision == "corrected":
            payload.update(start_ms=6500, end_ms=9500)
        url = f"{base}/{candidate}/decision"
        response = client.post(url, json=payload)
        assert response.status_code == 200, response.text
        assert client.post(url, json=payload).json()["record"] == response.json()["record"]
        assert client.post(url, json={**payload, "note": "different"}).status_code == 409
    # A malformed optional export cannot hide committed database decisions.
    path.with_name("api-take.reviews.json").write_text("broken JSON")
    assert client.get(base).json()["revision"] == 3
    with factory() as db:
        assert db.query(CaptureSegment).count() == 2
        assert db.query(MatchStateCandidateDecision).count() == 3
        assert db.query(SegmentEditOperation).count() == 3
    artifact = json.loads(path.read_text())
    artifact["decoder"]["minimum_confidence"] = 0.7
    path.write_text(json.dumps(artifact))
    assert client.get(base).json()["revision"] == 0
    assert client.post(url, json=payload).status_code == 200


def test_commit_failure_rolls_back_every_entity(candidate_api):
    client, base, version, _, factory = candidate_api

    def fail_commit(session):
        raise RuntimeError("injected commit failure")

    event.listen(factory, "before_commit", fail_commit)
    try:
        response = client.post(f"{base}/candidate_0001/decision", json=dict(
            decision="accepted", expected_revision=0, artifact_version=version, request_id="commit-failure"
        ))
        assert response.status_code == 409
    finally:
        event.remove(factory, "before_commit", fail_commit)
    with factory() as db:
        for model in (CaptureSegment, SegmentEditOperation, MatchStateCandidateDecision, MatchStateCandidateReview):
            assert db.query(model).count() == 0


def test_two_connections_cannot_claim_same_revision(candidate_api):
    client, base, version, _, factory = candidate_api
    # Seed revision 1 so this tests conditional UPDATE, not first-insert uniqueness.
    assert client.post(f"{base}/third/decision", json=dict(
        decision="rejected", expected_revision=0, artifact_version=version, request_id="seed-revision"
    )).status_code == 200
    barrier = Barrier(2)

    def submit(candidate):
        barrier.wait(timeout=5)
        return client.post(f"{base}/{candidate}/decision", json=dict(
            decision="accepted", expected_revision=1, artifact_version=version, request_id=f"race-{candidate}"
        )).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(submit, ["candidate_0001", "second"])) == [200, 409]
    with factory() as db:
        assert db.query(CaptureSegment).count() == 1
        assert db.query(MatchStateCandidateDecision).count() == 2
        assert db.query(MatchStateCandidateReview).one().revision == 2


@pytest.mark.parametrize("bad", [None, float("inf"), "NaN", True])
def test_invalid_bounds_are_unavailable(candidate_api, bad):
    client, base, version, path, _ = candidate_api
    artifact = json.loads(path.read_text())
    artifact["candidate_segments"][0]["start_ms"] = bad
    path.write_text(json.dumps(artifact))
    assert client.get(base).json()["status"] == "unavailable"
    assert client.post(f"{base}/candidate_0001/decision", json=dict(
        decision="accepted", expected_revision=0, artifact_version=version, request_id="invalid-bounds"
    )).status_code == 400


def test_legacy_import_dry_run_repeat_and_broken_references(candidate_api, monkeypatch):
    from backend.scripts import migrate_candidate_reviews as migration
    from app.models.match_state_candidate import MatchStateCandidateArtifact

    client, base, version, path, factory = candidate_api
    monkeypatch.setattr(migration, 'get_session_factory', lambda: factory)
    response = client.post(f'{base}/candidate_0001/decision', json=dict(
        decision='accepted', expected_revision=0, artifact_version=version, request_id='legacy-source'
    ))
    assert response.status_code == 200
    sidecar = path.with_name('api-take.reviews.json')
    source_bytes = sidecar.read_bytes()
    with factory() as db:
        db.query(MatchStateCandidateDecision).delete()
        db.query(MatchStateCandidateReview).delete()
        db.query(MatchStateCandidateArtifact).delete()
        db.commit()
    assert migration.migrate(path.parent, apply=False)['summary']['imported'] == 1
    with factory() as db:
        assert db.query(MatchStateCandidateDecision).count() == 0
    assert migration.migrate(path.parent, apply=True)['summary']['imported'] == 1
    assert migration.migrate(path.parent, apply=True)['summary']['skipped'] == 1
    assert sidecar.read_bytes() == source_bytes
    broken = json.loads(source_bytes)
    broken['history'][0]['output_segment_id'] = 'missing-segment'
    sidecar.write_text(json.dumps(broken))
    assert migration.migrate(path.parent, apply=False)['summary']['legacy_unbound'] == 1
    with factory() as db:
        assert db.query(CaptureSegment).count() == 1
        assert db.query(SegmentEditOperation).count() == 1
