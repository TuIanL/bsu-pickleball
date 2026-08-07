"""球员锁定管理器测试 —— bootstrap 中心优先+象限唯一、硬锁到底、重连保持身份。"""

from app.schemas.tracking import PlayerFramePosition
from app.vision.player_tracking_engine.player_lock_manager import PlayerLockManager
from app.vision.player_tracking_engine.player_lock_types import PlayerLockConfig


def pos(
    track_id,
    frame,
    x_ft,
    y_ft,
    confidence=0.9,
    bbox=None,
    valid=True,
    projection_status="inside_court",
    is_inside_tracking_area=True,
):
    if bbox is None:
        bbox = [x_ft * 20, 100, x_ft * 20 + 60, 260]
    return PlayerFramePosition(
        frame_index=frame,
        timestamp=frame / 30.0,
        track_id=track_id,
        bbox=bbox,
        image_footpoint=[(bbox[0] + bbox[2]) / 2.0, bbox[3]],
        court_position=[x_ft, y_ft],
        court_unit="ft",
        confidence=confidence,
        valid=valid,
        projection_status=projection_status,
        is_inside_tracking_area=is_inside_tracking_area,
    )


def _doubles_config(**overrides):
    defaults = dict(
        fps=30,
        target_player_count=4,
        near_side_quota=2,
        far_side_quota=2,
        bootstrap_min_frames=5,
        bootstrap_max_frames=20,
        min_observed_frames=3,
        lock_min_hits=5,
    )
    defaults.update(overrides)
    return PlayerLockConfig(**defaults)


def test_bootstrap_quadrant_unique_assigns_each_home_slot():
    # 四个象限各一个候选 → 各自锁定到对应槽位（Player_1..4 = 近左/近右/远左/远右）
    manager = PlayerLockManager(_doubles_config())
    candidates = [
        (101, 5.0, 5.0),  # near_left
        (102, 15.0, 5.0),  # near_right
        (103, 5.0, 39.0),  # far_left
        (104, 15.0, 39.0),  # far_right
    ]
    for frame in range(10):
        manager.update(frame, positions=[pos(tid, frame, x, y) for tid, x, y in candidates])

    locked = {slot.identity_id: slot.current_track_id for slot in manager.slots.values() if slot.state == "locked"}
    assert locked == {"Player_1": 101, "Player_2": 102, "Player_3": 103, "Player_4": 104}
    assert manager.slots["Player_1"].home_quadrant == "near_left"
    assert manager.slots["Player_1"].side_hint == "near_left"
    assert manager.slots["Player_2"].home_quadrant == "near_right"
    assert manager.slots["Player_3"].home_quadrant == "far_left"
    assert manager.slots["Player_4"].side_hint == "far_right"


def test_bootstrap_does_not_steal_other_quadrant_slot():
    # 只有近左候选 → 只锁 Player_1，Player_2（近右）不被抢占
    manager = PlayerLockManager(_doubles_config())
    for frame in range(10):
        manager.update(frame, positions=[pos(101, frame, 5.0, 5.0)])

    assert manager.slots["Player_1"].current_track_id == 101
    assert manager.slots["Player_2"].state == "searching"


def test_bootstrap_accepts_visible_boundary_player_inside_tracking_area():
    manager = PlayerLockManager(
        _doubles_config(
            target_player_count=1,
            near_side_quota=1,
            far_side_quota=0,
        )
    )

    def boundary_position(frame):
        return pos(
            105,
            frame,
            10.0,
            -2.5,
            valid=False,
            projection_status="outside_court_visible",
        )

    for frame in range(10):
        manager.update(frame, positions=[boundary_position(frame)])

    slot = manager.slots["Player_1"]
    assert slot.state == "locked"
    assert slot.current_track_id == 105


def test_bootstrap_same_quadrant_picks_center_closest():
    # 同一象限（近左）两个候选：track 201 更靠近画面中心，应被优先锁定
    manager = PlayerLockManager(_doubles_config())
    center_bbox = [480, 200, 560, 400]  # bbox 中心 (520, 300) → 距画面中心 (640, 360) 约 134px
    edge_bbox = [120, 200, 200, 400]  # bbox 中心 (160, 300) → 距画面中心约 484px
    for frame in range(10):
        manager.update(
            frame,
            positions=[
                pos(201, frame, 6.0, 5.0, bbox=center_bbox),
                pos(202, frame, 2.0, 5.0, bbox=edge_bbox),
            ],
            frame_width=1280,
            frame_height=720,
        )

    assert manager.slots["Player_1"].current_track_id == 201


