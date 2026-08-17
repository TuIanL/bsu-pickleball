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


# ---------- fix-multiview-player-identity D3：bootstrap 近端大尺寸候选接纳 ----------


def test_bootstrap_near_large_candidate_preferred_over_center_closest_far():
    """近端右路大 bbox 候选优先于画面中心近的远端候选（不被中心距离排序抢占）。"""
    manager = PlayerLockManager(_doubles_config())
    # 近端右路（near_right）：bbox 大（画面近端）、court (15, 5)
    near_large_bbox = [900, 380, 1280, 700]  # 面积 380*320=121600 px²，中心 (1090, 540)
    # 远端候选（far_left）：bbox 小、court (5, 39)、中心靠近画面中央
    far_small_bbox = [560, 280, 720, 400]  # 面积 160*120=19200 px²，中心 (640, 340)
    for frame in range(10):
        manager.update(
            frame,
            positions=[
                pos(301, frame, 15.0, 5.0, bbox=near_large_bbox),
                pos(302, frame, 5.0, 39.0, bbox=far_small_bbox),
            ],
            frame_width=1280,
            frame_height=720,
        )
    # 近端右路大候选应锁定到 Player_2（near_right 槽位）
    assert manager.slots["Player_2"].current_track_id == 301
    assert manager.slots["Player_2"].home_quadrant == "near_right"


def test_bootstrap_accepts_near_large_player_outside_tracking_area():
    """近端大尺寸高清晰候选在 is_inside_tracking_area=False 时仍可被接纳（D3 放宽）。"""
    manager = PlayerLockManager(
        _doubles_config(
            target_player_count=1,
            near_side_quota=1,
            far_side_quota=0,
        )
    )
    # 近端大 bbox，脚点 court y=5（近端），但 is_inside_tracking_area=False
    near_large_bbox = [880, 360, 1280, 700]  # 面积 400*340=136000 px²
    for frame in range(10):
        manager.update(
            frame,
            positions=[
                pos(
                    310,
                    frame,
                    15.0,
                    5.0,
                    confidence=0.9,
                    bbox=near_large_bbox,
                    is_inside_tracking_area=False,
                    projection_status="outside_tracking_area",
                )
            ],
            frame_width=1280,
            frame_height=720,
        )
    slot = manager.slots["Player_1"]
    assert slot.current_track_id == 310


def test_bootstrap_does_not_accept_near_large_low_conf_or_far():
    """近端但低置信度、或远端的候选不因大 bbox 放宽而被接纳。"""
    manager = PlayerLockManager(
        _doubles_config(
            target_player_count=1,
            near_side_quota=1,
            far_side_quota=0,
        )
    )
    near_large_bbox = [880, 360, 1280, 700]  # 面积 400*340=136000 px²
    for frame in range(10):
        manager.update(
            frame,
            positions=[
                # 近端大 bbox 但低置信度 → 不接纳
                pos(320, frame, 15.0, 5.0, confidence=0.05, bbox=near_large_bbox),
                # 远端大 bbox（court y=39 远侧）→ 不接纳（D3 仅放宽近端）
                pos(321, frame, 15.0, 39.0, confidence=0.9, bbox=near_large_bbox),
            ],
            frame_width=1280,
            frame_height=720,
        )
    assert manager.slots["Player_1"].current_track_id is None


def test_bootstrap_rejects_referee_center_court():
    """画面中央的裁判（court_position 有效但站在网线附近/场外）不被锁定。"""
    manager = PlayerLockManager(_doubles_config())
    # 裁判：court (10, 22)（网线中央）→ inferred_side 落在 SIDE_DEAD_ZONE → 无象限
    for frame in range(10):
        manager.update(frame, positions=[pos(330, frame, 10.0, 22.0)])
    # 网线中央候选无象限归属 → 不进入任何槽位（第二遍仅填"未知象限"候选到 searching 槽位，
    # 但 22ft 处于 dead zone 且未被 _infer_quadrant 识别，home_quadrant 为 None）
    assert manager.slots["Player_1"].home_quadrant is None or manager.slots["Player_1"].state == "searching"


# ---------- fix-multiview-player-identity D4/D5：reconnect 同侧约束 + 互换防护 ----------


