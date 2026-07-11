from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.camera.camera_registry import CAMERAS
from app.camera.models import RecordingSession
from app.camera.session_service import SESSIONS, session_service
import app.camera.session_service as recording_service_module
from app.core import config
from app.database import Base, get_engine, init_db, reset_database_state
from app.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PICKLEBALL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PICKLEBALL_DATABASE_PATH", str(tmp_path / "data" / "test.sqlite3"))
    config.get_settings.cache_clear()
    reset_database_state()
    init_db()

    CAMERAS.clear()
    SESSIONS.clear()
    monkeypatch.setattr(recording_service_module, "_ACTIVE_CAMERA", None)
    monkeypatch.setattr(recording_service_module, "_ACTIVE_SESSION_ID", None)

    yield TestClient(app, raise_server_exceptions=False)

    Base.metadata.drop_all(bind=get_engine())
    reset_database_state()
    config.get_settings.cache_clear()
    CAMERAS.clear()
    SESSIONS.clear()


def _create_field_session(client: TestClient, **overrides) -> dict:
    payload = {
        "title": "北体训练",
        "venue": "北京体育大学",
        "court_name": "A 场",
        "capture_mode": "practice",
        "match_format": "doubles",
        "camera_setup": "single",
        "notes": "baseline test",
    }
    payload.update(overrides)
    response = client.post("/api/field-sessions", json=payload)
    assert response.status_code == 201
    return response.json()


def _register_camera(client: TestClient, camera_id: str = "cam-a") -> None:
    response = client.post(
        "/api/cameras",
        json={
            "camera_id": camera_id,
            "name": camera_id,
            "stream_url": "rtsp://example.invalid/live",
            "protocol": "rtsp",
        },
    )
    assert response.status_code == 201


def test_database_uses_temp_sqlite_file(client, tmp_path):
    assert (tmp_path / "data" / "test.sqlite3").exists()


def test_create_field_session_defaults_and_rejects_invalid_enums(client):
    created = _create_field_session(client)

    assert created["id"].startswith("fs_")
    assert created["status"] == "planned"
    assert created["started_at"] is None
    assert created["ended_at"] is None
    assert created["created_at"]
    assert created["updated_at"]

    invalid = client.post(
        "/api/field-sessions",
        json={
            "title": "bad",
            "capture_mode": "bad-value",
            "match_format": "bad-format",
            "camera_setup": "bad-setup",
        },
    )
    assert invalid.status_code == 422


def test_field_session_ids_are_unique_for_rapid_creates(client):
    first = _create_field_session(client, title="first")
    second = _create_field_session(client, title="second")

    assert first["id"] != second["id"]


def test_list_filter_and_read_field_sessions(client):
    practice = _create_field_session(client, title="practice", capture_mode="practice", match_format="doubles")
    match = _create_field_session(client, title="match", capture_mode="match", match_format="singles")

    listed = client.get("/api/field-sessions")
    assert listed.status_code == 200
    ids = [item["id"] for item in listed.json()]
    assert practice["id"] in ids
    assert match["id"] in ids

    filtered = client.get("/api/field-sessions", params={"capture_mode": "match", "match_format": "singles"})
    assert filtered.status_code == 200
    assert [item["id"] for item in filtered.json()] == [match["id"]]

    detail = client.get(f"/api/field-sessions/{practice['id']}")
    assert detail.status_code == 200
    assert detail.json()["title"] == "practice"

    missing = client.get("/api/field-sessions/missing")
    assert missing.status_code == 404


