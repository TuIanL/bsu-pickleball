import pytest

from app.schemas.tracking import PlayerFramePosition, PlayerIdentityDiagnostic, PlayerTrajectoryArtifact
from app.vision.courtvision_calibration_engine.court_units import (
    PICKLEBALL_COURT_LENGTH_M,
    PICKLEBALL_COURT_WIDTH_M,
    feet_to_meters,
)
from app.vision.player_tracking_engine.player_identity import PlayerIdentityConfig, PlayerIdentityManager


def position(track_id, frame, x_ft, y_ft, timestamp=None):
    return PlayerFramePosition(
        frame_index=frame,
        timestamp=float(frame if timestamp is None else timestamp),
        track_id=track_id,
        bbox=[x_ft, y_ft, x_ft + 1, y_ft + 2],
        image_footpoint=[x_ft + 0.5, y_ft + 2],
        court_position=[x_ft, y_ft],
        court_unit="ft",
        confidence=0.9,
    )


@pytest.mark.parametrize("event", ["side_quota_fallback_replaced", "fallback_tentative_promoted"])
def test_player_identity_diagnostic_accepts_lock_manager_events(event):
    diagnostic = PlayerIdentityDiagnostic(
        frame_index=0,
        event=event,
        reason="test",
    )

    assert diagnostic.event == event


def test_player_trajectory_artifact_serializes_metric_metadata_and_track_history():
    manager = PlayerIdentityManager(PlayerIdentityConfig(smoothing_window=3))

    manager.update(0, [position(1, 0, 10, 20)])
    manager.update(1, [position(1, 1, 11, 20)])
    artifact = manager.to_artifact(
        job_id="job-test",
        video_id="video-test",
        fps=30,
        frame_count=1,
        processed_frame_count=1,
        frame_stride=1,
    )
    payload = artifact.model_dump(mode="json")

    assert payload["court"]["court_unit"] == "m"
    assert payload["court"]["canonical"] == {"width": 6.1, "length": 13.41, "unit": "m"}
    assert payload["court"]["imperial_reference"] == {"width": 20.0, "length": 44.0, "unit": "ft"}
    assert payload["players"]["Player_1"][0]["court_x"] == pytest.approx(feet_to_meters(10))
    assert payload["players"]["Player_1"][0]["smoothed_court_x"] is not None
    assert payload["states"]["Player_1"]["history_track_ids"] == [1]


def test_identity_reuses_existing_track_binding():
    manager = PlayerIdentityManager()

    first = manager.update(0, [position(1, 0, 10, 20)])
    second = manager.update(1, [position(1, 1, 10.5, 20.5)])

    assert first[0].player_id == "Player_1"
    assert second[0].player_id == "Player_1"
    assert len(manager.players) == 1


def test_identity_reconnects_new_track_to_existing_player_after_slots_are_full():
    manager = PlayerIdentityManager(
        PlayerIdentityConfig(
            max_players=1,
            fps=30,
            match_threshold=0.4,
            max_reconnect_distance_m=2.5,
            max_speed_mps=7.0,
        )
    )

    manager.update(0, [position(1, 0, 10, 20, timestamp=0.0)])
    manager.update(1, [], eligible_track_ids=set())
    samples = manager.update(2, [position(2, 2, 10.2, 20.2, timestamp=2.0)])

    assert samples[-1].player_id == "Player_1"
    assert manager.track_to_player[2] == "Player_1"
    assert manager.players["Player_1"].history_track_ids == {1, 2}
    assert any(diagnostic.event == "reconnected" for diagnostic in manager.diagnostics)


def test_identity_enforces_four_player_cap_and_records_unmatched():
    manager = PlayerIdentityManager(
        PlayerIdentityConfig(max_players=4, match_threshold=0.99, max_reconnect_distance_m=0.1)
    )

    manager.update(
        0,
        [
            position(1, 0, 1, 1),
            position(2, 0, 5, 1),
            position(3, 0, 10, 20),
            position(4, 0, 15, 20),
        ],
    )
    samples = manager.update(1, [position(5, 1, 100, 100)])

    assert samples == []
    assert len(manager.players) == 4
    assert 5 not in manager.track_to_player
    assert any(diagnostic.event in {"filtered", "unmatched"} and diagnostic.track_id == 5 for diagnostic in manager.diagnostics)


def test_identity_updates_lost_and_inactive_statuses():
    manager = PlayerIdentityManager(PlayerIdentityConfig(lost_buffer_frames=2, inactive_buffer_frames=4))

    manager.update(0, [position(1, 0, 10, 20)])
    manager.update(1, [])
    assert manager.players["Player_1"].status == "lost"
    manager.update(3, [])
    assert manager.players["Player_1"].status == "inactive"


def test_identity_interpolates_short_gap_and_skips_long_gap():
    manager = PlayerIdentityManager(PlayerIdentityConfig(max_players=1, interpolation_buffer_frames=3))

    manager.update(0, [position(1, 0, 10, 20, timestamp=0.0)])
    short_gap = manager.update(2, [position(1, 2, 12, 20, timestamp=2.0)])
    assert [sample.frame_index for sample in short_gap if sample.is_interpolated] == [1]
    assert short_gap[0].tracking_status == "interpolated"

    manager.update(10, [position(1, 10, 13, 20, timestamp=10.0)])
    player_samples = manager.players["Player_1"].trajectory
    assert not any(sample.is_interpolated and sample.frame_index in {3, 4, 5, 6, 7, 8, 9} for sample in player_samples)


def test_metric_bounds_use_meters_not_feet():
    manager = PlayerIdentityManager()

    assert manager._in_metric_bounds([PICKLEBALL_COURT_WIDTH_M, PICKLEBALL_COURT_LENGTH_M])
    assert not manager._in_metric_bounds([44.0, 20.0])


def test_projected_track_points_can_be_exported_in_feet_for_legacy_metrics():
    manager = PlayerIdentityManager()
    manager.update(0, [position(1, 0, 10, 20)])

    points = manager.to_projected_track_points(output_court_unit="ft")

    assert points[0].track_id == "Player_1"
    assert points[0].court_point.x == pytest.approx(10)
    assert points[0].court_point.y == pytest.approx(20)


def test_projected_track_points_preserve_tolerated_boundary_observations():
    manager = PlayerIdentityManager()
    manager.update(0, [position(1, 0, 10, 44.2195)])

    points = manager.to_projected_track_points(output_court_unit="ft")

    assert points[0].track_id == "Player_1"
    assert points[0].court_point.x == pytest.approx(10)
    assert points[0].court_point.y == pytest.approx(44.2195)


def test_player_trajectory_artifact_schema_accepts_empty_players():
    artifact = PlayerTrajectoryArtifact(job_id="job-empty")

    assert artifact.court.court_unit == "m"
    assert artifact.players == {}


def test_identity_filters_non_target_court_tracks_from_eligible_set():
    manager = PlayerIdentityManager()

    samples = manager.update(
        0,
        [position(1, 0, 10, 20), position(2, 0, 35, 20)],
        eligible_track_ids={1},
    )

    assert [sample.track_id for sample in samples] == [1]
    assert 2 not in manager.track_to_player
    assert any(
        diagnostic.event == "filtered"
        and diagnostic.track_id == 2
        and diagnostic.reason == "not target-court eligible"
        for diagnostic in manager.diagnostics
    )
