from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes_video import router
from app.schemas.video import VideoMetadata
from app.services.video_service import VIDEOS


def _client(tmp_path):
    app = FastAPI()
    app.include_router(router)
    path = tmp_path / "clip.webm"
    path.write_bytes(b"0123456789")
    VIDEOS["range-probe"] = VideoMetadata(
        id="range-probe",
        original_filename=path.name,
        size_bytes=10,
        path=str(path),
        uploaded_at=datetime.now(UTC),
    )
    return TestClient(app), path


def test_video_stream_supports_mime_and_suffix_range(tmp_path):
    client, _ = _client(tmp_path)
    response = client.get("/api/videos/range-probe/stream", headers={"Range": "bytes=-3"})
    assert response.status_code == 206
    assert response.headers["content-type"].startswith("video/webm")
    assert response.headers["content-range"] == "bytes 7-9/10"
    assert response.content == b"789"


def test_video_stream_supports_open_range_and_head(tmp_path):
    client, _ = _client(tmp_path)
    response = client.get("/api/videos/range-probe/stream", headers={"Range": "bytes=4-"})
    assert response.status_code == 206
    assert response.content == b"456789"

    head = client.head("/api/videos/range-probe/stream")
    assert head.status_code == 200
    assert head.headers["content-length"] == "10"
    assert head.content == b""


def test_video_stream_rejects_unsatisfiable_range(tmp_path):
    client, _ = _client(tmp_path)
    response = client.get("/api/videos/range-probe/stream", headers={"Range": "bytes=10-"})
    assert response.status_code == 416
    assert response.headers["content-range"] == "bytes */10"


def test_video_stream_ignores_valid_multi_range_without_faking_multipart(tmp_path):
    client, _ = _client(tmp_path)
    response = client.get("/api/videos/range-probe/stream", headers={"Range": "bytes=0-1,4-5"})
    assert response.status_code == 200
    assert response.content == b"0123456789"


@pytest.mark.parametrize("range_header,status,body", [
    ("bytes=2-4", 206, b"234"), ("bytes=-20", 206, b"0123456789"),
    ("bytes=-0", 416, b""), ("items=0-1", 400, None), ("bytes=garbage", 400, None),
])
def test_range_edge_cases(tmp_path, range_header, status, body):
    client, _ = _client(tmp_path)
    response = client.get("/api/videos/range-probe/stream", headers={"Range": range_header})
    assert response.status_code == status
    if body is not None:
        assert response.content == body


def test_head_does_not_open_body(tmp_path, monkeypatch):
    import builtins
    client, path = _client(tmp_path)
    original = builtins.open

    def guarded(file, *args, **kwargs):
        assert str(file) != str(path), "HEAD opened the media body"
        return original(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded)
    response = client.head("/api/videos/range-probe/stream", headers={"Range": "bytes=2-4"})
    assert response.status_code == 206
    assert response.headers["content-length"] == "3"
    assert response.content == b""


@pytest.mark.parametrize(
    ("suffix", "content_type"),
    [
        (".mp4", "video/mp4"),
        (".mov", "video/quicktime"),
        (".m4v", "video/mp4"),
        (".avi", "video/x-msvideo"),
        (".mkv", "video/x-matroska"),
        (".webm", "video/webm"),
    ],
)
def test_video_stream_maps_every_supported_container_mime(tmp_path, suffix, content_type):
    app = FastAPI()
    app.include_router(router)
    path = tmp_path / f"clip{suffix}"
    path.write_bytes(b"media")
    video_id = f"mime-{suffix[1:]}"
    VIDEOS[video_id] = VideoMetadata(
        id=video_id,
        original_filename=path.name,
        size_bytes=5,
        path=str(path),
        uploaded_at=datetime.now(UTC),
    )
    response = TestClient(app).get(f"/api/videos/{video_id}/stream")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(content_type)
    assert response.content == b"media"
