from __future__ import annotations

import asyncio
from io import BytesIO
from threading import Event

import httpx
import pytest
from fastapi import UploadFile

from app.core.config import Settings
from app.services import video_service as video_service_module
from app.services.storage_service import StorageService
from app.services.video_service import VIDEOS, EmptyUploadError, UploadSizeExceededError, VideoService


def _upload(name: str, data: bytes) -> UploadFile:
    return UploadFile(filename=name, file=BytesIO(data), headers={"content-type": "video/mp4"})


def test_upload_limit_stops_unknown_length_stream_and_cleans_partial_file(tmp_path, monkeypatch):
    settings = Settings(
        data_dir=tmp_path,
        uploads_dir=tmp_path / "uploads",
        tmp_dir=tmp_path / "tmp",
        max_upload_bytes=4,
    )
    storage = StorageService(settings)
    service = VideoService(storage)
    monkeypatch.setattr(video_service_module, "generate_poster", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(video_service_module, "get_settings", lambda: settings)
    try:
        asyncio.run(service.save_upload(_upload("clip.mp4", b"12345")))
    except UploadSizeExceededError:
        pass
    else:
        raise AssertionError("expected upload limit")
    assert list(storage.uploads_dir.glob("*")) == []


def test_empty_upload_and_metadata_failure_do_not_register_media(tmp_path, monkeypatch):
    settings = Settings(
        data_dir=tmp_path,
        uploads_dir=tmp_path / "uploads",
        tmp_dir=tmp_path / "tmp",
        max_upload_bytes=100,
    )
    storage = StorageService(settings)
    service = VideoService(storage)
    monkeypatch.setattr(video_service_module, "generate_poster", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(video_service_module, "get_settings", lambda: settings)
    VIDEOS.clear()
    try:
        asyncio.run(service.save_upload(_upload("empty.mp4", b"")))
    except EmptyUploadError:
        pass
    else:
        raise AssertionError("expected empty upload")
    assert list(storage.uploads_dir.glob("*")) == []

    def fail_write(*_args, **_kwargs):
        raise OSError("metadata disk failure")

    monkeypatch.setattr(storage, "write_json", fail_write)
    try:
        asyncio.run(service.save_upload(_upload("clip.mp4", b"123")))
    except OSError:
        pass
    else:
        raise AssertionError("expected metadata failure")
    assert list(storage.uploads_dir.glob("*")) == []
    assert not VIDEOS


@pytest.mark.parametrize("declared", [None, "1"])
def test_multipart_receive_limit_counts_unknown_and_forged_lengths(tmp_path, monkeypatch, declared):
    from fastapi import FastAPI
    from app.api.routes_video import router
    from app.core import upload_limit
    from app.core.upload_limit import UploadBodyLimitMiddleware

    settings = Settings(max_upload_bytes=4)
    monkeypatch.setattr(upload_limit, "get_settings", lambda: settings)
    app = FastAPI()
    app.include_router(router)
    app.add_middleware(UploadBodyLimitMiddleware)
    consumed = []

    async def body():
        yield b'--probe\r\nContent-Disposition: form-data; name="file"; filename="a.mp4"\r\n\r\n'
        for i in range(10):
            consumed.append(i)
            yield b"a" * (512 * 1024)
        yield b"\r\n--probe--\r\n"

    async def run():
        headers = {"content-type": "multipart/form-data; boundary=probe"}
        if declared:
            headers["content-length"] = declared
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/videos/upload", content=body(), headers=headers)
            assert response.status_code == 413

    asyncio.run(run())
    assert len(consumed) == 2


def test_poster_wait_does_not_block_other_requests(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from app.api import routes_video

    settings = Settings(uploads_dir=tmp_path / "uploads", max_upload_bytes=100)
    service = VideoService(StorageService(settings))
    entered, release = Event(), Event()

    def poster(*args):
        entered.set()
        assert release.wait(timeout=5)
        return False

    monkeypatch.setattr(video_service_module, "get_settings", lambda: settings)
    monkeypatch.setattr(video_service_module, "generate_poster", poster)
    monkeypatch.setattr(routes_video, "video_service", service)
    app = FastAPI()
    app.include_router(routes_video.router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            upload = asyncio.create_task(client.post("/api/videos/upload", files={"file": ("a.mp4", b"123")}))
            try:
                assert await asyncio.to_thread(entered.wait, 3)
                assert (await client.get("/health")).status_code == 200
                assert not upload.done()
            finally:
                release.set()
            response = await upload
            assert response.status_code == 200
            video_id = response.json()["video"]["id"]
            assert (await client.get(f"/api/videos/{video_id}/poster")).status_code == 404
            assert (await client.get(f"/api/videos/{video_id}/stream")).content == b"123"

    asyncio.run(run())
