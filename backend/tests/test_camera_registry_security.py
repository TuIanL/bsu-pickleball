from __future__ import annotations

import pytest

from app.camera.camera_registry import CAMERAS, CameraRegistry
from app.core import config
from app.services.storage_service import StorageService


def test_camera_registry_uses_configured_root_and_rejects_path_ids(tmp_path, monkeypatch):
    root = tmp_path / "configured-cameras"
    monkeypatch.setenv("PICKLEBALL_CAMERAS_DIR", str(root))
    config.get_settings.cache_clear()
    registry = CameraRegistry(StorageService())

    with pytest.raises(ValueError):
        registry.create("../escaped", "bad", "rtsp://example.invalid", "rtsp")
    with pytest.raises(ValueError):
        registry.create("/absolute", "bad", "rtsp://example.invalid", "rtsp")
    assert not (tmp_path / "escaped.json").exists()

    created = registry.create("中文 cam 1", "safe", "rtsp://example.invalid/live", "rtsp")
    assert created.camera_id == "中文 cam 1"
    assert (root / "中文 cam 1.json").is_file()

    with pytest.raises(FileExistsError):
        registry.create("中文 cam 1", "duplicate", "rtsp://example.invalid/live", "rtsp")

    CAMERAS.clear()
    config.get_settings.cache_clear()


def test_camera_api_response_redacts_url_userinfo():
    from datetime import UTC, datetime

    from app.api.routes_camera import _sanitize
    from app.camera.models import CameraInfo

    camera = CameraInfo(
        camera_id="cam-1",
        name="camera",
        stream_url="rtsp://user:secret@example.invalid/live",
        protocol="rtsp",
        username="user",
        password="secret",
        created_at=datetime.now(UTC),
    )
    safe = _sanitize(camera)
    assert "secret" not in safe.stream_url
    assert safe.stream_url == "rtsp://example.invalid/live"
    assert safe.password == "***"
