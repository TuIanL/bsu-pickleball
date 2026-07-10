from __future__ import annotations

import math

import pytest

from app.vision.pickleball_game_analysis.court_track_types import (
    CourtTrackObservation,
    CourtTrackEvent,
    ProcessedCourtTracks,
    RenderFrame,
)
from app.vision.pickleball_game_analysis.court_track_postprocessor import (
    CourtTrackPostProcessor,
)


def _obs(
    frame_index: int,
    player_id: str = "Player_1",
    epoch: int = 0,
    x: float = 0.0,
    y: float = 0.0,
    confidence: float = 0.9,
    projection_status: str = "inside_court",
    tracking_status: str = "detected",
) -> CourtTrackObservation:
    timestamp = frame_index / 30.0
    return CourtTrackObservation(
        frame_index=frame_index,
        timestamp_seconds=timestamp,
        player_id=player_id,
        identity_epoch=epoch,
        track_id=1,
        raw_x_ft=x,
        raw_y_ft=y,
        confidence=confidence,
        projection_status=projection_status,
        projection_confidence=confidence * 0.95,
        footpoint_method="bbox_bottom",
        lock_state=None,
        tracking_status=tracking_status,
    )


def _event(frame_index: int, player_id: str, event_type: str) -> CourtTrackEvent:
    return CourtTrackEvent(
        frame_index=frame_index,
        timestamp_seconds=frame_index / 30.0,
        player_id=player_id,
        event_type=event_type,
    )


class TestBuildTracks:
    def test_empty_observations(self):
        pp = CourtTrackPostProcessor()
        result = pp.build_tracks([], [], fps=30, total_frames=100)
        assert len(result.render_tracks) == 0

    def test_single_observation(self):
        pp = CourtTrackPostProcessor()
        obs = [_obs(0, x=5.0, y=10.0)]
        result = pp.build_tracks(obs, [], fps=30, total_frames=10)
        assert len(result.render_tracks) == 1
        assert result.render_tracks[0].x_ft == 5.0
        assert result.render_tracks[0].y_ft == 10.0
        assert result.render_tracks[0].source == "observed"

    def test_two_observations_interpolated(self):
        pp = CourtTrackPostProcessor()
        obs = [
            _obs(0, x=0.0, y=0.0),
            _obs(5, x=10.0, y=10.0),
        ]
        result = pp.build_tracks(obs, [], fps=30, total_frames=10)
        assert len(result.render_tracks) == 6  # 0 + 4 interpolated + 5
        assert result.render_tracks[0].source == "observed"
        assert result.render_tracks[1].source == "interpolated"
        assert result.render_tracks[-1].source == "observed"
        assert result.render_tracks[1].x_ft == pytest.approx(2.0)  # frame 1
        assert result.render_tracks[3].x_ft == pytest.approx(6.0)  # frame 3

    def test_gap_exceeds_max_visible_no_interpolation(self):
        pp = CourtTrackPostProcessor(max_visible_gap_seconds=0.6)
        obs = [
            _obs(0, x=0.0, y=0.0),
            _obs(20, x=10.0, y=10.0),  # gap = 20/30 ≈ 0.667s > 0.6s
        ]
        result = pp.build_tracks(obs, [], fps=30, total_frames=25)
        # Only the two observed endpoints, no interpolation in between
        assert len(result.render_tracks) == 2
        assert result.render_tracks[0].source == "observed"
        assert result.render_tracks[1].source == "observed"

    def test_gap_mid_interpolation_confidence_decay(self):
        pp = CourtTrackPostProcessor(
            max_interpolation_gap_seconds=0.35,
            max_visible_gap_seconds=0.60,
        )
        obs = [
            _obs(0, x=0.0, y=0.0, confidence=0.9),
            _obs(14, x=10.0, y=10.0, confidence=0.9),  # gap ≈ 0.467s
        ]
        result = pp.build_tracks(obs, [], fps=30, total_frames=20)
        assert len(result.render_tracks) == 15
        mid_conf = result.render_tracks[7].confidence
        # Decayed confidence < 0.9 * 0.95 = 0.855
        assert mid_conf < 0.855

    def test_max_interpolation_gap_full_confidence(self):
        pp = CourtTrackPostProcessor(
            max_interpolation_gap_seconds=0.35,
        )
        obs = [
            _obs(0, x=0.0, y=0.0, confidence=0.9),
            _obs(10, x=10.0, y=10.0, confidence=0.85),  # gap ≈ 0.333s ≤ 0.35
        ]
        result = pp.build_tracks(obs, [], fps=30, total_frames=15)
        assert len(result.render_tracks) == 11
        # full confidence: min(0.9, 0.85) * 0.95 = 0.8075
        assert result.render_tracks[1].confidence == pytest.approx(0.8075)
        assert result.render_tracks[5].confidence == pytest.approx(0.8075)


