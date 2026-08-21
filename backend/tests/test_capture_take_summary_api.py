"""API 测试 —— CaptureTakeSummary.video_ids 与 list_segments 编辑契约字段。"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app
from app.models.capture_take import CaptureMode as TakeCaptureMode
from app.models.capture_take import CaptureTake, CaptureTakeStatus, SourceSessionType
from app.models.field_session import CameraSetup, FieldSession, FieldSessionStatus, MatchFormat
from app.models.field_session import CaptureMode as FieldCaptureMode
from app.services.capture_segment_service import create_segment
from app.services.capture_track_service import create_track

client = TestClient(app)


def _create_single_take(isolated_database, *, take_id: str = "take-summary-single") -> str:
    db = isolated_database()
    now = datetime.now(UTC)
    field_session = FieldSession(
        id=f"field-{take_id}",
        title="摘要测试",
        venue="测试场",
        court_name="测试场 1",
        capture_mode=FieldCaptureMode.match,
        match_format=MatchFormat.singles,
        camera_setup=CameraSetup.single,
        status=FieldSessionStatus.planned,
    )
    take = CaptureTake(
        id=take_id,
        field_session_id=field_session.id,
        capture_mode=TakeCaptureMode.single,
        source_session_type=SourceSessionType.recording,
        source_session_id=f"rec-{take_id}",
        status=CaptureTakeStatus.completed,
        started_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add_all([field_session, take])
    db.flush()
    # 机位 1 注册视频；机位 2 无视频（模拟单摄）
    create_track(
        db,
        capture_take_id=take_id,
        camera_id="camera-a",
        role="primary",
        slot="cam_1",
        analysis_role="default",
        video_id="video-single-a",
        offset_ms=0,
        offset_source="measured",
        sync_quality="good",
    )
    db.commit()
    db.close()
    return take_id


def _create_dual_take(isolated_database, *, take_id: str = "take-summary-dual") -> str:
    db = isolated_database()
    now = datetime.now(UTC)
    field_session = FieldSession(
        id=f"field-{take_id}",
        title="摘要测试双摄",
        venue="测试场",
        court_name="测试场 1",
        capture_mode=FieldCaptureMode.match,
        match_format=MatchFormat.doubles,
        camera_setup=CameraSetup.dual,
        status=FieldSessionStatus.planned,
    )
    take = CaptureTake(
        id=take_id,
        field_session_id=field_session.id,
        capture_mode=TakeCaptureMode.dual,
        source_session_type=SourceSessionType.sync_recording,
        source_session_id=f"sync-{take_id}",
        status=CaptureTakeStatus.completed,
        started_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add_all([field_session, take])
    db.flush()
    # 机位顺序：cam_1、cam_2；故意让 cam_2 先插入以验证按 slot 排序
    create_track(
        db,
        capture_take_id=take_id,
        camera_id="camera-b",
        role="secondary",
        slot="cam_2",
        analysis_role="supplementary",
        video_id="video-sync-b",
        offset_ms=100,
        offset_source="measured",
        sync_quality="good",
    )
    create_track(
        db,
        capture_take_id=take_id,
        camera_id="camera-a",
        role="primary",
        slot="cam_1",
        analysis_role="default",
        video_id="video-sync-a",
        offset_ms=0,
        offset_source="measured",
        sync_quality="good",
    )
    # 一个带人工修正的 game 片段：start=1000/end=5000，修正为 1200/4800
    seg = create_segment(
        db,
        capture_take_id=take_id,
        segment_type="game",
        ordinal=1,
        start_ms=1000,
        label="第1局",
        source="algorithm",
    )
    seg.end_ms = 5000
    seg.end_event_id = "ev_end"
    seg.corrected_start_ms = 1200
    seg.corrected_end_ms = 4800
    seg.edit_version = 1
    db.commit()
    db.close()
    return take_id


def test_capture_take_summary_video_ids_ordered_by_slot(isolated_database):
    take_id = _create_dual_take(isolated_database)

    response = client.get(f"/api/capture-takes/{take_id}")
    assert response.status_code == 200
    body = response.json()
    # 按 slot cam_1→cam_2 排序，即使插入顺序相反
    assert body["video_ids"] == ["video-sync-a", "video-sync-b"]


def test_capture_take_summary_video_ids_single(isolated_database):
    take_id = _create_single_take(isolated_database)

    response = client.get(f"/api/capture-takes/{take_id}")
    assert response.status_code == 200
    assert response.json()["video_ids"] == ["video-single-a"]


def test_capture_take_summary_video_ids_falls_back_to_source_session(isolated_database):
    """track 无 video_id（legacy/测试 take）时回退到来源录制会话的 video_id。"""
    from datetime import datetime, timezone

    from app.camera.models import RecordingSession
    from app.camera.session_service import SESSIONS

    take_id = _create_single_take(isolated_database)
    # 移除 track 的 video_id，模拟 legacy take（create_track 默认 video_id=None，这里显式清空）
    db = isolated_database()
    from app.models.capture_track import CaptureTrack

    for track in db.query(CaptureTrack).filter(CaptureTrack.capture_take_id == take_id).all():
        track.video_id = None
    db.commit()
    db.close()

    SESSIONS["rec-take-summary-single"] = RecordingSession(
        session_id="rec-take-summary-single",
        camera_id="camera-a",
        field_session_id=f"field-{take_id}",
        court_name="测试场 1",
        match_format="doubles",
        camera_angle="wide",
        fps=30,
        resolution="1920x1080",
        auto_analyze_after_stop=True,
        status="completed",
        started_at=datetime.now(timezone.utc),
        video_id="video-fallback",
    )
    try:
        response = client.get(f"/api/capture-takes/{take_id}")
        assert response.status_code == 200
        assert response.json()["video_ids"] == ["video-fallback"]
    finally:
        SESSIONS.pop("rec-take-summary-single", None)


def test_list_segments_exposes_edit_contract_fields(isolated_database):
    take_id = _create_dual_take(isolated_database)

    response = client.get(f"/api/capture-takes/{take_id}/segments")
    assert response.status_code == 200
    segs = response.json()
    assert segs, "期望至少一个片段"
    seg = segs[0]

    # 编辑契约字段
    assert "edit_status" in seg
    assert seg["edit_status"] in {"active", "superseded", "archived"}
    assert "edit_version" in seg
    assert seg["edit_version"] >= 1

    # corrected / effective 字段，effective 遵循 corrected 优先
    assert seg["corrected_start_ms"] == 1200
    assert seg["corrected_end_ms"] == 4800
    assert seg["effective_start_ms"] == 1200
    assert seg["effective_end_ms"] == 4800
    # 原始值仍保留
    assert seg["start_ms"] == 1000
    assert seg["end_ms"] == 5000


def test_list_segments_effective_falls_back_to_raw_when_no_correction(isolated_database):
    take_id = _create_single_take(isolated_database)
    db = isolated_database()
    seg = create_segment(
        db,
        capture_take_id=take_id,
        segment_type="rally",
        ordinal=1,
        start_ms=2000,
        label="第1分",
        source="algorithm",
    )
    seg.end_ms = 4000
    seg.end_event_id = "ev_end"
    db.commit()
    db.close()

    response = client.get(f"/api/capture-takes/{take_id}/segments")
    assert response.status_code == 200
    seg = next(s for s in response.json() if s["segment_type"] == "rally")
    assert seg["corrected_start_ms"] is None
    assert seg["corrected_end_ms"] is None
    assert seg["effective_start_ms"] == 2000
    assert seg["effective_end_ms"] == 4000
