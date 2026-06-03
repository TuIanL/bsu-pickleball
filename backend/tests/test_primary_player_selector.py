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

    assert {selection.track_id for selection in selected} == {1, 2}
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


def test_court_aware_selector_prefers_target_court_players_over_neighbor_court_motion():
    selector = PrimaryPlayerSelector(min_confidence=0.65, max_subjects=4, court_margin_ft=4, target_court_threshold=0.5)
    target_tracks = [
        Track(track_id=1, bbox=[10, 10, 30, 70], confidence=0.9),
        Track(track_id=2, bbox=[40, 10, 60, 70], confidence=0.88),
        Track(track_id=3, bbox=[10, 80, 30, 140], confidence=0.91),
        Track(track_id=4, bbox=[40, 80, 60, 140], confidence=0.89),
    ]
    neighbor_tracks = [
        Track(track_id=5, bbox=[70, 10, 90, 70], confidence=0.95),
        Track(track_id=6, bbox=[75, 80, 95, 140], confidence=0.94),
    ]

    for frame in range(6):
        tracks = [
            *[
                track.model_copy(update={"bbox": [track.bbox[0] + frame, track.bbox[1], track.bbox[2] + frame, track.bbox[3]]})
                for track in target_tracks
            ],
            *[
                track.model_copy(update={"bbox": [track.bbox[0] + frame, track.bbox[1], track.bbox[2] + frame, track.bbox[3]]})
                for track in neighbor_tracks
            ],
        ]
        positions = [
            player_position(1, frame, 4 + frame * 0.1, 8),
            player_position(2, frame, 15 - frame * 0.1, 8),
            player_position(3, frame, 4 + frame * 0.1, 34),
            player_position(4, frame, 15 - frame * 0.1, 34),
            player_position(5, frame, 34 + frame * 0.2, 8),
            player_position(6, frame, 36 + frame * 0.2, 34),
        ]
        selected = selector.select(tracks, positions=positions, frame_width=120, frame_height=160)

    assert {selection.track_id for selection in selected} == {1, 2, 3, 4}
    excluded = {diagnostic.track_id: diagnostic for diagnostic in selector.last_diagnostics}
    assert excluded[5].candidate_label == "neighbor_court_player"
    assert excluded[6].reason == "low target-court membership"


def test_court_aware_selector_tolerates_short_boundary_excursion():
    selector = PrimaryPlayerSelector(min_confidence=0.65, max_subjects=1, court_margin_ft=2, target_court_threshold=0.4)
    track = Track(track_id=1, bbox=[10, 10, 30, 70], confidence=0.92)

    for frame, y in enumerate([42, 43, 44.6, 43.5, 42.5]):
        selected = selector.select([track], positions=[player_position(1, frame, 10, y)], frame_width=100, frame_height=100)

    assert [selection.track_id for selection in selected] == [1]
    diagnostic = selector.last_diagnostics[0]
    assert diagnostic.selected is True
    assert diagnostic.target_court_score > 0.4


def test_court_aware_selector_does_not_fill_missing_players_with_neighbor_court():
    selector = PrimaryPlayerSelector(min_confidence=0.65, max_subjects=4, court_margin_ft=3, target_court_threshold=0.5)
    tracks = [
        Track(track_id=1, bbox=[10, 10, 30, 70], confidence=0.9),
        Track(track_id=2, bbox=[40, 10, 60, 70], confidence=0.89),
        Track(track_id=5, bbox=[70, 10, 90, 70], confidence=0.96),
    ]
    positions = [
        player_position(1, 0, 4, 8),
        player_position(2, 0, 15, 8),
        player_position(5, 0, 36, 8),
    ]

    selected = selector.select(tracks, positions=positions, frame_width=100, frame_height=100)

    assert {selection.track_id for selection in selected} == {1, 2}


def test_attention_unavailable_records_fallback_diagnostics():
    selector = PrimaryPlayerSelector(
        min_confidence=0.65,
        max_subjects=1,
        attention_enabled=True,
        attention_model_path=None,
    )
    track = Track(track_id=1, bbox=[10, 10, 30, 70], confidence=0.92)

    selected = selector.select([track], positions=[player_position(1, 0, 10, 20)], frame_width=100, frame_height=100)

    assert [selection.track_id for selection in selected] == [1]
    assert selector.last_selection_mode == "fallback"
    assert "model path" in (selector.last_fallback_reason or "")


def player_position(track_id, frame, x_ft, y_ft):
    return PlayerFramePosition(
        frame_index=frame,
        timestamp=frame / 30,
        track_id=track_id,
        bbox=[x_ft, y_ft, x_ft + 1, y_ft + 2],
        image_footpoint=[x_ft + 0.5, y_ft + 2],
        court_position=[x_ft, y_ft],
        confidence=0.9,
        valid=True,
        validity="valid",
    )
