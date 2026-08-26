from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.core.config import get_settings
from app.models.capture_take import CaptureMode, CaptureTake, CaptureTakeStatus, SourceSessionType
from app.services.capture_take_service import get_active_capture_take, has_active_capture_take


def _take(take_id: str, *, status: CaptureTakeStatus, started_at: datetime) -> CaptureTake:
    return CaptureTake(
        id=take_id,
        field_session_id=f"field-{take_id}",
        capture_mode=CaptureMode.single,
        source_session_type=SourceSessionType.recording,
        source_session_id=f"source-{take_id}",
        status=status,
        started_at=started_at,
        created_at=started_at,
        updated_at=started_at,
    )


def test_backend_tests_use_temp_runtime_paths():
    settings = get_settings()
    workspace_data = Path(__file__).resolve().parents[1] / "data"

    assert settings.resolve_path(settings.database_path) != (workspace_data / "app.sqlite3").resolve()
    assert settings.resolved_uploads_dir != (workspace_data / "uploads").resolve()
    assert settings.model_dir != Path("../models")


def test_active_capture_timeout_boundary_is_explicit(isolated_database):
    factory = isolated_database
    now = datetime.now(UTC)
    db = factory()
    fresh = _take("fresh", status=CaptureTakeStatus.recording, started_at=now)
    stale = _take("stale", status=CaptureTakeStatus.recording, started_at=now - timedelta(minutes=10))
    db.add_all([fresh, stale])
    db.commit()

    assert has_active_capture_take(db) is True
    assert get_active_capture_take(db).id == "fresh"
    db.close()


def test_orphan_capture_take_recovery_marks_only_active_orphans_failed(isolated_database, monkeypatch):
    from app.camera import capture_recovery

    factory = isolated_database
    now = datetime.now(UTC)
    db = factory()
    orphan = _take("orphan", status=CaptureTakeStatus.recording, started_at=now)
    completed = _take("completed", status=CaptureTakeStatus.completed, started_at=now)
    db.add_all([orphan, completed])
    db.commit()
    db.close()

    monkeypatch.setattr(capture_recovery, "get_session_factory", lambda: factory)
    capture_recovery.recover_orphan_recordings()

    check = factory()
    try:
        assert check.get(CaptureTake, "orphan").status is CaptureTakeStatus.failed
        assert check.get(CaptureTake, "completed").status is CaptureTakeStatus.completed
    finally:
        check.close()


def test_api_upload_does_not_pollute_production_uploads():
    """通过 API 上传的视频 MUST 落在隔离临时目录，绝不写入生产 uploads 目录。

    这是 cleanup-test-upload-pollution 变更的核心回归断言：``conftest`` 的
    ``_isolate_uploads_singleton`` 会话级 fixture 把全局 ``video_service`` 单例的
    storage 指向临时目录，使 ``TestClient`` 上传产物不再污染 ``backend/data/uploads``。
    """
    from fastapi.testclient import TestClient

    from app.main import app
    from app.services.storage_service import StorageService
    from app.services.video_service import VIDEOS, video_service

    production_uploads = Path(__file__).resolve().parents[1] / "data" / "uploads"

    response = TestClient(app).post(
        "/api/videos/upload",
        files={"file": ("isolation-check.mp4", b"not-a-real-video", "video/mp4")},
    )
    assert response.status_code == 200
    video = response.json()["video"]

    media_path = Path(video["path"])
    assert media_path.exists(), "上传媒体文件应已落盘"
    # 关键断言：不能落在生产 uploads 目录树下。
    assert production_uploads.resolve() not in [p.resolve() for p in media_path.parents]

    # 本测试自带清理（与 autouse teardown 正交，确保无论如何都回收）。
    StorageService.delete_path(media_path)
    StorageService.delete_path(video_service.storage.uploads_dir / f"{video['id']}.json")
    VIDEOS.pop(video["id"], None)
