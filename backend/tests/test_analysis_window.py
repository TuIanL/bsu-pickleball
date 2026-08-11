from __future__ import annotations

import pytest

from app.services.analysis_window import AnalysisWindowError, resolve_analysis_window


def test_analysis_window_uses_half_open_requested_range_and_rolls():
    window = resolve_analysis_window(
        source_duration_ms=10_000,
        source_frame_count=300,
        fps=30.0,
        clip_start_ms=2_000,
        clip_end_ms=4_000,
    )

    assert window.decoded_start_ms == 500
    assert window.decoded_end_ms == 4_500
    assert window.requested_start_frame == 60
    assert window.requested_end_frame == 120
    assert window.decoded_start_frame == 15
    assert window.decoded_end_frame == 135
    assert window.is_requested_frame(60)
    assert not window.is_requested_frame(120)
    assert window.metadata()["source_frame_count"] == 300


def test_analysis_window_clips_decode_range_at_video_boundary():
    window = resolve_analysis_window(
        source_duration_ms=3_000,
        source_frame_count=90,
        fps=30.0,
        clip_start_ms=2_500,
        clip_end_ms=5_000,
    )
    assert window.requested_end_ms == 5_000
    assert window.decoded_end_ms == 3_000
    assert window.decoded_end_frame == 90


@pytest.mark.parametrize(
    "start,end",
    [(-1, 100), (100, 100), (100, 50)],
)
def test_analysis_window_rejects_invalid_ranges(start, end):
    with pytest.raises(AnalysisWindowError):
        resolve_analysis_window(
            source_duration_ms=10_000,
            source_frame_count=300,
            fps=30.0,
            clip_start_ms=start,
            clip_end_ms=end,
        )


def test_analysis_window_rejects_partial_clip_payload():
    with pytest.raises(AnalysisWindowError):
        resolve_analysis_window(
            source_duration_ms=10_000,
            source_frame_count=300,
            fps=30.0,
            clip_start_ms=100,
            clip_end_ms=None,
        )
