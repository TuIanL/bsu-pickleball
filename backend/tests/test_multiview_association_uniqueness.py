"""fix-multiview-cam1-bootstrap-4player D3/D4：reference view 槽位唯一性测试。

覆盖：
- registry.set_binding 对 reference 槽位冲突返回 False（不覆盖 incumbent）
- GlobalPlayerAssociator 冲突路径记录 reference_slot_conflict（不直接覆盖）
- 冲突事件可观测（reference_slot_conflicts 计数 + last_reference_slot_conflict）
"""

from __future__ import annotations

from app.vision.multiview.association_global import GlobalPlayerAssociator
from app.vision.multiview.court_frame import CourtOrientation
from app.vision.multiview.global_state import GlobalPlayerRegistry, ViewBinding
from test_global_roster import _obs, _seed_roster

IDENTITY = CourtOrientation.identity


def _binding(view_player_id: str, track_id: int) -> ViewBinding:
    return ViewBinding(
        view_player_id=view_player_id,
        local_identity_epoch=0,
        track_id=track_id,
        last_seen_take_timestamp_ms=0.0,
        last_source_frame_index=0,
        quality=0.9,
        visibility="observed",
    )


def test_set_binding_rejects_reference_slot_conflict():
    """D3：reference view 槽位已被其他 global 占用时 set_binding 返回 False。"""
    reg = GlobalPlayerRegistry(reference_view_id="cam_1")
    # gid_1 先绑定 cam_1 Player_1（晋升为 provisional occupant）
    assert reg.set_binding("global_player_1", "cam_1", _binding("Player_1", 3), 0.0) is True
    reg.players["global_player_1"].roster_status = "provisional"
    assert reg.reference_slot_occupant("cam_1", "Player_1") == "global_player_1"
    # gid_3 尝试绑定同一 reference 槽位 → 冲突，返回 False，不覆盖
    assert reg.set_binding("global_player_3", "cam_1", _binding("Player_1", 100), 0.0) is False
    assert reg.reference_slot_occupant("cam_1", "Player_1") == "global_player_1"
    assert reg.reference_slot_conflicts.get(("cam_1", "Player_1")) == 1
    assert reg.last_reference_slot_conflict == ("cam_1", "Player_1", "global_player_1", "global_player_3")


def test_set_binding_allows_same_global_refresh_and_other_views():
    """D3：同 global 刷新自身 binding / 不同槽位不受影响。"""
    reg = GlobalPlayerRegistry(reference_view_id="cam_1")
    assert reg.set_binding("gid_1", "cam_1", _binding("Player_1", 3), 0.0) is True
    # 同 global 刷新（同槽位）→ 允许
    assert reg.set_binding("gid_1", "cam_1", _binding("Player_1", 3), 10.0) is True
    # 同 global 换 track（仍同槽位）→ 允许
    assert reg.set_binding("gid_1", "cam_1", _binding("Player_1", 88), 20.0) is True
    # 非 reference view（cam_2）空槽位 → 允许
    assert reg.set_binding("gid_3", "cam_2", _binding("Player_1", 34), 0.0) is True
    # 不同 reference 槽位 → 允许
    assert reg.set_binding("gid_3", "cam_1", _binding("Player_2", 200), 0.0) is True
    assert reg.reference_slot_conflicts == {}


def test_set_binding_rejects_non_reference_view_conflict():
    """fix-multiview-cam1-bootstrap-4player 残留修复：非 reference view（cam_2）槽位同样唯一。

    原实现只保护 reference view，导致 cam_2 的 local 身份槽位可被第二个 global
    抢占 → 该 player 的 fused overlay 证据丢失。现扩展至所有 view。
    """
    reg = GlobalPlayerRegistry(reference_view_id="cam_1")
    assert reg.set_binding("gid_1", "cam_2", _binding("Player_1", 3), 0.0) is True
    reg.players["gid_1"].roster_status = "provisional"
    # gid_3 抢占 cam_2 同一槽位 → 冲突，返回 False
    assert reg.set_binding("gid_3", "cam_2", _binding("Player_1", 100), 0.0) is False
    assert reg.reference_slot_occupant("cam_2", "Player_1") == "gid_1"
    assert reg.reference_slot_conflicts.get(("cam_2", "Player_1")) == 1