def test_reconnect_cross_side_candidate_rejected_keeps_lost():
    """P1（near_left）LOST + far 侧候选 → 候选不被 P1 跨侧重连，P1 保持 LOST，无 reconnected 事件。"""
    manager = _lock_p1_near_left_for_reconnect(reconnect_threshold=0.0)  # 阈值放宽也绝不跨侧
    update = manager.update(20, positions=[pos(200, 20, 5.0, 39.0)])

    slot = manager.slots["Player_1"]
    assert slot.state == "lost"
    assert slot.current_track_id is None
    # far 候选不得被 near_left 的 P1 重连（可能被其他 searching 槽位接管，那是 Phase 3 填充语义）
    assert update.track_identity_hints.get(200) != "Player_1"
    assert not any(d.event == "player_reconnected_from_lost" for d in update.diagnostics)


def test_reconnect_cross_side_candidate_with_high_score_still_rejected():
    """跨侧候选即使 position/motion/bbox 分数极高，也不得重连到 P1（D4 硬约束）。"""
    manager = _lock_p1_near_left_for_reconnect(reconnect_threshold=0.0)
    # far 侧 (5, 39) 且 bbox 外观与 P1 历史 bbox 完全一致（aspect 1.0）→ 分数会很高，仍须拒绝
    update = manager.update(20, positions=[pos(200, 20, 5.0, 39.0, bbox=[200, 200, 400, 300])])

    slot = manager.slots["Player_1"]
    assert slot.state == "lost"
    assert slot.current_track_id is None
    assert update.track_identity_hints.get(200) != "Player_1"


def test_reconnect_lateral_mismatch_score_penalized():
    """同侧横向错配（near_left 槽位接 near_right 候选）→ 总分乘惩罚系数，不足以重连。"""
    manager = _lock_p1_near_left_for_reconnect(reconnect_threshold=0.45)
    # near_right (18, 5)：距离 13ft 在 15ft 门内，但横向错配 side_score=0.2 + 总分 ×0.5 惩罚
    update = manager.update(20, positions=[pos(200, 20, 18.0, 5.0)])

    slot = manager.slots["Player_1"]
    assert slot.state == "lost"
    assert update.track_identity_hints.get(200) != "Player_1"


def test_reconnect_same_side_same_lateral_reconnects_normally():
    """同侧同横向（near_left → near_left）候选正常重连，不触发 swap 事件。"""
    manager = _lock_p1_near_left_for_reconnect(reconnect_threshold=0.45)
    update = manager.update(20, positions=[pos(200, 20, 5.2, 5.0)])

    slot = manager.slots["Player_1"]
    assert slot.state == "locked"
    assert slot.current_track_id == 200
    assert update.track_identity_hints.get(200) == "Player_1"
    assert not any(d.event == "identity_swap_suspected" for d in update.diagnostics)


# ---------- fix-multiview-cam1-bootstrap-4player D1：纵向可判即接纳 ----------


def test_is_court_side_decidable():
    """纯函数：y 可判 near/far 为 True，死区/缺失为 False；x 不参与判定。"""
    from app.vision.player_tracking_engine.player_lock_manager import is_court_side_decidable
    from app.vision.courtvision_calibration_engine.court_geometry import standard_court

    court = standard_court()
    assert is_court_side_decidable([31.3, 12.4], court) is True  # x 超界但 y 可判 near
    assert is_court_side_decidable([6.8, 45.3], court) is True  # y 可判 far
    assert is_court_side_decidable([10.0, 22.0], court) is False  # y 死区（网线中央）
    assert is_court_side_decidable(None, court) is False
    assert is_court_side_decidable([5.0], court) is False  # 长度不足


def test_bootstrap_accepts_x_out_of_bounds_candidate():
    """x 超 tracking bounds 但纵向可判的第 4 人候选被 bootstrap 收集（D1）。"""
    manager = PlayerLockManager(_doubles_config())
    # 构造 4 名球员：3 个正常 + 1 个远端右（court x=31.3 超 tracking 上界 24，y=12.4 可判）
    candidates = [
        (101, 6.8, 45.3, [642, 445, 820, 787]),   # 近端左 far_left
        (102, 14.9, 47.6, [1224, 492, 1348, 905]),  # 近端右 far_right
        (103, 4.5, 9.8, [788, 87, 870, 208]),     # 远端中 near_left
        (104, 31.3, 12.4, [1520, 104, 1579, 227]),  # 远端右 x 超界 → near_right
    ]
    for frame in range(10):
        manager.update(
            frame,
            positions=[
                pos(tid, frame, x, y, bbox=b, is_inside_tracking_area=(x <= 24))
                for tid, x, y, b in candidates
            ],
            frame_width=1920,
            frame_height=1080,
        )
    # 4 个候选全部被收集（含 x 超界的 track 104）
    assert 104 in manager._bootstrap_tracklets
    # 4 槽位全部锁定：x 超界候选经纵向可判接纳 + 图像位置松弛映射锁到 Player_2
    locked = {slot.identity_id: slot.current_track_id for slot in manager.slots.values() if slot.state == "locked"}
    assert locked == {
        "Player_1": 103,  # near_left
        "Player_2": 104,  # near_right（x 超界候选）
        "Player_3": 101,  # far_left
        "Player_4": 102,  # far_right
    }


