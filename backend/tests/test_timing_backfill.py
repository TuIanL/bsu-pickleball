import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.schemas.video import VideoMetadata
from app.services.timing_backfill import collect_registered_media, start_timing_backfill


def _metadata(video_id: str, path: Path, source: str = "recording") -> VideoMetadata:
    return VideoMetadata(
        id=video_id,
        original_filename=f"{video_id}.mp4",
        content_type="video/mp4",
        size_bytes=path.stat().st_size if path.is_file() else 0,
        path=str(path),
        uploaded_at=datetime.now(UTC),
        source=source,
    )


class _FakeVideoService:
    def __init__(self, videos: list[VideoMetadata]) -> None:
        self.videos = {video.id: video for video in videos}

    def list_videos(self):
        return list(self.videos.values())

    def get_available_video(self, video_id):
        video = self.videos.get(video_id)
        if video is None:
            return None
        path = Path(video.path)
        if not path.is_file() or path.stat().st_size <= 0:
            return None
        return video


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


def test_collect_registered_media_excludes_unavailable(tmp_path):
    good = tmp_path / "good.mp4"
    good.write_bytes(b"registered-media")
    missing = tmp_path / "missing.mp4"  # metadata exists but file does not
    service = _FakeVideoService([_metadata("rec-good", good), _metadata("rec-missing", missing)])

    collected = collect_registered_media(video_service=service)

    ids = {video_id for video_id, _ in collected}
    assert ids == {"rec-good"}
    assert collected[0][1] == good.resolve()


def test_start_timing_backfill_backfills_missing_sidecars(tmp_path):
    first = tmp_path / "first.mp4"
    first.write_bytes(b"registered-media")
    second = tmp_path / "second.mp4"
    second.write_bytes(b"registered-media")
    service = _FakeVideoService([_metadata("rec-first", first), _metadata("rec-second", second)])

    with patch("app.services.dual_camera_sync.subprocess.run", return_value=_ffprobe_payload()):
        thread = start_timing_backfill(video_service=service)
        thread.join(timeout=15)

    assert not thread.is_alive()
    assert (first.parent / "first.mp4.pts.jsonl").is_file()
    assert (second.parent / "second.mp4.pts.jsonl").is_file()


def test_start_timing_backfill_reuses_existing_sidecar(tmp_path):
    media = tmp_path / "camera.mp4"
    media.write_bytes(b"registered-media")
    sidecar = tmp_path / "camera.mp4.pts.jsonl"
    sidecar.write_text(
        '{"frame_index":0,"pts_seconds":0.033333,"dts_seconds":0.033333,"keyframe":true}\n',
        encoding="utf-8",
    )
    service = _FakeVideoService([_metadata("rec-camera", media)])

    with patch("app.services.dual_camera_sync.subprocess.run", return_value=_ffprobe_payload()) as run:
        thread = start_timing_backfill(video_service=service)
        thread.join(timeout=15)

    assert not thread.is_alive()
    run.assert_not_called()
    assert sidecar.read_text(encoding="utf-8") == (
        '{"frame_index":0,"pts_seconds":0.033333,"dts_seconds":0.033333,"keyframe":true}\n'
    )


def test_start_timing_backfill_tolerates_broken_sync_service(tmp_path):
    """A failing sync-recording service must not block or crash startup backfill."""
    media = tmp_path / "camera.mp4"
    media.write_bytes(b"registered-media")
    service = _FakeVideoService([_metadata("rec-camera", media)])

    class _BrokenSync:
        def list_sessions(self):
            raise RuntimeError("sessions dir unreadable")

    with patch("app.services.dual_camera_sync.subprocess.run", return_value=_ffprobe_payload()):
        thread = start_timing_backfill(video_service=service, sync_recording_service=_BrokenSync())
        thread.join(timeout=15)

    assert not thread.is_alive()
    # 即使 sync 服务异常，video_service 里的缺失 sidecar 仍被补写
    assert (tmp_path / "camera.mp4.pts.jsonl").is_file()


def test_start_timing_backfill_skips_unavailable_media_without_blocking(tmp_path):
    """Missing media must be skipped and startup must not block."""
    missing = tmp_path / "missing.mp4"  # file does not exist
    service = _FakeVideoService([_metadata("rec-missing", missing)])

    thread = start_timing_backfill(video_service=service)
    thread.join(timeout=15)

    assert not thread.is_alive()
    assert not (tmp_path / "missing.mp4.pts.jsonl").exists()