def test_release_view_slot_allows_strong_evidence_reassociation():
    """fix-multiview-cam1-bootstrap-4player 残留修复：release 后 challenger 可接管槽位。

    强证据 reassociation（连续 N 帧）必须先 release incumbent，否则唯一性保护
    会错误拦截同 view 内的合法身份切换。
    """
    reg = GlobalPlayerRegistry(reference_view_id="cam_1")
    assert reg.set_binding("gid_1", "cam_1", _binding("Player_1", 3), 0.0) is True
    reg.players["gid_1"].roster_status = "provisional"
    assert reg.reference_slot_occupant("cam_1", "Player_1") == "gid_1"
    # release 解除 incumbent 槽位占用
    assert reg.release_view_slot("cam_1", "Player_1") == "gid_1"
    assert reg.reference_slot_occupant("cam_1", "Player_1") is None
    # challenger 现在可绑定（不冲突）
    assert reg.set_binding("gid_2", "cam_1", _binding("Player_1", 100), 0.0) is True
    reg.players["gid_2"].roster_status = "provisional"
    assert reg.reference_slot_occupant("cam_1", "Player_1") == "gid_2"


def test_bound_observation_survives_slight_prediction_lead():
    """fix-multiview-cam1-bootstrap-4player 残留修复：已绑定观测在预测略超前时仍保持关联。

    原实现 incumbent 分支用固定 base_gate（比 reacquire 更紧）：球员减速时 Kalman
    预测超前略超 3.0ft 即被拒 → 观测失去修正 → 预测继续超前 → 死锁（P4 fused
    overlay 消失）。修复后已绑定观测门宽随 uncertainty 扩展，观测持续修正预测。
    """
    reg = _seed_roster(1, positions=[(14.5, 40.0)])
    assoc = GlobalPlayerAssociator(reg, max_association_distance_ft=3.0, switch_margin=0.15)
    # 稳定建立绑定：Player_A 连续多帧在 G1 附近（matched 路径）
    for t in range(5):
        obs = _obs("cam_1", 14.5, 40.0 + t * 0.2, pid="A", tid=1, ts=t / 30.0, frame=t)
        updates = assoc.process_tick([obs], t / 30.0, {"cam_1": IDENTITY}, tick=t)
        assert any(
            u.observation.view_player_id == "A" and u.global_id == "global_player_1"
            for u in updates
        ), f"tick {t}: 绑定未建立"
        reg.absorb_measurement("global_player_1", 14.5, 40.0 + t * 0.2, t / 30.0)
    # 球员减速（速度骤降 → Kalman 预测超前）：观测实际位置比预测位置近 ~3.2ft，
    # 仍应保持关联（已绑定门宽随 uncertainty 扩展，不拒绝）
    for t in range(5, 20):
        obs = _obs("cam_1", 14.5, 41.2, pid="A", tid=1, ts=t / 30.0, frame=t)
        updates = assoc.process_tick([obs], t / 30.0, {"cam_1": IDENTITY}, tick=t)
        assert any(
            u.observation.view_player_id == "A" and u.global_id == "global_player_1"
            for u in updates
        ), f"tick {t}: 已绑定观测被拒（预测超前导致死锁）"
        reg.absorb_measurement("global_player_1", 14.5, 41.2, t / 30.0)


def test_associator_conflict_records_and_keeps_incumbent():
    """D3/D4：两个 global 抢同一 reference 槽位时，challenger 不覆盖，冲突可观测。"""
    reg = GlobalPlayerRegistry(reference_view_id="cam_1")
    # gid_1 先占用 cam_1 Player_1 槽位（模拟 incumbent）
    reg.set_binding("global_player_1", "cam_1", _binding("Player_1", 3), 0.0)
    reg.players["global_player_1"].roster_status = "provisional"
    # challenger gid_3 尝试绑定同一 reference 槽位 → registry 层拦截（覆盖 guided/continuity/historical 全部走 set_binding）
    assert reg.set_binding("global_player_3", "cam_1", _binding("Player_1", 100), 1000.0) is False
    assert reg.reference_slot_occupant("cam_1", "Player_1") == "global_player_1"
    assert reg.reference_slot_conflicts.get(("cam_1", "Player_1")) == 1
    assert reg.last_reference_slot_conflict == ("cam_1", "Player_1", "global_player_1", "global_player_3")


def test_reference_slot_occupant_ignores_unconfirmed():
    """D4：未晋升（无 roster status）的 global 不作为槽位占用者。"""
    reg = GlobalPlayerRegistry(reference_view_id="cam_1")
    reg.set_binding("gid_x", "cam_1", _binding("Player_1", 3), 0.0)
    # gid_x 无 roster_status（未晋升）→ occupant 查询忽略它
    assert reg.reference_slot_occupant("cam_1", "Player_1") is None
    # 晋升后成为占用者
    reg.players["gid_x"].roster_status = "provisional"
    assert reg.reference_slot_occupant("cam_1", "Player_1") == "gid_x"