def test_hard_lock_keeps_identity_after_long_loss():
    config = _doubles_config(
        target_player_count=2,
        near_side_quota=1,
        far_side_quota=1,
        lost_grace_frames=2,
        lost_max_frames_locked=5,  # deprecated：不应再触发回退
    )
    manager = PlayerLockManager(config)

    for frame in range(15):
        manager.update(frame, positions=[pos(100, frame, 10.0, 5.0)])
    # 长时间无观测（远超 lost_max_frames_locked）
    last_update = None
    for frame in range(15, 80):
        last_update = manager.update(frame, positions=[], suggestions=[])

    slot = manager.slots["Player_1"]
    assert slot.state == "lost"  # 保持 LOST，不回退 SEARCHING
    assert slot.identity_id == "Player_1"
    assert slot.current_track_id is None
    assert not any(d.event == "player_reset_after_prolonged_loss" for d in last_update.diagnostics)
    # 近侧占用仍保留（LOST 也计占用，身份没被释放）
    assert manager.near_occupancy == 1


def test_hard_lock_reconnects_new_track_to_same_slot():
    config = _doubles_config(
        target_player_count=2,
        near_side_quota=1,
        far_side_quota=1,
        lost_grace_frames=2,
        reconnect_threshold=0.0,  # 放宽阈值确保重连命中
    )
    manager = PlayerLockManager(config)

    for frame in range(15):
        manager.update(frame, positions=[pos(100, frame, 10.0, 5.0)])
    for frame in range(15, 40):
        manager.update(frame, positions=[], suggestions=[])

    update = None
    for frame in range(40, 50):
        update = manager.update(frame, positions=[pos(200, frame, 10.0, 5.0)])

    slot = manager.slots["Player_1"]
    assert slot.state == "locked"
    assert slot.current_track_id == 200
    assert 200 in update.eligible_track_ids
    assert update.track_identity_hints.get(200) == "Player_1"


def _lock_two_slots_for_reconnect(**overrides):
    config = _doubles_config(
        target_player_count=2,
        near_side_quota=1,
        far_side_quota=1,
        lost_grace_frames=2,
        **overrides,
    )
    manager = PlayerLockManager(config)
    for frame in range(15):
        manager.update(
            frame,
            positions=[
                pos(100, frame, 10.0, 5.0),
                pos(101, frame, 10.0, 39.0),
            ],
        )
    assert manager.slots["Player_1"].state == "locked"
    assert manager.slots["Player_2"].state == "locked"
    for frame in range(15, 20):
        manager.update(frame, positions=[])
    assert all(slot.state == "lost" for slot in manager.slots.values())
    return manager


def test_reconnect_competition_assigns_one_slot_per_track():
    manager = _lock_two_slots_for_reconnect(reconnect_threshold=0.25)

    update = manager.update(20, positions=[pos(200, 20, 10.0, 5.0)])

    matching_slots = [slot.identity_id for slot in manager.slots.values() if slot.current_track_id == 200]
    assert len(matching_slots) == 1
    assert len([track_id for track_id in update.track_identity_hints if track_id == 200]) == 1
    assert 200 in update.eligible_track_ids
    assert any(slot.state == "lost" for slot in manager.slots.values())


def test_reconnect_assigns_two_distinct_tracks_to_two_lost_slots():
    manager = _lock_two_slots_for_reconnect(reconnect_threshold=0.45)

    update = manager.update(
        20,
        positions=[
            pos(200, 20, 10.0, 5.0),
            pos(201, 20, 10.0, 39.0),
        ],
    )

    assert manager.slots["Player_1"].current_track_id == 200
    assert manager.slots["Player_2"].current_track_id == 201
    assert update.track_identity_hints == {200: "Player_1", 201: "Player_2"}
    assert update.eligible_track_ids == {200, 201}


