import json
import math
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services.dual_camera_sync import (
    FrameTiming,
    SyncCalibration,
    build_frame_map,
    calibrations_from_anchor_rows,
    fit_affine_calibration,
    read_frame_timing_sidecar,
    retime_filter_expression,
    summarize_frame_timing_sidecar,
    validate_anchor_payload,
    write_frame_timing_sidecar,
)
from app.services.multiview_acceptance import materialize_registered_video_timing, prepare_take_timing


def test_fit_affine_calibration_reports_offset_and_drift():
    calibration = fit_affine_calibration(
        [0.0, 10.0, 20.0],
        [0.050, 10.051, 20.052],
        reference_camera="174",
        camera_id="175",
    )

    assert calibration.offset_ms == pytest.approx(50.0)
    assert calibration.drift_ppm == pytest.approx(100.0)
    assert calibration.quality == "good"


def test_fit_affine_calibration_rejects_insufficient_anchors():
    calibration = fit_affine_calibration([0.0], [0.05], reference_camera="174", camera_id="175")

    assert calibration.quality == "unknown"
    assert calibration.anchor_count == 1


def test_build_frame_map_applies_camera_mapping():
    calibration = fit_affine_calibration([0.0, 10.0], [0.050, 10.050], reference_camera="174", camera_id="175")
    frames = [FrameTiming(i, i / 60) for i in range(601)]
    selected = build_frame_map([0.0, 1.0], frames, calibration=calibration)

    assert selected[0].source_frame_index == 3
    assert selected[1].source_frame_index == 63
    assert all(item.status == "ok" for item in selected)


def test_build_frame_map_marks_out_of_range_targets_unavailable():
    frames = [FrameTiming(i, i / 60) for i in range(61)]

    selected = build_frame_map([-1.0, 0.0, 1.0, 2.0], frames)

    assert selected[0].status == "unavailable_out_of_media_range"
    assert selected[1].status == "ok"
    assert selected[2].status == "ok"
    assert selected[3].status == "unavailable_out_of_media_range"


def test_calibrations_from_anchor_rows_fits_each_camera():
    mappings = calibrations_from_anchor_rows(
        [{"174": 0.0, "175": 0.05}, {"174": 10.0, "175": 10.051}],
        reference_camera="174",
        camera_ids=["174", "175"],
    )

    assert mappings["174"].offset_ms == pytest.approx(0.0)
    assert mappings["175"].drift_ppm == pytest.approx(100.0)


def test_retime_filter_expression_uses_offset_and_rate():
    calibration = fit_affine_calibration([0.0, 10.0], [0.05, 10.051], reference_camera="174", camera_id="175")

    expression = retime_filter_expression(calibration)

    assert expression.startswith("setpts=(PTS-STARTPTS-")
    assert "/1.000100000000" in expression