class TestSpikeRejection:
    def test_three_point_spike_rejected(self):
        pp = CourtTrackPostProcessor(max_spike_displacement_ft=6.0)
        obs = [
            _obs(0, x=5.0, y=10.0),
            _obs(1, x=25.0, y=10.0),   # spike: 20ft from both neighbors
            _obs(2, x=5.2, y=10.1),
        ]
        result = pp.build_tracks(obs, [], fps=30, total_frames=5)
        assert len(result.render_tracks) == 3
        # frame 1 should be interpolated between frame 0 and 2, not using spike
        assert result.render_tracks[1].source == "interpolated"
        assert result.render_tracks[1].x_ft == pytest.approx(5.1)  # (5.0 + 5.2) / 2
        assert result.render_tracks[1].y_ft == pytest.approx(10.05)

    def test_not_a_spike_passes_through(self):
        pp = CourtTrackPostProcessor(max_spike_displacement_ft=6.0)
        obs = [
            _obs(0, x=5.0, y=10.0),
            _obs(1, x=10.0, y=10.0),   # 5ft displacement, within threshold
            _obs(2, x=15.0, y=10.0),
        ]
        result = pp.build_tracks(obs, [], fps=30, total_frames=5)
        assert len(result.render_tracks) == 3
        assert result.render_tracks[1].source == "observed"

    def test_projection_failed_dropped(self):
        pp = CourtTrackPostProcessor()
        obs = [
            _obs(0, x=5.0, y=10.0),
            _obs(1, x=10.0, y=10.0, projection_status="projection_failed"),
            _obs(2, x=15.0, y=10.0),
        ]
        result = pp.build_tracks(obs, [], fps=30, total_frames=5)
        assert len(result.render_tracks) == 3
        # frame 1 should be interpolated between 0 and 2
        assert result.render_tracks[1].source == "interpolated"

    def test_non_finite_value_dropped(self):
        pp = CourtTrackPostProcessor()
        obs = [
            _obs(0, x=5.0, y=10.0),
            _obs(1, x=float("nan"), y=10.0),
            _obs(2, x=15.0, y=10.0),
        ]
        result = pp.build_tracks(obs, [], fps=30, total_frames=5)
        assert len(result.render_tracks) == 3
        assert result.render_tracks[1].source == "interpolated"

    def test_inf_value_dropped(self):
        pp = CourtTrackPostProcessor()
        obs = [
            _obs(0, x=5.0, y=10.0),
            _obs(1, x=float("inf"), y=10.0),
            _obs(2, x=15.0, y=10.0),
        ]
        result = pp.build_tracks(obs, [], fps=30, total_frames=5)
        assert len(result.render_tracks) == 3


class TestSegmentation:
    def test_different_players_separate(self):
        pp = CourtTrackPostProcessor()
        obs = [
            _obs(0, player_id="Player_1", x=0.0, y=0.0),
            _obs(1, player_id="Player_2", x=10.0, y=10.0),
        ]
        result = pp.build_tracks(obs, [], fps=30, total_frames=5)
        assert len(result.render_tracks) == 2

    def test_epoch_change_cuts_segment(self):
        pp = CourtTrackPostProcessor()
        obs = [
            _obs(0, player_id="Player_1", epoch=0, x=0.0, y=0.0),
            _obs(1, player_id="Player_1", epoch=0, x=2.0, y=2.0),
            _obs(5, player_id="Player_1", epoch=1, x=10.0, y=10.0),
            _obs(6, player_id="Player_1", epoch=1, x=12.0, y=12.0),
        ]
        result = pp.build_tracks(obs, [], fps=30, total_frames=10)
        # Two segments: frames 0-1 and 5-6, no interpolation across epoch boundary
        assert len(result.render_tracks) == 4
        assert result.render_tracks[0].frame_index == 0
        assert result.render_tracks[1].frame_index == 1
        assert result.render_tracks[2].frame_index == 5
        assert result.render_tracks[3].frame_index == 6


class TestCanonicalPlayerId:
    def test_importable(self):
        from app.vision.pickleball_game_analysis.visualization_schemas import canonical_player_id
        assert canonical_player_id("player_1") == "Player_1"
        assert canonical_player_id("Player_1") == "Player_1"
        assert canonical_player_id("player_2") == "Player_2"
        assert canonical_player_id("Player_2") == "Player_2"
        assert canonical_player_id("unknown") == "unknown"


class TestPlayerRenderPointsFromArtifact:
    def test_parse_empty(self):
        from app.vision.pickleball_game_analysis.visualization_schemas import player_render_points_from_artifact
        assert player_render_points_from_artifact({}) == []
        assert player_render_points_from_artifact({"players": {}}) == []

    def test_parse_valid(self):
        from app.vision.pickleball_game_analysis.visualization_schemas import player_render_points_from_artifact
        payload = {
            "players": {
                "Player_1": [
                    {"frame_index": 0, "timestamp_seconds": 0.0, "x_ft": 5.0, "y_ft": 10.0, "source": "observed", "confidence": 0.9},
                    {"frame_index": 1, "timestamp_seconds": 0.033, "x_ft": 5.5, "y_ft": 10.5, "source": "interpolated", "confidence": 0.85},
                ]
            }
        }
        points = player_render_points_from_artifact(payload)
        assert len(points) == 2
        assert points[0].x_ft == 5.0
        assert points[0].frame_index == 0
        assert points[1].source == "interpolated"
