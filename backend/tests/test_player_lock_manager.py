"""球员锁定管理器测试 —— bootstrap 中心优先+象限唯一、硬锁到底、重连保持身份。"""

import pytest

from app.schemas.tracking import PlayerFramePosition
from app.vision.player_tracking_engine.player_lock_manager import PlayerLockManager
from app.vision.player_tracking_engine.player_lock_types import PlayerLockConfig


def pos(track_id, frame, x_ft, y_ft, confidence=0.9, bbox=None):
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
        valid=True,
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
        (101, 5.0, 5.0),   # near_left
        (102, 15.0, 5.0),  # near_right
        (103, 5.0, 39.0),  # far_left
        (104, 15.0, 39.0),  # far_right
    ]
    for frame in range(10):
        manager.update(frame, positions=[pos(tid, frame, x, y) for tid, x, y in candidates])

    locked = {slot.identity_id: slot.current_track_id for slot in manager.slots.values() if slot.state == "locked"}
    assert locked == {"Player_1": 101, "Player_2": 102, "Player_3": 103, "Player_4": 104}


def test_bootstrap_does_not_steal_other_quadrant_slot():
    # 只有近左候选 → 只锁 Player_1，Player_2（近右）不被抢占
    manager = PlayerLockManager(_doubles_config())
    for frame in range(10):
        manager.update(frame, positions=[pos(101, frame, 5.0, 5.0)])

    assert manager.slots["Player_1"].current_track_id == 101
    assert manager.slots["Player_2"].state == "searching"


def test_bootstrap_same_quadrant_picks_center_closest():
    # 同一象限（近左）两个候选：track 201 更靠近画面中心，应被优先锁定
    manager = PlayerLockManager(_doubles_config())
    center_bbox = [480, 200, 560, 400]  # bbox 中心 (520, 300) → 距画面中心 (640, 360) 约 134px
    edge_bbox = [120, 200, 200, 400]    # bbox 中心 (160, 300) → 距画面中心约 484px
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
