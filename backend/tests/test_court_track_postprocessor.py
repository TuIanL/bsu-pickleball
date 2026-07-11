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


def _process(
    observations: list[CourtTrackObservation] | None = None,
    events: list[CourtTrackEvent] | None = None,
    fps: float = 30.0,
    total_frames: int = 100,
) -> CourtTrackPostProcessResult:
    pp = CourtTrackPostProcessor()
    return pp.process(
        observations or [],
        events or [],
        fps=fps,
        total_frames=total_frames,
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


class TestProcess:
    """Tests for the new process() method (CourtTrackPostProcessResult)."""

    def test_build_roster_collects_and_sorts(self):
        """11.1: _build_roster collects all unique player_ids in natural sort order."""
        pp = CourtTrackPostProcessor()
        obs = [
            _obs(0, player_id="Player_2"),
            _obs(1, player_id="Player_10"),
            _obs(2, player_id="Player_1"),
            _obs(3, player_id="Player_1"),
        ]
        roster = pp._build_roster(pp._normalize_player_ids(obs))
        assert roster == ["Player_1", "Player_2", "Player_10"]

    def test_assign_render_slots_deterministic(self):
        """11.2: _assign_render_slots returns deterministic mapping."""
        pp = CourtTrackPostProcessor()
        roster = ["Player_1", "Player_2"]
        result1 = pp._assign_render_slots(roster)
        result2 = pp._assign_render_slots(roster)
        assert result1 == result2
        assert result1 == {"Player_1": "slot_1", "Player_2": "slot_2"}

    def test_render_slot_overflow_error(self):
        """11.3: observed_player_count > MAX_RENDER_SLOTS raises RenderSlotOverflowError."""
        from app.vision.pickleball_game_analysis.court_track_types import MAX_RENDER_SLOTS, RenderSlotOverflowError

        obs = [_obs(i, player_id=f"Player_{i}") for i in range(MAX_RENDER_SLOTS + 1)]
        with pytest.raises(RenderSlotOverflowError) as excinfo:
            _process(observations=obs)
        assert excinfo.value.observed == MAX_RENDER_SLOTS + 1
        assert excinfo.value.maximum == MAX_RENDER_SLOTS

    def test_overflow_error_catchable(self):
        """11.4: RenderSlotOverflowError can be caught without crashing surrounding code."""
        from app.vision.pickleball_game_analysis.court_track_types import MAX_RENDER_SLOTS, RenderSlotOverflowError

        obs = [_obs(i, player_id=f"Player_{i}") for i in range(MAX_RENDER_SLOTS + 1)]
        caught = False
        try:
            _process(observations=obs)
        except RenderSlotOverflowError:
            caught = True
        assert caught

    def test_canonical_player_id_normalization(self):
        """11.5: process normalizes mixed-case player_ids."""
        obs = [
            _obs(0, player_id="player_1"),
            _obs(1, player_id="PLAYER_2"),
        ]
        result = _process(observations=obs)
        player_ids = sorted(p.player_id for p in result.players)
        assert player_ids == ["Player_1", "Player_2"]

    def test_identity_epoch_change_triggers_new_segment(self):
        """11.6: identity_epoch change triggers new segment with break_before = identity_reset."""
        obs = [
            _obs(0, player_id="Player_1", epoch=0),
            _obs(1, player_id="Player_1", epoch=0),
            _obs(5, player_id="Player_1", epoch=1),
            _obs(6, player_id="Player_1", epoch=1),
        ]
        events = [_event(5, "Player_1", "player_reset_after_prolonged_loss")]
        result = _process(observations=obs, events=events, total_frames=10)
        assert len(result.segments) == 2
        break_before_values = [s.break_before for s in result.segments]
        assert break_before_values[0] == "start"
        assert any(b == "identity_reset" for b in break_before_values)

    def test_visible_gap_triggers_new_segment(self):
        """11.7: visible_gap triggers new segment without affecting identity_epoch."""
        obs = [
            _obs(0, player_id="Player_1", epoch=0),
            _obs(1, player_id="Player_1", epoch=0),
            _obs(20, player_id="Player_1", epoch=0),  # gap = 19 frames ≈ 0.633s > 0.60s
            _obs(21, player_id="Player_1", epoch=0),
        ]
        result = _process(observations=obs, fps=30, total_frames=25)
        assert len(result.segments) == 2
        for seg in result.segments:
            assert seg.identity_epoch == 0  # epoch unchanged
        # At least one segment should have visible_gap break
        assert any(s.break_before == "visible_gap" for s in result.segments)

    def test_track_reconnect_no_new_segment(self):
        """11.8: Normal track reconnection (spatiotemporal continuity) doesn't create new segment."""
        obs = [
            _obs(0, player_id="Player_1", epoch=0, x=0.0, y=0.0),
            _obs(3, player_id="Player_1", epoch=0, x=3.0, y=3.0),
            _obs(6, player_id="Player_1", epoch=0, x=6.0, y=6.0),
        ]
        result = _process(observations=obs, fps=30, total_frames=10)
        assert len(result.segments) == 1

    def test_multiple_visible_gaps_in_same_epoch(self):
        """11.9: Two visible gaps within same epoch produce 3 segments (s0, s1, s2)."""
        obs = [
            _obs(0, player_id="Player_1", epoch=0),
            _obs(1, player_id="Player_1", epoch=0),
            _obs(20, player_id="Player_1", epoch=0),  # gap 1
            _obs(21, player_id="Player_1", epoch=0),
            _obs(40, player_id="Player_1", epoch=0),  # gap 2
            _obs(41, player_id="Player_1", epoch=0),
        ]
        result = _process(observations=obs, fps=30, total_frames=45)
        assert len(result.segments) == 3

    def test_segment_id_format(self):
        """11.10: segment_id format is {player_id}:e{epoch}:s{index}."""
        obs = [
            _obs(0, player_id="Player_1", epoch=0),
            _obs(1, player_id="Player_1", epoch=0),
            _obs(20, player_id="Player_1", epoch=0),  # gap triggers s1
            _obs(21, player_id="Player_1", epoch=0),
        ]
        result = _process(observations=obs, fps=30, total_frames=25)
        for seg in result.segments:
            assert seg.segment_id.startswith("Player_1:e0:s")
        assert result.segments[0].segment_id == "Player_1:e0:s0"
        assert result.segments[1].segment_id == "Player_1:e0:s1"

    def test_render_slot_consistent_across_epochs(self):
        """11.11: render_slot is consistent across epoch/segment changes."""
        obs = [
            _obs(0, player_id="Player_1", epoch=0),
            _obs(1, player_id="Player_1", epoch=0),
            _obs(5, player_id="Player_1", epoch=1),
            _obs(6, player_id="Player_1", epoch=1),
        ]
        result = _process(observations=obs, total_frames=10)
        for s in result.samples:
            assert s.render_slot == "slot_1"

    def test_multi_player_interleaved_sequence_index(self):
        """11.12: Multiple players in same frame, sequence_index is globally unique."""
        obs = [
            _obs(0, player_id="Player_1", x=0.0, y=0.0),
            _obs(0, player_id="Player_2", x=10.0, y=10.0),
            _obs(1, player_id="Player_1", x=1.0, y=1.0),
            _obs(1, player_id="Player_2", x=11.0, y=11.0),
        ]
        result = _process(observations=obs, total_frames=5)
        indices = [s.sequence_index for s in result.samples]
        assert len(indices) == len(set(indices)), "sequence_index must be unique"
        assert indices == list(range(len(indices))), "sequence_index must be sequential from 0"

    def test_deterministic_output(self):
        """11.13: Same input produces identical results."""
        obs = [
            _obs(0, player_id="Player_2", epoch=0, x=0.0, y=0.0),
            _obs(1, player_id="Player_1", epoch=0, x=5.0, y=5.0),
            _obs(20, player_id="Player_2", epoch=0, x=1.0, y=1.0),
        ]
        result1 = _process(observations=obs, total_frames=25)
        result2 = _process(observations=obs, total_frames=25)
        assert len(result1.players) == len(result2.players)
        assert len(result1.segments) == len(result2.segments)
        assert len(result1.samples) == len(result2.samples)
        for s1, s2 in zip(result1.samples, result2.samples):
            assert s1.render_slot == s2.render_slot
            assert s1.segment_id == s2.segment_id

    def test_v2_artifact_json_structure(self):
        """11.14: process() result can be serialized to complete v2 JSON."""
        from app.vision.pickleball_game_analysis.visualization_schemas import serialize_render_trajectory_v2

        obs = [
            _obs(0, player_id="Player_1", x=0.0, y=0.0),
            _obs(0, player_id="Player_2", x=10.0, y=10.0),
        ]
        result = _process(observations=obs, total_frames=5)
        payload = serialize_render_trajectory_v2({
            "players": result.players,
            "segments": result.segments,
            "samples": result.samples,
        })
        assert payload["schema_version"] == "player-render-trajectory.v2"
        assert len(payload["players"]) == 2
        assert len(payload["segments"]) >= 1
        assert len(payload["samples"]) >= 2
        for sample in payload["samples"]:
            assert "player_id" in sample
            assert "render_slot" in sample
            assert "segment_id" in sample
            assert "identity_epoch" in sample
            assert "sequence_index" in sample

    def test_v1_field_compatibility(self):
        """11.15: v1 required fields (frame_index, timestamp_seconds, x_ft, y_ft, source, confidence) are present in samples."""
        obs = [
            _obs(0, player_id="Player_1", x=0.0, y=0.0, confidence=0.9),
            _obs(1, player_id="Player_1", x=5.0, y=5.0, confidence=0.85),
        ]
        result = _process(observations=obs, total_frames=5)
        for s in result.samples:
            assert hasattr(s, "frame_index")
            assert hasattr(s, "timestamp_seconds")
            assert hasattr(s, "x_ft")
            assert hasattr(s, "y_ft")
            assert hasattr(s, "source")
            assert hasattr(s, "confidence")

    def test_no_false_projection_gap(self):
        """11.16: No explicit projection event doesn't create projection_gap."""
        obs = [
            _obs(0, player_id="Player_1", epoch=0, projection_status="inside_court"),
            _obs(1, player_id="Player_1", epoch=0, projection_status="inside_court"),
        ]
        result = _process(observations=obs, total_frames=5)
        for seg in result.segments:
            assert seg.break_before != "projection_gap"

    def test_fourth_player_late_roster_stable(self):
        """11.17: Fourth player appearing late gets stable slot_4 in final roster."""
        obs = [
            _obs(0, player_id="Player_1"),
            _obs(0, player_id="Player_2"),
            _obs(0, player_id="Player_3"),
            _obs(100, player_id="Player_4"),
        ]
        result = _process(observations=obs, fps=30, total_frames=150)
        slot_map = {p.player_id: p.render_slot for p in result.players}
        assert slot_map["Player_1"] == "slot_1"
        assert slot_map["Player_2"] == "slot_2"
        assert slot_map["Player_3"] == "slot_3"
        assert slot_map["Player_4"] == "slot_4"

    def test_process_returns_complete_result(self):
        """11.18: process() returns complete CourtTrackPostProcessResult with all fields."""
        obs = [
            _obs(0, player_id="Player_1"),
            _obs(1, player_id="Player_1"),
            _obs(2, player_id="Player_2"),
        ]
        result = _process(observations=obs, total_frames=5)
        assert hasattr(result, "players")
        assert hasattr(result, "segments")
        assert hasattr(result, "samples")
        assert len(result.players) == 2
        assert len(result.segments) >= 1
        assert len(result.samples) >= 3
        # Verify player metadata fields
        for p in result.players:
            assert p.render_slot
            assert p.player_id
        # Verify segment metadata fields
        for seg in result.segments:
            assert seg.segment_id
            assert seg.player_id in ("Player_1", "Player_2")
            assert seg.break_before in ("start", "visible_gap", "identity_reset")

    def test_build_tracks_backward_compatible(self):
        """11.19: build_tracks() still returns ProcessedCourtTracks with render_tracks as list[RenderFrame]."""
        pp = CourtTrackPostProcessor()
        obs = [
            _obs(0, player_id="Player_1", x=0.0, y=0.0),
            _obs(5, player_id="Player_1", x=5.0, y=5.0),
        ]
        result = pp.build_tracks(obs, [], fps=30, total_frames=10)
        from app.vision.pickleball_game_analysis.court_track_types import ProcessedCourtTracks
        assert isinstance(result, ProcessedCourtTracks)
        assert hasattr(result, "render_tracks")
        assert len(result.render_tracks) >= 2
        for rf in result.render_tracks:
            assert isinstance(rf, RenderFrame)


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
