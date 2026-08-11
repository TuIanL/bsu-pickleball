from pathlib import Path

import pytest

from app.services.analysis_window import resolve_analysis_window
from app.services.dual_camera_sync import FrameTiming
from app.services.frame_timing_provider import FrameTimingProvider


def test_source_pts_provider_is_versioned_and_seekable(tmp_path: Path):
    sidecar = tmp_path / "camera.pts.jsonl"
    sidecar.write_text(
        '{"frame_index":0,"pts_seconds":10.0,"dts_seconds":10.0,"keyframe":1}\n'
        '{"frame_index":1,"pts_seconds":10.04,"dts_seconds":10.03,"keyframe":0}\n'
        '{"frame_index":2,"pts_seconds":10.11,"dts_seconds":10.10,"keyframe":0}\n',
        encoding="utf-8",
    )

    provider = FrameTimingProvider.from_sidecar(sidecar, media_path=tmp_path / "camera.ts")

    assert provider.is_source_pts
    assert provider.provenance.schema_version == "frame_timing_provider.v1"
    assert provider.timestamp_for_frame(2) == pytest.approx(10.11)
    assert provider.frame_index_at_or_after(10.05) == 2
    assert provider.frame_index_at_or_after_take_time(0.05) == 2
    assert provider.nearest_frame(10.05).frame_index == 1
    assert provider.metadata()["authority"] == "source_pts"


def test_missing_pts_is_explicit_legacy_compatibility():
    provider = FrameTimingProvider.nominal(frame_count=3, fps=25.0)

    assert not provider.is_source_pts
    assert provider.provenance.authority == "legacy_nominal_fps"
    assert provider.provenance.reason
    assert provider.timestamp_for_frame(2) == pytest.approx(0.08)


def test_invalid_sidecar_falls_back_with_explicit_diagnostic(tmp_path: Path):
    media = tmp_path / "camera.mp4"
    sidecar = tmp_path / "camera.mp4.pts.jsonl"
    media.write_bytes(b"placeholder")
    sidecar.write_text(
        '{"frame_index":0,"pts_seconds":0.0}\n'
        '{"frame_index":1,"pts_seconds":-0.1}\n',
        encoding="utf-8",
    )

    provider = FrameTimingProvider.from_media(media, frame_count=2, fps=25.0)

    assert provider.provenance.authority == "legacy_nominal_fps"
    assert "invalid" in (provider.provenance.reason or "")


def test_analysis_window_uses_pts_boundaries_when_available():
    provider = FrameTimingProvider(
        frames=(
            FrameTiming(0, 0.0),
            FrameTiming(1, 0.04),
            FrameTiming(2, 0.11),
            FrameTiming(3, 0.17),
            FrameTiming(4, 0.22),
        ),
        provenance=FrameTimingProvider.nominal(frame_count=1, fps=1).provenance,
        fps=20.0,
    )
    provider = FrameTimingProvider(
        frames=provider.frames,
        provenance=provider.provenance.__class__(authority="source_pts"),
        fps=20.0,
    )

    window = resolve_analysis_window(
        source_duration_ms=250,
        source_frame_count=5,
        fps=20.0,
        clip_start_ms=50,
        clip_end_ms=180,
        pre_roll_ms=0,
        post_roll_ms=0,
        timing_provider=provider,
    )

    assert window.requested_start_frame == 2
    assert window.requested_end_frame == 4
    assert window.metadata()["timing_provenance"]["authority"] == "source_pts"
