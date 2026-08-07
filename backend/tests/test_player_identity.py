import pytest

from app.schemas.tracking import (
    PlayerFramePosition,
    PlayerIdentityDiagnostic,
    PlayerTrajectoryArtifact,
    PlayerTrajectorySample,
    PlayerTrajectoryState,
)
from app.vision.courtvision_calibration_engine.court_units import (
    PICKLEBALL_COURT_LENGTH_M,
    PICKLEBALL_COURT_WIDTH_M,
    feet_to_meters,
)
from app.vision.player_tracking_engine.player_identity import PlayerIdentityConfig, PlayerIdentityManager
from app.vision.player_tracking_engine.player_lock_manager import PlayerLockManager
from app.vision.player_tracking_engine.player_lock_types import PlayerLockConfig


def position(
    track_id,
    frame,
    x_ft,
    y_ft,
    timestamp=None,
    valid=True,
    projection_status="inside_court",
    is_inside_tracking_area=True,
):
    return PlayerFramePosition(
        frame_index=frame,
        timestamp=float(frame if timestamp is None else timestamp),
        track_id=track_id,
        bbox=[x_ft, y_ft, x_ft + 1, y_ft + 2],
        image_footpoint=[x_ft + 0.5, y_ft + 2],
        court_position=[x_ft, y_ft],
        court_unit="ft",
        confidence=0.9,
        valid=valid,
        projection_status=projection_status,
        is_inside_tracking_area=is_inside_tracking_area,
    )


@pytest.mark.parametrize(
    "event",
    [
        "side_quota_fallback_replaced",
        "fallback_tentative_promoted",
        "player_reconnected_after_track_change",
    ],
)
def test_player_identity_diagnostic_accepts_lock_manager_events(event):
    diagnostic = PlayerIdentityDiagnostic(
        frame_index=0,
        event=event,
        reason="test",
    )

    assert diagnostic.event == event


def test_player_trajectory_artifact_serializes_metric_metadata_and_track_history():
    manager = PlayerIdentityManager(PlayerIdentityConfig(smoothing_window=3))

    manager.update(0, [position(1, 0, 10, 20)], track_identity_hints={1: "Player_1"})
    manager.update(1, [position(1, 1, 11, 20)], track_identity_hints={1: "Player_1"})
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


def test_identity_consumes_canonical_lock_hints_and_reuses_binding():
    manager = PlayerIdentityManager()

    first = manager.update(0, [position(1, 0, 10, 20)], track_identity_hints={1: "Player_1"})
    second = manager.update(1, [position(1, 1, 10.5, 20.5)], track_identity_hints={1: "Player_1"})

    assert first[0].player_id == "Player_1"
    assert second[0].player_id == "Player_1"
    assert len(manager.players) == 1
    assert manager.track_to_player[1] == "Player_1"


def test_identity_binds_lost_slot_new_track_to_same_player_via_hint():
    manager = PlayerIdentityManager(PlayerIdentityConfig(max_players=1))

    manager.update(0, [position(1, 0, 10, 20)], track_identity_hints={1: "Player_1"})
    manager.update(1, [], eligible_track_ids=set())
    # 锁定层重连：新的 source track 仍发 hint 到 Player_1（LOST 槽位身份保留）
    samples = manager.update(2, [position(2, 2, 10.2, 20.2)], track_identity_hints={2: "Player_1"})

    assert samples[-1].player_id == "Player_1"
    assert manager.track_to_player[2] == "Player_1"
    assert manager.players["Player_1"].history_track_ids == {1, 2}


def test_identity_hint_wins_when_old_mapped_track_shares_slot_in_same_frame():
    manager = PlayerIdentityManager(PlayerIdentityConfig(max_players=1))

    manager.update(0, [position(1, 0, 10, 20)], track_identity_hints={1: "Player_1"})
    samples = manager.update(
        1,
        [position(1, 1, 10.1, 20.0), position(2, 1, 10.2, 20.0)],
        eligible_track_ids={1, 2},
        track_identity_hints={2: "Player_1"},
    )

    detected = [sample for sample in samples if sample.frame_index == 1 and not sample.is_interpolated]
    assert len(detected) == 1
    assert detected[0].track_id == 2
    assert detected[0].player_id == "Player_1"
    assert any(
        diagnostic.event == "filtered"
        and diagnostic.track_id == 1
        and diagnostic.reason == "player slot already assigned by higher-priority track in this frame"
        for diagnostic in manager.diagnostics
    )