def test_bootstrap_rejects_side_deadzone_and_missing_bbox():
    """D1 不破坏既有过滤：y 死区 / court_position 缺失候选仍被拒绝。"""
    from app.schemas.tracking import PlayerFramePosition

    manager = PlayerLockManager(_doubles_config())
    # y 死区候选（网线中央 22ft）不被收集
    for frame in range(10):
        manager.update(frame, positions=[pos(301, frame, 10.0, 22.0)])
    assert manager.slots["Player_1"].state == "searching"

    # court_position 缺失候选不被收集（直接构造 None）
    manager2 = PlayerLockManager(_doubles_config())
    no_court = PlayerFramePosition(
        frame_index=0, timestamp=0.0, track_id=401,
        bbox=[100, 100, 200, 300], image_footpoint=[150, 300],
        court_position=None, confidence=0.9, is_inside_tracking_area=True,
    )
    assert manager2._is_identity_candidate(no_court, stage="bootstrap") is False


# ---------- fix-multiview-cam1-bootstrap-4player D2：图像位置松弛映射 ----------


def test_infer_quadrant_image_position_fallback_for_x_deadzone():
    """D2：court x 落在半场死区无法判 left/right 时，用图像 bbox 中心推断。"""
    manager = PlayerLockManager(_doubles_config())
    manager._frame_width = 1920  # 模拟 update 时记录的画面宽度
    manager._frame_height = 1080
    # court x=10.5 在 half_width(10)±dead_zone(2) 内 → inferred_lateral=None
    # 图像 bbox 中心 x=1286 > 画面宽度 1920 的 50% → right
    tl = manager._bootstrap_tracklets.setdefault(
        501,
        __import__("app.vision.player_tracking_engine.player_lock_manager", fromlist=["_BootstrapTracklet"])._BootstrapTracklet(),
    )
    tl.frame_indices = [0, 1, 2]
    tl.confidences = [0.9, 0.9, 0.9]
    tl.court_xs = [10.5, 10.5, 10.5]
    tl.court_ys = [5.0, 5.0, 5.0]
    tl.bbox_centers = [(1200.0, 600.0), (1286.0, 600.0), (1300.0, 600.0)]
    quadrant = manager._infer_quadrant(tl)
    assert quadrant == "near_right"

    # 图像中心偏左 → near_left
    tl2 = manager._bootstrap_tracklets.setdefault(
        502,
        __import__("app.vision.player_tracking_engine.player_lock_manager", fromlist=["_BootstrapTracklet"])._BootstrapTracklet(),
    )
    tl2.frame_indices = [0, 1, 2]
    tl2.confidences = [0.9, 0.9, 0.9]
    tl2.court_xs = [10.5, 10.5, 10.5]
    tl2.court_ys = [5.0, 5.0, 5.0]
    tl2.bbox_centers = [(300.0, 600.0), (400.0, 600.0), (350.0, 600.0)]
    assert manager._infer_quadrant(tl2) == "near_left"


def test_infer_quadrant_court_projection_priority():
    """D2：正常投影（x 在界内）优先用 court 投影，不走图像松弛映射。"""
    manager = PlayerLockManager(_doubles_config())
    tl = manager._bootstrap_tracklets.setdefault(
        601,
        __import__("app.vision.player_tracking_engine.player_lock_manager", fromlist=["_BootstrapTracklet"])._BootstrapTracklet(),
    )
    tl.frame_indices = [0, 1, 2]
    tl.confidences = [0.9, 0.9, 0.9]
    tl.court_xs = [6.8, 6.8, 6.8]
    tl.court_ys = [45.3, 45.3, 45.3]
    tl.bbox_centers = [(1500.0, 600.0), (1500.0, 600.0), (1500.0, 600.0)]  # 图像偏右
    # court x=6.8 < 10 → left，正常投影优先（即使图像偏右也不改）
    assert manager._infer_quadrant(tl) == "far_left"