def test_locked_slot_recovers_track_change_before_lost_transition():
    config = _doubles_config(
        target_player_count=1,
        near_side_quota=1,
        far_side_quota=0,
        lost_grace_frames=3,
        reconnect_threshold=0.45,
    )
    manager = PlayerLockManager(config)
    for frame in range(15):
        manager.update(frame, positions=[pos(100, frame, 10.0, 5.0)])

    update = manager.update(15, positions=[pos(200, 15, 10.2, 5.0)])

    slot = manager.slots["Player_1"]
    assert slot.state == "locked"
    assert slot.current_track_id == 200
    assert slot.track_id_history == [100, 200]
    assert update.track_identity_hints == {200: "Player_1"}
    assert any(d.event == "player_reconnected_after_track_change" for d in update.diagnostics)


def test_track_history_ownership_prevents_cross_slot_reassignment():
    manager = _lock_two_slots_for_reconnect(reconnect_threshold=0.45)

    # Player_1 changes from 100 to 200 while Player_2 keeps 101. The old
    # source track 100 must remain owned by Player_1 if it reappears later.
    manager.update(
        20,
        positions=[
            pos(200, 20, 10.0, 5.0),
            pos(101, 20, 10.0, 39.0),
        ],
    )
    update = manager.update(
        21,
        positions=[
            pos(200, 21, 10.0, 5.0),
            pos(100, 21, 10.0, 5.0),
        ],
    )

    assert manager.slots["Player_2"].current_track_id == 101
    assert update.track_identity_hints.get(100) != "Player_2"


def _lock_one_slot_for_reconnect(**overrides):
    config = _doubles_config(
        target_player_count=1,
        near_side_quota=1,
        far_side_quota=0,
        lost_grace_frames=2,
        **overrides,
    )
    manager = PlayerLockManager(config)
    for frame in range(15):
        manager.update(frame, positions=[pos(100, frame, 5.0, 5.0)])
    assert manager.slots["Player_1"].state == "locked"
    for frame in range(15, 20):
        manager.update(frame, positions=[], suggestions=[])
    assert manager.slots["Player_1"].state == "lost"
    return manager


def _lock_p1_near_left_for_reconnect(**overrides):
    config = _doubles_config(
        target_player_count=4,
        near_side_quota=2,
        far_side_quota=2,
        lost_grace_frames=2,
        **overrides,
    )
    manager = PlayerLockManager(config)
    # 只给一个近左候选 → bootstrap 锁到 Player_1（近左）
    for frame in range(15):
        manager.update(frame, positions=[pos(100, frame, 5.0, 5.0)])
    slot = manager.slots["Player_1"]
    assert slot.state == "locked", slot.state
    assert slot.home_quadrant == "near_left", slot.home_quadrant
    for frame in range(15, 20):
        manager.update(frame, positions=[], suggestions=[])
    assert slot.state == "lost"
    return manager


def test_reconnect_distance_gate_rejects_far_candidate():
    # P1 锁定在近左 (5,5)；候选在 (25,5) 距离 20ft > 15ft 硬门 → 拒绝，保持 LOST
    manager = _lock_one_slot_for_reconnect(reconnect_threshold=0.0)  # 即使阈值放宽也不应重连
    update = manager.update(20, positions=[pos(200, 20, 25.0, 5.0)])

    slot = manager.slots["Player_1"]
    assert slot.state == "lost"
    assert slot.current_track_id is None
    assert update.track_identity_hints.get(200) is None
    assert 200 not in update.eligible_track_ids


def test_reconnect_distance_gate_accepts_near_candidate():
    # P1 锁定在近左 (5,5)；候选在 (5.2,5.0) 距离极小 → 正常重连
    manager = _lock_one_slot_for_reconnect(reconnect_threshold=0.45)
    update = manager.update(20, positions=[pos(200, 20, 5.2, 5.0)])

    slot = manager.slots["Player_1"]
    assert slot.state == "locked"
    assert slot.current_track_id == 200
    assert update.track_identity_hints.get(200) == "Player_1"


def test_reconnect_lateral_mismatch_alone_cannot_reach_threshold():
    # P1（双打）锁定在近左 (5,5)；候选在近右 (18,5) 距离 13ft 在门内，但横向错配侧分仅 0.2
    manager = _lock_p1_near_left_for_reconnect(reconnect_threshold=0.45)
    update = manager.update(20, positions=[pos(200, 20, 18.0, 5.0)])

    slot = manager.slots["Player_1"]
    assert slot.state == "lost"
    assert slot.current_track_id is None
    # 近右候选不能被错配给近左的 P1（可归近右槽位 Player_2，但不能顶替 P1）
    assert update.track_identity_hints.get(200) != "Player_1"
