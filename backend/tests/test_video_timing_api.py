from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from app.api import routes_video
from app.schemas.video import VideoMetadata


def _video(path) -> VideoMetadata:
    return VideoMetadata(
        id="rec-test-video",
        original_filename="camera.mp4",
        content_type="video/mp4",
        size_bytes=path.stat().st_size,
        path=str(path),
        uploaded_at=datetime.now(UTC),
        source="recording",
    )


def test_timing_endpoint_returns_validated_source_pts(tmp_path, monkeypatch):
    media = tmp_path / "camera.mp4"
    media.write_bytes(b"registered-media")
    sidecar = tmp_path / "camera.mp4.pts.jsonl"
    sidecar.write_text(
        '{"frame_index":0,"pts_seconds":0.033333,"dts_seconds":0.033333,"keyframe":true}\n'
        '{"frame_index":1,"pts_seconds":0.050000,"dts_seconds":0.050000,"keyframe":false}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(routes_video.video_service, "get_available_video", lambda _: _video(media))

    result = routes_video.read_video_timing("rec-test-video")

    assert result.authority == "source_pts"
    assert result.frame_count == 2
    assert result.frames[1].frame_index == 1
    assert result.frames[1].pts_seconds == pytest.approx(0.05)


def test_timing_endpoint_rejects_missing_sidecar(tmp_path, monkeypatch):
    media = tmp_path / "camera.mp4"
    media.write_bytes(b"registered-media")
    monkeypatch.setattr(routes_video.video_service, "get_available_video", lambda _: _video(media))

    with pytest.raises(HTTPException) as error:
        routes_video.read_video_timing("rec-test-video")

    assert error.value.status_code == 409
    assert error.value.detail["code"] == "source_pts_missing"