def test_update_metadata_does_not_change_status(client):
    created = _create_field_session(client)

    updated = client.patch(
        f"/api/field-sessions/{created['id']}",
        json={"title": "更新标题", "notes": "更新备注", "match_format": "singles"},
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["title"] == "更新标题"
    assert body["notes"] == "更新备注"
    assert body["match_format"] == "singles"
    assert body["status"] == "planned"

    invalid = client.patch(f"/api/field-sessions/{created['id']}", json={"camera_setup": "bad"})
    assert invalid.status_code == 422


def test_field_session_status_transitions(client):
    created = _create_field_session(client)

    started = client.post(f"/api/field-sessions/{created['id']}/start")
    assert started.status_code == 200
    assert started.json()["status"] == "live"
    assert started.json()["started_at"] is not None

    completed = client.post(f"/api/field-sessions/{created['id']}/complete")
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert completed.json()["ended_at"] is not None

    archived = client.post(f"/api/field-sessions/{created['id']}/archive")
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    invalid = client.post(f"/api/field-sessions/{created['id']}/start")
    assert invalid.status_code == 400


def test_delete_empty_field_session_and_block_protected_sessions(client):
    empty = _create_field_session(client, title="empty")
    deleted = client.delete(f"/api/field-sessions/{empty['id']}")
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"
    assert client.get(f"/api/field-sessions/{empty['id']}").status_code == 404

    live = _create_field_session(client, title="live")
    assert client.post(f"/api/field-sessions/{live['id']}/start").status_code == 200
    live_delete = client.delete(f"/api/field-sessions/{live['id']}")
    assert live_delete.status_code == 409
    assert client.get(f"/api/field-sessions/{live['id']}").status_code == 200

    linked = _create_field_session(client, title="linked")
    now = datetime.now(timezone.utc)
    session_service._persist(
        RecordingSession(
            session_id="rec_delete_guard",
            camera_id="cam-a",
            field_session_id=linked["id"],
            court_name="A 场",
            match_format="doubles",
            camera_angle="baseline_high",
            fps=30,
            resolution="1920x1080",
            auto_analyze_after_stop=False,
            status="completed",
            started_at=now,
            stopped_at=now,
        )
    )
    linked_delete = client.delete(f"/api/field-sessions/{linked['id']}")
    assert linked_delete.status_code == 409
    assert client.get(f"/api/field-sessions/{linked['id']}").status_code == 200


def test_recording_start_links_field_session_and_inherits_context(client, monkeypatch):
    created = _create_field_session(client, court_name="继承球场", match_format="singles")
    _register_camera(client)
    starts: list[dict] = []

    monkeypatch.setattr("app.api.routes_recording.check_ffmpeg_available", lambda: True)
    monkeypatch.setattr(recording_service_module, "check_ffmpeg_available", lambda: True)
    monkeypatch.setattr(recording_service_module.session_service._recorder, "start", lambda **kwargs: starts.append(kwargs))

    response = client.post(
        "/api/recordings/start",
        json={"camera_id": "cam-a", "field_session_id": created["id"], "court_name": "", "auto_analyze_after_stop": False},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["field_session_id"] == created["id"]
    assert body["court_name"] == "继承球场"
    assert body["match_format"] == "singles"
    assert len(starts) == 1


def test_recording_start_with_missing_field_session_returns_404_without_starting(client, monkeypatch):
    _register_camera(client)
    starts: list[dict] = []

    monkeypatch.setattr("app.api.routes_recording.check_ffmpeg_available", lambda: True)
    monkeypatch.setattr(recording_service_module, "check_ffmpeg_available", lambda: True)
    monkeypatch.setattr(recording_service_module.session_service._recorder, "start", lambda **kwargs: starts.append(kwargs))

    response = client.post(
        "/api/recordings/start",
        json={"camera_id": "cam-a", "field_session_id": "missing-field-session", "auto_analyze_after_stop": False},
    )

    assert response.status_code == 404
    assert starts == []


def test_recording_start_without_field_session_still_works(client, monkeypatch):
    _register_camera(client)

    monkeypatch.setattr("app.api.routes_recording.check_ffmpeg_available", lambda: True)
    monkeypatch.setattr(recording_service_module, "check_ffmpeg_available", lambda: True)
    monkeypatch.setattr(recording_service_module.session_service._recorder, "start", lambda **kwargs: None)

    response = client.post(
        "/api/recordings/start",
        json={
            "camera_id": "cam-a",
            "court_name": "直接录制球场",
            "match_format": "doubles",
            "auto_analyze_after_stop": False,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["field_session_id"] is None
    assert body["court_name"] == "直接录制球场"
    assert body["match_format"] == "doubles"


def test_recording_list_filters_by_field_session(client):
    field_session = _create_field_session(client)
    now = datetime.now(timezone.utc)
    linked = RecordingSession(
        session_id="rec_linked",
        camera_id="cam-a",
        field_session_id=field_session["id"],
        court_name="A 场",
        match_format="doubles",
        camera_angle="baseline_high",
        fps=30,
        resolution="1920x1080",
        auto_analyze_after_stop=False,
        status="completed",
        started_at=now,
        stopped_at=now,
    )
    direct = linked.model_copy(update={"session_id": "rec_direct", "field_session_id": None})
    session_service._persist(linked)
    session_service._persist(direct)

    response = client.get("/api/recordings", params={"field_session_id": field_session["id"]})

    assert response.status_code == 200
    body = response.json()
    assert [item["session_id"] for item in body] == ["rec_linked"]
