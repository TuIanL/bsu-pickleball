from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
    now = datetime.now(timezone.utc)
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
    now = datetime.now(timezone.utc)
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