def test_lock_recovery_contract_preserves_player_id_and_eligibility():
    lock_manager = PlayerLockManager(
        PlayerLockConfig(
            target_player_count=1,
            near_side_quota=1,
            far_side_quota=0,
            bootstrap_min_frames=3,
            bootstrap_max_frames=20,
            min_observed_frames=3,
            lock_min_hits=3,
            reconnect_threshold=0.45,
        )
    )
    identity_manager = PlayerIdentityManager(PlayerIdentityConfig(max_players=1))

    for frame in range(8):
        observed = [position(100, frame, 10, 20)]
        lock_update = lock_manager.update(frame, observed)
        identity_manager.update(
            frame,
            observed,
            eligible_track_ids=lock_update.eligible_track_ids,
            track_identity_hints=lock_update.track_identity_hints,
        )

    recovered_position = position(200, 8, 10.1, 20.0)
    lock_update = lock_manager.update(8, [recovered_position])
    samples = identity_manager.update(
        8,
        [recovered_position],
        eligible_track_ids=lock_update.eligible_track_ids,
        track_identity_hints=lock_update.track_identity_hints,
    )

    assert samples[-1].player_id == "Player_1"
    assert samples[-1].track_id == 200
    assert identity_manager.players["Player_1"].history_track_ids == {100, 200}
    assert any(d.event == "player_reconnected_after_track_change" for d in lock_update.diagnostics)

    filtered = identity_manager.update(
        9,
        [position(300, 9, 10.2, 20.0)],
        eligible_track_ids=set(),
        track_identity_hints={},
    )
    assert filtered == []
    assert any(
        d.event == "filtered" and d.track_id == 300 and d.reason == "not target-court eligible"
        for d in identity_manager.diagnostics
    )


def test_identity_does_not_create_identity_without_hint():
    manager = PlayerIdentityManager(PlayerIdentityConfig(max_players=4))

    samples = manager.update(0, [position(5, 0, 10, 20)])

    assert samples == []
    assert 5 not in manager.track_to_player
    assert len(manager.players) == 0
    assert any(diagnostic.event == "unmatched" and diagnostic.track_id == 5 for diagnostic in manager.diagnostics)


def test_identity_never_creates_identity_beyond_locked_slots():
    manager = PlayerIdentityManager(PlayerIdentityConfig(max_players=4))

    manager.update(
        0,
        [
            position(1, 0, 1, 1),
            position(2, 0, 5, 1),
            position(3, 0, 10, 20),
            position(4, 0, 15, 20),
        ],
        track_identity_hints={1: "Player_1", 2: "Player_2", 3: "Player_3", 4: "Player_4"},
    )
    samples = manager.update(1, [position(5, 1, 100, 100)])

    assert samples == []
    assert len(manager.players) == 4
    assert 5 not in manager.track_to_player
    assert any(
        diagnostic.event in {"filtered", "unmatched"} and diagnostic.track_id == 5 for diagnostic in manager.diagnostics
    )


def test_identity_updates_lost_and_inactive_statuses():
    manager = PlayerIdentityManager(PlayerIdentityConfig(lost_buffer_frames=2, inactive_buffer_frames=4))

    manager.update(0, [position(1, 0, 10, 20)], track_identity_hints={1: "Player_1"})
    manager.update(1, [])
    assert manager.players["Player_1"].status == "lost"
    manager.update(3, [])
    assert manager.players["Player_1"].status == "inactive"


def test_identity_interpolates_short_gap_and_skips_long_gap():
    manager = PlayerIdentityManager(PlayerIdentityConfig(max_players=1, interpolation_buffer_frames=3))

    manager.update(0, [position(1, 0, 10, 20, timestamp=0.0)], track_identity_hints={1: "Player_1"})
    short_gap = manager.update(2, [position(1, 2, 12, 20, timestamp=2.0)], track_identity_hints={1: "Player_1"})
    assert [sample.frame_index for sample in short_gap if sample.is_interpolated] == [1]
    assert short_gap[0].tracking_status == "interpolated"

    manager.update(10, [position(1, 10, 13, 20, timestamp=10.0)], track_identity_hints={1: "Player_1"})
    player_samples = manager.players["Player_1"].trajectory
    assert not any(sample.is_interpolated and sample.frame_index in {3, 4, 5, 6, 7, 8, 9} for sample in player_samples)


def test_metric_bounds_use_meters_not_feet():
    manager = PlayerIdentityManager()

    assert manager._in_metric_bounds([PICKLEBALL_COURT_WIDTH_M, PICKLEBALL_COURT_LENGTH_M])
    assert not manager._in_metric_bounds([44.0, 20.0])


def test_projected_track_points_can_be_exported_in_feet_for_legacy_metrics():
    manager = PlayerIdentityManager()
    manager.update(0, [position(1, 0, 10, 20)], track_identity_hints={1: "Player_1"})

    points = manager.to_projected_track_points(output_court_unit="ft")

    assert points[0].track_id == "Player_1"
    assert points[0].court_point.x == pytest.approx(10)
    assert points[0].court_point.y == pytest.approx(20)


