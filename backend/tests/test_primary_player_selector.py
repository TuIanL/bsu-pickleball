import pytest

from app.schemas.tracking import PlayerFramePosition, Track
from app.vision.player_tracking_engine.primary_player_selector import PrimaryPlayerSelector


def test_primary_player_selector_keeps_high_confidence_tracks_by_rank():
    selector = PrimaryPlayerSelector(min_confidence=0.65, max_subjects=2)
    tracks = [
        Track(track_id=1, bbox=[10, 10, 30, 70], confidence=0.91),
        Track(track_id=2, bbox=[40, 10, 60, 70], confidence=0.87),
        Track(track_id=3, bbox=[70, 10, 90, 70], confidence=0.78),
    ]

    selected = selector.select(tracks, positions=[], frame_width=100, frame_height=100)

    assert [selection.track_id for selection in selected] == [1, 2]
    assert selected[0].rolling_confidence == pytest.approx(0.91)


def test_primary_player_selector_drops_low_confidence_tracks():
    selector = PrimaryPlayerSelector(min_confidence=0.65, max_subjects=4)
    tracks = [
        Track(track_id=1, bbox=[10, 10, 30, 70], confidence=0.91),
        Track(track_id=2, bbox=[40, 10, 60, 70], confidence=0.52),
    ]

    selected = selector.select(tracks, positions=[], frame_width=100, frame_height=100)

    assert [selection.track_id for selection in selected] == [1]


def test_primary_player_selector_keeps_line_out_player_without_position():
    selector = PrimaryPlayerSelector(min_confidence=0.65, max_subjects=4)
    track = Track(track_id=1, bbox=[110, 10, 140, 80], confidence=0.9)

    selected = selector.select([track], positions=[], frame_width=100, frame_height=100)

    assert [selection.track_id for selection in selected] == [1]


def test_primary_player_selector_can_reject_far_scene_positions():
    selector = PrimaryPlayerSelector(min_confidence=0.65, max_subjects=4, court_margin_ft=12)
    track = Track(track_id=1, bbox=[10, 10, 30, 70], confidence=0.9)
    position = PlayerFramePosition(
        frame_index=0,
        timestamp=0.0,
        track_id=1,
        bbox=track.bbox,
        image_footpoint=[20, 70],
        court_position=[80, 120],
        confidence=0.9,
        valid=False,
        validity="invalid",
    )

    selected = selector.select([track], positions=[position], frame_width=100, frame_height=100)

    assert selected == []
