from datetime import UTC, datetime
import json
from types import SimpleNamespace
from unittest.mock import patch

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


def _ffprobe_payload():
    return SimpleNamespace(
        returncode=0,
        stdout=json.dumps(
            {
                "frames": [
                    {"best_effort_timestamp_time": "1.400000", "pkt_dts_time": "1.400000", "key_frame": 1},
                    {"best_effort_timestamp_time": "1.416667", "pkt_dts_time": "1.416667", "key_frame": 0},
                ]
            }
        ),
        stderr="",
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


def test_materialize_endpoint_generates_sidecar(tmp_path, monkeypatch):
    media = tmp_path / "camera.mp4"
    media.write_bytes(b"registered-media")
    monkeypatch.setattr(routes_video.video_service, "get_available_video", lambda _: _video(media))

    with patch("app.services.dual_camera_sync.subprocess.run", return_value=_ffprobe_payload()) as run:
        result = routes_video.materialize_video_timing("rec-test-video")

    assert result.authority == "source_pts"
    assert result.status == "ready"
    assert result.reused is False
    assert result.frame_count == 2
    assert result.fps == pytest.approx(59.9988, rel=1e-4)
    assert run.call_count == 1
    sidecar = tmp_path / "camera.mp4.pts.jsonl"
    assert sidecar.is_file()
    # 补写后 GET /timing 应返回 source_pts authority
    timing = routes_video.read_video_timing("rec-test-video")
    assert timing.authority == "source_pts"
    assert timing.frame_count == 2


def test_materialize_endpoint_reuses_existing_sidecar(tmp_path, monkeypatch):
    media = tmp_path / "camera.mp4"
    media.write_bytes(b"registered-media")
    sidecar = tmp_path / "camera.mp4.pts.jsonl"
    sidecar.write_text(
        '{"frame_index":0,"pts_seconds":0.033333,"dts_seconds":0.033333,"keyframe":true}\n'
        '{"frame_index":1,"pts_seconds":0.050000,"dts_seconds":0.050000,"keyframe":false}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(routes_video.video_service, "get_available_video", lambda _: _video(media))

    with patch("app.services.dual_camera_sync.subprocess.run", return_value=_ffprobe_payload()) as run:
        result = routes_video.materialize_video_timing("rec-test-video")

    assert result.authority == "source_pts"
    assert result.status == "ready"
    assert result.reused is True
    assert result.frame_count == 2
    run.assert_not_called()


def test_materialize_endpoint_rejects_unknown_video(tmp_path, monkeypatch):
    media = tmp_path / "camera.mp4"
    media.write_bytes(b"registered-media")
    monkeypatch.setattr(routes_video.video_service, "get_available_video", lambda _: None)

    with pytest.raises(HTTPException) as error:
        routes_video.materialize_video_timing("rec-test-video")

    assert error.value.status_code == 404


def test_materialize_endpoint_rejects_invalid_pts(tmp_path, monkeypatch):
    media = tmp_path / "camera.mp4"
    media.write_bytes(b"registered-media")
    monkeypatch.setattr(routes_video.video_service, "get_available_video", lambda _: _video(media))
    empty = SimpleNamespace(returncode=0, stdout=json.dumps({"frames": []}), stderr="")

    with patch("app.services.dual_camera_sync.subprocess.run", return_value=empty):
        with pytest.raises(HTTPException) as error:
            routes_video.materialize_video_timing("rec-test-video")

    assert error.value.status_code == 409
    assert error.value.detail["code"] == "source_pts_invalid"
    # 媒体本身保持原样，未被修改或删除
    assert media.read_bytes() == b"registered-media"