def test_projected_track_points_preserve_tolerated_boundary_observations():
    manager = PlayerIdentityManager()
    manager.update(0, [position(1, 0, 10, 44.2195)], track_identity_hints={1: "Player_1"})

    points = manager.to_projected_track_points(output_court_unit="ft")

    assert points[0].track_id == "Player_1"
    assert points[0].court_point.x == pytest.approx(10)
    assert points[0].court_point.y == pytest.approx(44.2195)


def test_identity_preserves_visible_boundary_player_for_overlay_and_trajectory():
    manager = PlayerIdentityManager()
    boundary = position(
        1,
        0,
        10,
        46.5,
        valid=False,
        projection_status="outside_court_visible",
    )

    samples = manager.update(
        0,
        [boundary],
        eligible_track_ids={1},
        track_identity_hints={1: "Player_1"},
    )

    assert samples[-1].player_id == "Player_1"
    assert manager.players["Player_1"].history_track_ids == {1}
    exported = manager.to_projected_track_points(output_court_unit="ft")
    assert exported[-1].court_point.y == pytest.approx(46.5)


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
        track_identity_hints={1: "Player_1"},
    )

    assert [sample.track_id for sample in samples] == [1]
    assert 2 not in manager.track_to_player
    assert any(
        diagnostic.event == "filtered" and diagnostic.track_id == 2 and diagnostic.reason == "not target-court eligible"
        for diagnostic in manager.diagnostics
    )


def test_trajectory_player_id_schema_rejects_non_canonical_and_out_of_range():
    # 对外契约：player_id 只允许 Player_1..Player_4
    PlayerTrajectorySample(frame_index=0, timestamp_seconds=0, player_id="Player_1", court_x=0, court_y=0)
    PlayerTrajectoryState(player_id="Player_4")
    for bad in ("Player_0", "Player_5", "player_1", "164", "T164"):
        with pytest.raises(ValueError):
            PlayerTrajectorySample(frame_index=0, timestamp_seconds=0, player_id=bad, court_x=0, court_y=0)


# ---------- 位置连续性软接管 ----------


def test_identity_soft_takeover_assigns_nearby_unmatched_track_to_nearest_player():
    manager = PlayerIdentityManager(PlayerIdentityConfig(max_players=2))
    # 先锁定 Player_1，使其有最近已知位置
    manager.update(0, [position(1, 0, 10, 20)], track_identity_hints={1: "Player_1"})
    # 新 track 5 无 hint，出现在 Player_1 附近（约 1ft≈0.3m）→ 软接管为 tentative
    samples = manager.update(1, [position(5, 1, 11, 20)])

    assert samples
    assert samples[0].player_id == "Player_1"
    assert samples[0].tracking_status == "tentative"
    assert samples[0].confidence == pytest.approx(min(0.9, 0.45))
    assert manager.track_to_player[5] == "Player_1"
    assert any(d.event == "soft_takeover_assigned" for d in manager.diagnostics)


def test_identity_soft_takeover_keeps_far_track_unmatched():
    manager = PlayerIdentityManager(PlayerIdentityConfig(max_players=2))
    manager.update(0, [position(1, 0, 10, 20)], track_identity_hints={1: "Player_1"})
    # 新 track 5 在球场内但距 Player_1 约 20ft≈6m，超过 4m 阈值 → unmatched
    samples = manager.update(1, [position(5, 1, 15, 40)])

    assert samples == []
    assert 5 not in manager.track_to_player
    assert any(d.event == "unmatched" and d.track_id == 5 for d in manager.diagnostics)


def test_identity_soft_takeover_assigns_only_one_track_per_player_per_frame():
    manager = PlayerIdentityManager(PlayerIdentityConfig(max_players=2))
    manager.update(0, [position(1, 0, 10, 20)], track_identity_hints={1: "Player_1"})
    # 同一帧两条 track 都靠近 Player_1：第一条软接管，第二条 unmatched
    samples = manager.update(1, [position(5, 1, 11, 20), position(6, 1, 12, 20)])

    assert [s.player_id for s in samples] == ["Player_1"]
    assert manager.track_to_player.get(5) == "Player_1"
    assert 6 not in manager.track_to_player
    assert any(d.event == "unmatched" and d.track_id == 6 for d in manager.diagnostics)


def test_identity_lock_hint_takes_precedence_over_soft_takeover():
    manager = PlayerIdentityManager(PlayerIdentityConfig(max_players=2))
    manager.update(0, [position(1, 0, 10, 20)], track_identity_hints={1: "Player_1"})
    # 新 track 7 靠近 Player_1，但 lock 给出 hint 指向 Player_2 → 以 hint 为准
    samples = manager.update(1, [position(7, 1, 11, 20)], track_identity_hints={7: "Player_2"})

    assert samples
    assert samples[0].player_id == "Player_2"
    assert samples[0].tracking_status == "detected"
    assert manager.track_to_player[7] == "Player_2"