# ---------- fix-multiview-cam1-bootstrap-4player D5：slot_unfilled ----------


def test_bootstrap_all_four_slots_locked_no_unfilled_event():
    """4 名球员（含 x 超界候选）→ bootstrap 结束后 4 槽位全锁定，无 slot_unfilled。"""
    manager = PlayerLockManager(_doubles_config())
    candidates = [
        (701, 6.8, 45.3, [642, 445, 820, 787]),
        (702, 14.9, 47.6, [1224, 492, 1348, 905]),
        (703, 4.5, 9.8, [788, 87, 870, 208]),
        (704, 31.3, 12.4, [1520, 104, 1579, 227]),
    ]
    last_update = None
    for frame in range(20):  # 超过 bootstrap_max_frames=20 触发 finalize
        last_update = manager.update(
            frame,
            positions=[pos(tid, frame, x, y, bbox=b, is_inside_tracking_area=(x <= 24)) for tid, x, y, b in candidates],
            frame_width=1920,
            frame_height=1080,
        )
    locked = {slot.identity_id: slot.current_track_id for slot in manager.slots.values() if slot.state == "locked"}
    assert len(locked) == 4
    assert not any(d.event == "slot_unfilled" for d in last_update.diagnostics)


def test_bootstrap_three_players_one_referee_slot_unfilled():
    """仅 3 名球员 + 1 个裁判（y 死区）→ Player_2 保持 searching 且产出 slot_unfilled。"""
    manager = PlayerLockManager(_doubles_config())
    # 3 名球员 + 裁判（网线中央 y=22，y 死区不接纳）
    candidates = [
        (801, 6.8, 45.3, [642, 445, 820, 787]),   # far_left
        (802, 14.9, 47.6, [1224, 492, 1348, 905]),  # far_right
        (803, 4.5, 9.8, [788, 87, 870, 208]),     # near_left
        (890, 10.0, 22.0, [900, 400, 1000, 700]),  # 裁判：y 死区
    ]
    unfilled_events = []
    for frame in range(25):
        update = manager.update(
            frame,
            positions=[pos(tid, frame, x, y, bbox=b) for tid, x, y, b in candidates],
            frame_width=1920,
            frame_height=1080,
        )
        unfilled_events.extend(d for d in update.diagnostics if d.event == "slot_unfilled")
    # Player_2（near_right）无候选 → searching，产出 slot_unfilled
    assert manager.slots["Player_2"].state == "searching"
    assert any("Player_2" in d.player_id for d in unfilled_events)
    # 裁判（890）不得锁定到任何槽位
    assert 890 not in {slot.current_track_id for slot in manager.slots.values()}
    # 已锁定槽位不受影响
    assert manager.slots["Player_1"].state == "locked"


def test_bootstrap_persistence_beats_center_distance_for_same_quadrant():
    """fix-multiview-cam1-bootstrap-4player D1 修正：同象限内持续出现的稳定候选
    优先于更靠画面中心的短暂候选（短 track 不得抢占球员槽位）。"""
    manager = PlayerLockManager(_doubles_config())
    # near_left 象限两个候选：
    # - track 901：稳定（全程出现），court (6.8, 45.3)，bbox 中心偏画面右侧（距中心远）
    # - track 902：短暂（仅前 3 帧出现），court (6.0, 45.0)，bbox 中心在画面中央（距中心近）
    stable_bbox = [1200, 300, 1300, 700]   # 中心 (1250, 500) → 距画面中心 (640,360) 约 620px
    brief_bbox = [560, 300, 720, 500]      # 中心 (640, 400) → 距画面中心约 40px
    for frame in range(12):
        positions = [pos(901, frame, 6.8, 45.3, bbox=stable_bbox)]
        if frame < 3:
            positions.append(pos(902, frame, 6.0, 45.0, bbox=brief_bbox))
        manager.update(frame, positions=positions, frame_width=1280, frame_height=720)
    # 稳定 track 901 优先锁定到 far_left（Player_3），短暂 track 902 不得抢占
    assert manager.slots["Player_3"].current_track_id == 901
    assert 902 not in {slot.current_track_id for slot in manager.slots.values()}