def test_write_frame_timing_sidecar_is_atomic(tmp_path: Path):
    sidecar = tmp_path / "frames.jsonl"
    fake = SimpleNamespace(
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
    with patch("app.services.dual_camera_sync.subprocess.run", return_value=fake):
        summary = write_frame_timing_sidecar("source.ts", sidecar)

    rows = [json.loads(line) for line in sidecar.read_text().splitlines()]
    assert summary["frame_count"] == 2
    assert rows[0]["frame_index"] == 0
    assert rows[0]["pts_seconds"] == pytest.approx(1.4)
    assert rows[0]["keyframe"] is True
    assert rows[1]["pts_seconds"] == pytest.approx(1.416667)
    assert rows[1]["keyframe"] is False
    assert read_frame_timing_sidecar(sidecar)[1].frame_index == 1
    assert summary["timing_authority"] == "source_pts"
    assert summary["fps"] == pytest.approx(59.9988, rel=1e-4)


@pytest.mark.parametrize(
    "frames, message",
    [
        ([], "no video frames"),
        (
            [
                {"best_effort_timestamp_time": "1.0"},
                {"best_effort_timestamp_time": "0.9"},
            ],
            "monotonically",
        ),
    ],
)
def test_write_frame_timing_sidecar_rejects_empty_or_non_monotonic_pts(
    tmp_path: Path, frames: list[dict[str, str]], message: str
):
    sidecar = tmp_path / "frames.jsonl"
    fake = SimpleNamespace(
        returncode=0,
        stdout=json.dumps({"frames": frames}),
        stderr="",
    )
    with patch("app.services.dual_camera_sync.subprocess.run", return_value=fake):
        with pytest.raises(ValueError, match=message):
            write_frame_timing_sidecar("source.ts", sidecar)
    assert not sidecar.exists()


def test_summarize_frame_timing_sidecar_rejects_empty_and_non_monotonic(tmp_path: Path):
    sidecar = tmp_path / "empty.jsonl"
    sidecar.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        summarize_frame_timing_sidecar(sidecar)

    sidecar.write_text(
        '{"frame_index":0,"pts_seconds":1.0}\n'
        '{"frame_index":2,"pts_seconds":0.9}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="monotonically"):
        summarize_frame_timing_sidecar(sidecar)


def test_fit_affine_calibration_degraded_when_residual_exceeds_threshold():
    calibration = fit_affine_calibration(
        [0.0, 10.0, 20.0],
        [0.5, 10.0, 21.0],
        reference_camera="174",
        camera_id="175",
        max_residual_seconds=0.1,
    )
    assert calibration.quality == "degraded"
    assert calibration.reason is not None


def test_fit_affine_calibration_valid_range_from_anchors():
    calibration = fit_affine_calibration(
        [5.0, 15.0, 25.0],
        [5.050, 15.051, 25.052],
        reference_camera="174",
        camera_id="175",
    )
    assert calibration.valid_start_seconds == 5.0
    assert calibration.valid_end_seconds == 25.0


def test_build_frame_map_with_dropped_frames():
    frames = [
        FrameTiming(0, 0.000),
        FrameTiming(1, 0.017),
        FrameTiming(2, 0.033),
        FrameTiming(5, 0.100),  # frames 3,4 dropped
        FrameTiming(6, 0.117),
        FrameTiming(7, 0.133),
    ]
    selected = build_frame_map([0.0, 0.017, 0.050, 0.067, 0.083, 0.100], frames)
    # frame 0 → index 0
    assert selected[0].source_frame_index == 0
    assert selected[0].status == "ok"
    # target 0.050: nearest should be frame 2 (0.033) — 17ms off, still within 33ms tolerance
    assert selected[2].source_frame_index == 2
    # target 0.100: nearest should be frame 5 (0.100)
    assert selected[5].source_frame_index == 5


def test_build_frame_map_with_duplicate_pts():
    frames = [
        FrameTiming(0, 0.000),
        FrameTiming(1, 0.017),
        FrameTiming(2, 0.017),  # duplicate PTS
        FrameTiming(3, 0.033),
        FrameTiming(4, 0.050),
    ]
    selected = build_frame_map([0.017, 0.033], frames)
    assert selected[0].source_pts_seconds == 0.017
    assert selected[0].status == "ok"


def test_build_frame_map_empty_frames_returns_all_unavailable():
    selected = build_frame_map([0.0, 1.0], [])
    assert all(item.status == "unavailable" for item in selected)
    assert all(item.source_frame_index is None for item in selected)


def test_build_frame_map_honours_valid_range():
    cal = SyncCalibration(
        reference_camera="174",
        camera_id="175",
        offset_seconds=0.0,
        rate=1.0,
        drift_ppm=0.0,
        residual_rms_seconds=0.0,
        anchor_count=3,
        quality="good",
        valid_start_seconds=5.0,
        valid_end_seconds=25.0,
    )
    frames = [FrameTiming(i, i / 60) for i in range(1801)]
    selected = build_frame_map([0.0, 5.0, 25.0, 30.0], frames, calibration=cal)
    assert selected[0].status == "unavailable_outside_valid_interval"
    assert selected[1].source_frame_index is not None
    assert selected[2].source_frame_index is not None
    assert selected[3].status == "unavailable_outside_valid_interval"


def test_calibrations_from_anchor_rows_missing_camera_returns_unknown():
    mappings = calibrations_from_anchor_rows(
        [{"174": 0.0, "175": 0.05}],
        reference_camera="174",
        camera_ids=["174", "175", "176"],
    )
    assert "176" in mappings
    assert mappings["176"].quality == "unknown"
    assert mappings["176"].anchor_count == 0


def test_retime_filter_expression_unknown_calibration_returns_default():
    cal = SyncCalibration(
        reference_camera="174",
        camera_id="175",
        offset_seconds=0.0,
        rate=1.0,
        drift_ppm=0.0,
        residual_rms_seconds=math.inf,
        anchor_count=0,
        quality="unknown",
        reason="insufficient anchors",
    )
    expr = retime_filter_expression(cal)
    assert expr == "setpts=(PTS-STARTPTS-0.000000000/TB)/1.000000000000"


def test_manual_anchor_validation_requires_three_events_and_span():
    issues = validate_anchor_payload(
        {
            "reference_camera": "174",
            "cameras": ["174", "175"],
            "anchors": [{"174": 1.0, "175": 1.05}, {"174": 1.0, "175": 1.05}],
        }
    )
    assert "at least 3 shared-event anchors are required" in issues
    assert "anchors must span a positive reference-camera time range" in issues


def test_authoritative_minimum_anchor_count_marks_two_point_fit_degraded():
    calibration = fit_affine_calibration(
        [0.0, 10.0],
        [0.05, 10.05],
        reference_camera="174",
        camera_id="175",
        minimum_anchor_count=3,
    )
    assert calibration.quality == "degraded"
    assert "authoritative calibration" in (calibration.reason or "")


def test_registered_video_timing_reuses_bound_valid_sidecar(tmp_path: Path):
    media = tmp_path / "camera.mp4"
    media.write_bytes(b"media")
    sidecar = Path(f"{media}.pts.jsonl")
    sidecar.write_text(
        '{"frame_index":0,"pts_seconds":0.0}\n'
        '{"frame_index":1,"pts_seconds":0.04}\n',
        encoding="utf-8",
    )

    result = materialize_registered_video_timing(media, slot="cam_1")

    assert result.status == "ready"
    assert result.timing_authority == "source_pts"
    assert result.reused
    assert result.summary["frame_count"] == 2


def test_registered_video_timing_reports_missing_media(tmp_path: Path):
    result = materialize_registered_video_timing(tmp_path / "missing.mp4", slot="cam_1")

    assert result.status == "failed"
    assert result.timing_authority == "missing"
    assert "missing" in (result.reason or "")


def test_prepare_take_timing_is_structured_and_does_not_fallback(tmp_path: Path, monkeypatch):
    media_a = tmp_path / "175_merged.mp4"
    media_b = tmp_path / "174_merged.mp4"
    media_a.write_bytes(b"a")
    media_b.write_bytes(b"b")

    def fake_materialize(path, *, slot, ffprobe_bin):
        return materialize_registered_video_timing(
            path,
            slot=slot,
            sidecar_path=Path(f"{path}.pts.jsonl"),
        )

    monkeypatch.setattr(
        "app.services.multiview_acceptance.materialize_registered_video_timing",
        fake_materialize,
    )
    for media in (media_a, media_b):
        Path(f"{media}.pts.jsonl").write_text(
            '{"frame_index":0,"pts_seconds":0.0}\n',
            encoding="utf-8",
        )

    payload = prepare_take_timing(
        tmp_path,
        video_paths={"cam_1": media_a, "cam_2": media_b},
        output_path=tmp_path / "timing-preparation.json",
    )

    assert payload["status"] == "ready"
    assert payload["timing_authority"] == "source_pts"
    assert (tmp_path / "timing-preparation.json").exists()


def test_capture_track_repair_uses_explicit_session_registration(tmp_path: Path, monkeypatch):
    import app.services.capture_track_service as track_service
    from app.services.multiview_acceptance import repair_capture_track_video_indices

    media = tmp_path / "175_merged.mp4"
    media.write_bytes(b"media")
    Path(f"{media}.pts.jsonl").write_text(
        '{"frame_index":0,"pts_seconds":0.0}\n',
        encoding="utf-8",
    )
    (tmp_path / "metadata").mkdir()
    (tmp_path / "metadata" / "recording_session.json").write_text(
        json.dumps(
            {
                "camera_slots": {"cam_1": {"camera_id": "175"}},
                "registered_video_ids": {"cam_1": "rec-175"},
            }
        ),
        encoding="utf-8",
    )
    track = SimpleNamespace(
        id="track-1",
        slot=SimpleNamespace(value="cam_1"),
        camera_id="175",
        video_id=None,
        timing_authority="missing",
        timing_sidecar_path=None,
        timing_failure_reason=None,
    )
    monkeypatch.setattr(track_service, "get_tracks_for_take", lambda db, take_id: [track])

    class FakeDb:
        def flush(self):
            return None

    class FakeVideoService:
        def get_available_video(self, video_id):
            assert video_id == "rec-175"
            return SimpleNamespace(path=str(media))

    result = repair_capture_track_video_indices(
        FakeDb(),
        "take-1",
        tmp_path,
        video_service=FakeVideoService(),
    )

    assert result["ok"]
    assert track.video_id == "rec-175"
    assert track.timing_authority == "source_pts"
    assert track.timing_sidecar_path == str(Path(f"{media}.pts.jsonl"))


def test_capture_track_repair_rejects_identity_conflict(tmp_path: Path, monkeypatch):
    import app.services.capture_track_service as track_service
    from app.services.multiview_acceptance import repair_capture_track_video_indices

    (tmp_path / "metadata").mkdir()
    (tmp_path / "metadata" / "recording_session.json").write_text(
        json.dumps(
            {
                "camera_slots": {"cam_1": {"camera_id": "175"}},
                "registered_video_ids": {"cam_1": "rec-175"},
            }
        ),
        encoding="utf-8",
    )
    track = SimpleNamespace(
        id="track-1",
        slot=SimpleNamespace(value="cam_1"),
        camera_id="174",
        video_id=None,
    )
    monkeypatch.setattr(track_service, "get_tracks_for_take", lambda db, take_id: [track])

    result = repair_capture_track_video_indices(SimpleNamespace(), "take-1", tmp_path)

    assert not result["ok"]
    assert any("camera identity conflict" in issue for issue in result["issues"])

def _merge_ffprobe_payload():
    """Return a fake subprocess.CompletedProcess with two usable PTS frames."""
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


def _merge_test_session(session_id: str) -> "object":
    """Build a completed dual-camera session with both slots registered."""
    from app.camera.models import CameraSlotConfig, SyncRecordingSession

    return SyncRecordingSession(
        session_id=session_id,
        status="completed",
        camera_slots={
            "cam_1": CameraSlotConfig(role="cam_1", camera_id="174"),
            "cam_2": CameraSlotConfig(role="cam_2", camera_id="175"),
        },
        registered_video_ids={"cam_1": "rec-174", "cam_2": "rec-175"},
        merge_status="completed",
    )


def _merge_test_video_metadata(video_id: str, path: Path):
    from datetime import UTC, datetime

    from app.schemas.video import VideoMetadata

    return VideoMetadata(
        id=video_id,
        original_filename=f"{video_id}.mp4",
        content_type="video/mp4",
        size_bytes=path.stat().st_size,
        path=str(path),
        uploaded_at=datetime.now(UTC),
        source="recording",
    )


def test_request_merge_completed_session_backfills_missing_sidecars(tmp_path, monkeypatch):
    """completed 会话缺失 sidecar 时 request_merge 短路分支仍补写。"""
    from app.camera import sync_recorder_service as module
    from app.services.video_service import video_service

    media_1 = tmp_path / "cam_1.mp4"
    media_1.write_bytes(b"registered-media-1")
    media_2 = tmp_path / "cam_2.mp4"
    media_2.write_bytes(b"registered-media-2")
    session = _merge_test_session("sync-merge-backfill")
    module.SYNC_SESSIONS[session.session_id] = session

    def fake_get(video_id):
        if video_id == "rec-174":
            return _merge_test_video_metadata("rec-174", media_1)
        if video_id == "rec-175":
            return _merge_test_video_metadata("rec-175", media_2)
        return None

    monkeypatch.setattr(video_service, "get_available_video", fake_get)
    service = module.SyncRecordingService()

    try:
        with patch("app.services.dual_camera_sync.subprocess.run", return_value=_merge_ffprobe_payload()):
            result = service.request_merge(session.session_id)

        assert result.merge_status == "completed"
        assert (tmp_path / "cam_1.mp4.pts.jsonl").is_file()
        assert (tmp_path / "cam_2.mp4.pts.jsonl").is_file()
    finally:
        module.SYNC_SESSIONS.pop(session.session_id, None)


def test_request_merge_completed_session_reuses_existing_sidecars(tmp_path, monkeypatch):
    """completed 会话已具备 sidecar 时 request_merge 走幂等快路径，不重复 ffprobe。"""
    from app.camera import sync_recorder_service as module
    from app.services.video_service import video_service

    media_1 = tmp_path / "cam_1.mp4"
    media_1.write_bytes(b"registered-media-1")
    media_2 = tmp_path / "cam_2.mp4"
    media_2.write_bytes(b"registered-media-2")
    for media in (media_1, media_2):
        Path(f"{media}.pts.jsonl").write_text(
            '{"frame_index":0,"pts_seconds":0.033333,"dts_seconds":0.033333,"keyframe":true}\n',
            encoding="utf-8",
        )
    session = _merge_test_session("sync-merge-reuse")
    module.SYNC_SESSIONS[session.session_id] = session

    def fake_get(video_id):
        if video_id == "rec-174":
            return _merge_test_video_metadata("rec-174", media_1)
        if video_id == "rec-175":
            return _merge_test_video_metadata("rec-175", media_2)
        return None

    monkeypatch.setattr(video_service, "get_available_video", fake_get)
    service = module.SyncRecordingService()

    try:
        with patch("app.services.dual_camera_sync.subprocess.run", return_value=_merge_ffprobe_payload()) as run:
            result = service.request_merge(session.session_id)

        assert result.merge_status == "completed"
        run.assert_not_called()
    finally:
        module.SYNC_SESSIONS.pop(session.session_id, None)
