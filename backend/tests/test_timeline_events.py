"""Session Timeline Event 后端测试."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.camera.camera_registry import CAMERAS
from app.camera.session_service import SESSIONS, session_service, _ACTIVE_CAMERA, _ACTIVE_SESSION_ID
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


# ---- 辅助函数 ----

def _create_field_session(client: TestClient, **overrides) -> dict:
    payload = {
        "title": "测试场次",
        "venue": "测试场馆",
        "court_name": "A 场",
        "capture_mode": "practice",
        "match_format": "doubles",
        "camera_setup": "single",
        "notes": "",
    }
    payload.update(overrides)
    response = client.post("/api/field-sessions", json=payload)
    assert response.status_code == 201
    return response.json()


def _create_recording(client: TestClient, field_session_id: str | None = None) -> dict:
    """在内存中创建一条已完成的 RecordingSession 用于测试。"""
    from app.camera.models import RecordingSession

    now = datetime.now(timezone.utc)
    rec_id = f"rec_{now.strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:6]}_test"
    session = RecordingSession(
        session_id=rec_id,
        camera_id="cam-a",
        field_session_id=field_session_id,
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
    session_service._persist(session)
    return session.model_dump(mode="json")


def _create_timeline_event(
    client: TestClient,
    field_session_id: str,
    **overrides,
) -> dict:
    payload = {
        "event_type": "session_note",
        "source": "manual",
        "label": "测试事件",
        "note": "测试备注",
        "payload_json": {},
        **overrides,
    }
    response = client.post(
        f"/api/field-sessions/{field_session_id}/timeline-events",
        json=payload,
    )
    return response


# ---- 5.1 基本 CRUD 测试 ----

def test_create_timeline_event_succeeds(client):
    fs = _create_field_session(client)
    response = _create_timeline_event(client, fs["id"], payload_json={"text": "hello"})
    assert response.status_code == 201
    body = response.json()
    assert body["id"].startswith("te_")
    assert body["field_session_id"] == fs["id"]
    assert body["event_type"] == "session_note"
    assert body["source"] == "manual"
    assert body["label"] == "测试事件"
    assert body["note"] == "测试备注"
    assert body["payload_json"] == {"text": "hello"}
    assert body["timestamp_ms"] >= 0
    assert body["occurred_at"] is not None
    assert body["created_at"] is not None
    assert body["updated_at"] is not None


def test_list_timeline_events(client):
    fs = _create_field_session(client)
    e1 = _create_timeline_event(client, fs["id"], label="事件1", timestamp_ms=1000)
    e2 = _create_timeline_event(client, fs["id"], label="事件2", timestamp_ms=500)
    assert e1.status_code == 201
    assert e2.status_code == 201

    response = client.get(f"/api/field-sessions/{fs['id']}/timeline-events")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 2
    # 按 timestamp_ms ASC 排序
    assert items[0]["timestamp_ms"] == 500
    assert items[1]["timestamp_ms"] == 1000


def test_filter_by_event_type_and_source(client):
    fs = _create_field_session(client)
    _create_timeline_event(client, fs["id"], event_type="session_note", source="manual", label="备注")
    _create_timeline_event(client, fs["id"], event_type="game_start", source="manual", label="局开始")
    _create_timeline_event(client, fs["id"], event_type="session_note", source="algorithm", label="算法事件")

    by_type = client.get(
        f"/api/field-sessions/{fs['id']}/timeline-events",
        params={"event_type": "game_start"},
    )
    assert by_type.status_code == 200
    assert len(by_type.json()) == 1

    by_source = client.get(
        f"/api/field-sessions/{fs['id']}/timeline-events",
        params={"source": "algorithm"},
    )
    assert by_source.status_code == 200
    assert len(by_source.json()) == 1


def test_filter_by_time_range(client):
    fs = _create_field_session(client)
    _create_timeline_event(client, fs["id"], label="t0", timestamp_ms=0)
    _create_timeline_event(client, fs["id"], label="t5000", timestamp_ms=5000)
    _create_timeline_event(client, fs["id"], label="t10000", timestamp_ms=10000)

    filtered = client.get(
        f"/api/field-sessions/{fs['id']}/timeline-events",
        params={"from_ms": 1000, "to_ms": 8000},
    )
    assert filtered.status_code == 200
    items = filtered.json()
    assert len(items) == 1
    assert items[0]["label"] == "t5000"


def test_filter_by_recording_session_id(client):
    fs = _create_field_session(client)
    rec_a = _create_recording(client, field_session_id=fs["id"])
    rec_b = _create_recording(client, field_session_id=fs["id"])
    _create_timeline_event(client, fs["id"], label="录制 A", recording_session_id=rec_a["session_id"])
    _create_timeline_event(client, fs["id"], label="录制 B", recording_session_id=rec_b["session_id"])

    filtered = client.get(
        f"/api/field-sessions/{fs['id']}/timeline-events",
        params={"recording_session_id": rec_b["session_id"]},
    )

    assert filtered.status_code == 200
    items = filtered.json()
    assert [item["label"] for item in items] == ["录制 B"]


def test_get_timeline_event_detail(client):
    fs = _create_field_session(client)
    created = _create_timeline_event(client, fs["id"], label="详情测试")

    response = client.get(f"/api/timeline-events/{created.json()['id']}")
    assert response.status_code == 200
    assert response.json()["label"] == "详情测试"


def test_update_timeline_event(client):
    fs = _create_field_session(client)
    created = _create_timeline_event(client, fs["id"])
    event_id = created.json()["id"]

    updated = client.patch(
        f"/api/timeline-events/{event_id}",
        json={"label": "更新后标签", "note": "更新后备注", "timestamp_ms": 5000},
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["label"] == "更新后标签"
    assert body["note"] == "更新后备注"
    assert body["timestamp_ms"] == 5000
    # field_session_id 不变
    assert body["field_session_id"] == fs["id"]


def test_delete_timeline_event(client):
    fs = _create_field_session(client)
    created = _create_timeline_event(client, fs["id"])
    event_id = created.json()["id"]

    deleted = client.delete(f"/api/timeline-events/{event_id}")
    assert deleted.status_code == 204

    # 验证已删除
    get_again = client.get(f"/api/timeline-events/{event_id}")
    assert get_again.status_code == 404

    # 列表不再包含
    listed = client.get(f"/api/field-sessions/{fs['id']}/timeline-events")
    assert len(listed.json()) == 0


# ---- 5.2 错误场景测试 ----

def test_create_event_for_missing_field_session(client):
    response = _create_timeline_event(client, "nonexistent_fs")
    assert response.status_code == 404


def test_create_event_with_invalid_recording_session(client):
    fs = _create_field_session(client)
    response = _create_timeline_event(
        client, fs["id"], recording_session_id="nonexistent_recording"
    )
    assert response.status_code == 400


def test_create_event_with_recording_not_belonging_to_fs(client):
    fs_a = _create_field_session(client, title="A")
    fs_b = _create_field_session(client, title="B")
    rec = _create_recording(client, field_session_id=fs_a["id"])

    # 尝试为 fs_b 创建一个引用 rec 的事件，但 rec 属于 fs_a
    response = client.post(
        f"/api/field-sessions/{fs_b['id']}/timeline-events",
        json={
            "event_type": "session_note",
            "source": "manual",
            "label": "非法关联",
            "recording_session_id": rec["session_id"],
        },
    )
    assert response.status_code == 400


def test_create_event_negative_timestamp_rejected(client):
    fs = _create_field_session(client)
    response = _create_timeline_event(client, fs["id"], timestamp_ms=-1)
    assert response.status_code == 422


def test_create_event_invalid_event_type_rejected(client):
    fs = _create_field_session(client)
    response = _create_timeline_event(client, fs["id"], event_type="invalid_type")
    assert response.status_code == 422


def test_create_event_invalid_source_rejected(client):
    fs = _create_field_session(client)
    response = _create_timeline_event(client, fs["id"], source="unknown_source")
    assert response.status_code == 422


def test_create_event_invalid_payload_json_rejected(client):
    fs = _create_field_session(client)
    response = _create_timeline_event(client, fs["id"], payload_json="not-valid-json")
    assert response.status_code == 422


def test_update_nonexistent_event(client):
    response = client.patch("/api/timeline-events/nonexistent", json={"label": "nope"})
    assert response.status_code == 404


def test_delete_nonexistent_event(client):
    response = client.delete("/api/timeline-events/nonexistent")
    assert response.status_code == 404


def test_list_events_for_missing_field_session(client):
    response = client.get("/api/field-sessions/nonexistent/timeline-events")
    assert response.status_code == 404


# ---- 5.3 时间戳策略测试 ----

def test_timestamp_fallback_with_recording(client):
    fs = _create_field_session(client)
    rec = _create_recording(client, field_session_id=fs["id"])

    # 不提交 timestamp_ms，但有关联录制 → 后端兜底计算
    response = client.post(
        f"/api/field-sessions/{fs['id']}/timeline-events",
        json={
            "event_type": "session_note",
            "source": "manual",
            "label": "录制兜底",
            "recording_session_id": rec["session_id"],
        },
    )
    assert response.status_code == 201
    # 兜底时间戳应 ≥ 0（录制 started_at 和当前时间之间的差值）
    assert response.json()["timestamp_ms"] >= 0


def test_timestamp_default_zero_without_recording(client):
    fs = _create_field_session(client)

    # 不提交 timestamp_ms，也无关联录制 → 默认 0
    response = _create_timeline_event(client, fs["id"])
    assert response.status_code == 201
    assert response.json()["timestamp_ms"] == 0


def test_timestamp_explicit_value_preserved(client):
    fs = _create_field_session(client)

    response = _create_timeline_event(client, fs["id"], timestamp_ms=12345)
    assert response.status_code == 201
    assert response.json()["timestamp_ms"] == 12345


# ---- 5.4 Field Session 删除保护测试 ----

def test_delete_field_session_with_events_no_video_succeeds(client):
    """无视频的采集任务即使有时间线事件也应能删除（级联清理）。"""
    fs = _create_field_session(client)
    _create_timeline_event(client, fs["id"])

    # 先完成防止 live 状态拦截
    assert client.post(f"/api/field-sessions/{fs['id']}/complete").status_code == 200

    response = client.delete(f"/api/field-sessions/{fs['id']}")
    assert response.status_code == 200
    assert response.json()["status"] == "deleted"

    # Field Session 已被删除
    get_resp = client.get(f"/api/field-sessions/{fs['id']}")
    assert get_resp.status_code == 404


def test_delete_field_session_without_events_succeeds(client):
    fs = _create_field_session(client)

    response = client.delete(f"/api/field-sessions/{fs['id']}")
    assert response.status_code == 200
    assert response.json()["status"] == "deleted"
