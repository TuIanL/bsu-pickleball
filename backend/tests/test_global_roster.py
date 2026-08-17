"""Global Roster 集中单测（stabilize-joint-global-player-roster）。

覆盖：
- Registry roster 化（tasks 1.5）：slot 上限、candidate 不参与 predict_all、占满未确认不 ACTIVE、confirmed 不删
- Candidate 候选池（tasks 2.4）：归属规则（强 key / 弱 prior / 跨 view geometry / 同 view 不合并）、晋升、过期
- Associator（tasks 3.4）：roster 关闭后不创建 G5、PendingReassociation N-1/N 帧、微弱优势不累积、challenger 变化清零
- Roster 重建边界（tasks 4.4）：epoch reset 不重建、reset_roster 进入新 BOOTSTRAPPING
- Guided 强约束 + base 优先 + stale（tasks 5.4）
- F1 冻结 roster（tasks 7.2）：refinement 输出 gid ⊆ F0 gids
"""

from __future__ import annotations

from app.vision.multiview.association_global import GlobalPlayerAssociator, JointObservation
from app.vision.multiview.court_frame import CourtOrientation
from app.vision.multiview.global_state import GlobalPlayerRegistry

IDENTITY = CourtOrientation.identity


def _obs(view_id, x, y, pid="", tid=None, ts=0.0, *, epoch=0, origin="base", expected=None, frame=0):
    return JointObservation(
        view_id=view_id,
        source_frame_index=frame,
        take_timestamp_ms=ts * 1000.0,
        local_x_ft=x,
        local_y_ft=y,
        view_player_id=pid,
        local_identity_epoch=epoch,
        track_id=tid,
        confidence=0.9,
        detection_origin=origin,
        expected_global_player_id=expected,
    )


def _seed_roster(n: int = 2, *, positions: list[tuple[float, float]] | None = None) -> GlobalPlayerRegistry:
    """手动建立 n 个 provisional roster 玩家（带 motion 状态），供关联测试使用。"""
    reg = GlobalPlayerRegistry(expected_player_count=4)
    positions = positions or [(5.0, 8.0), (15.0, 8.0)]
    for i in range(n):
        gid = f"global_player_{i + 1}"
        x, y = positions[i]
        state = reg.ensure(gid)
        state.roster_status = "provisional"
        state.x_ft, state.y_ft = x, y
        reg.estimator.update(gid, x, y, 0.0)
        state.position_uncertainty_ft = 1.0
    return reg


# ---- Registry roster 化（tasks 1.5）----


def test_roster_slot_cap_returns_none_when_full():
    reg = GlobalPlayerRegistry(expected_player_count=2)
    g1 = reg._allocate_roster_slot()  # noqa: SLF001
    reg.ensure(g1)  # 占用 slot
    g2 = reg._allocate_roster_slot()  # noqa: SLF001
    reg.ensure(g2)
    assert {g1, g2} == {"global_player_1", "global_player_2"}
    assert reg._allocate_roster_slot() is None  # roster 满


def test_candidate_does_not_enter_predict_all():
    reg = GlobalPlayerRegistry(expected_player_count=4)
    cid = reg.find_or_create_candidate(
        view_id="cam_1", view_player_id="Player_1", identity_epoch=0,
        canonical_x_ft=5.0, canonical_y_ft=8.0, tick=0,
    )
    reg.note_candidate_observation(cid, view_id="cam_1", view_player_id="Player_1",
                                   identity_epoch=0, canonical_x_ft=5.0, canonical_y_ft=8.0, tick=0)
    assert reg.predict_all(0.0) == {}  # 候选不参与预测


def test_roster_full_but_unconfirmed_stays_bootstrapping():
    reg = GlobalPlayerRegistry(expected_player_count=2, roster_confirm_ticks=30)
    # 两个 occupant 占满但未达确认条件（K tick / anchored）
    for i in range(2):
        gid = f"global_player_{i + 1}"
        state = reg.ensure(gid)
        state.roster_status = "provisional"
    assert reg.roster_state == "BOOTSTRAPPING"
    # 达到 K tick 后才确认
    for _ in range(30):
        for i in range(2):
            reg.absorb_measurement(f"global_player_{i + 1}", 5.0 + i, 8.0, 0.1)
    assert reg.roster_state == "ROSTER_ACTIVE"
    assert all(reg.players[gid].roster_status == "confirmed" for gid in reg.players)


def test_confirmed_roster_survives_out_of_view():
    reg = _seed_roster(1)
    reg.absorb_measurement("global_player_1", 5.0, 8.0, 0.0)
    reg.record_dual_consistent("global_player_1")
    # 长时间未见 → stale（退出普通匹配），但不删除
    reg.update_stale_eligibility(100.0)
    assert "global_player_1" in reg.players  # 不删除
    assert reg.players["global_player_1"].association_eligible is False  # 退出普通匹配
    assert "global_player_1" not in reg.predict_all(100.0)


# ---- Candidate 候选池（tasks 2.4）----


def test_transient_observation_makes_candidate_not_global():
    reg = GlobalPlayerRegistry(expected_player_count=4)
    cid = reg.find_or_create_candidate(
        view_id="cam_1", view_player_id="Player_1", identity_epoch=0,
        canonical_x_ft=5.0, canonical_y_ft=8.0, tick=0,
    )
    assert cid.startswith("candidate_")
    assert reg.players == {}  # 未创建 global
    assert "candidate_" in cid


def test_same_local_identity_accumulates_same_candidate():
    reg = GlobalPlayerRegistry(expected_player_count=4)
    c1 = reg.find_or_create_candidate(
        view_id="cam_1", view_player_id="Player_1", identity_epoch=0,
        canonical_x_ft=5.0, canonical_y_ft=8.0, tick=0,
    )
    c2 = reg.find_or_create_candidate(
        view_id="cam_1", view_player_id="Player_1", identity_epoch=0,
        canonical_x_ft=5.1, canonical_y_ft=8.1, tick=1,
    )
    assert c1 == c2  # 强 key 复用，不扩散


def test_epoch_change_weak_prior_reuses_candidate():
    reg = GlobalPlayerRegistry(expected_player_count=4)
    c1 = reg.find_or_create_candidate(
        view_id="cam_1", view_player_id="Player_1", identity_epoch=0,
        canonical_x_ft=5.0, canonical_y_ft=8.0, tick=0,
    )
    c2 = reg.find_or_create_candidate(
        view_id="cam_1", view_player_id="Player_1", identity_epoch=1,  # epoch 变化
        canonical_x_ft=50.0, canonical_y_ft=50.0, tick=1,  # 几何远
    )
    assert c1 == c2  # 跨 epoch 弱 prior 复用（证据权重低，由调用方控制）


def test_same_view_two_players_never_merge():
    reg = GlobalPlayerRegistry(expected_player_count=4)
    a = reg.find_or_create_candidate(
        view_id="cam_1", view_player_id="Player_1", identity_epoch=0,
        canonical_x_ft=5.0, canonical_y_ft=8.0, tick=0,
    )
    b = reg.find_or_create_candidate(
        view_id="cam_1", view_player_id="Player_2", identity_epoch=0,
        canonical_x_ft=5.2, canonical_y_ft=8.1, tick=0,  # canonical 近距
    )
    assert a != b  # 同 view 双人不得合并


def test_cross_view_geometry_joins_candidate():
    reg = GlobalPlayerRegistry(expected_player_count=4)
    a = reg.find_or_create_candidate(
        view_id="cam_1", view_player_id="Player_1", identity_epoch=0,
        canonical_x_ft=5.0, canonical_y_ft=8.0, tick=0,
    )
    b = reg.find_or_create_candidate(
        view_id="cam_2", view_player_id="Player_1", identity_epoch=0,
        canonical_x_ft=5.2, canonical_y_ft=8.1, tick=0,  # 跨 view 近距
    )
    assert a == b  # 跨 view geometry 邻域合并


def test_promotion_occupies_slot_and_expiry_cleans():
    reg = GlobalPlayerRegistry(expected_player_count=2, candidate_expire_ticks=3)
    cid = reg.find_or_create_candidate(
        view_id="cam_1", view_player_id="Player_1", identity_epoch=0,
        canonical_x_ft=5.0, canonical_y_ft=8.0, tick=0,
    )
    reg.note_candidate_observation(cid, view_id="cam_1", view_player_id="Player_1",
                                   identity_epoch=0, canonical_x_ft=5.0, canonical_y_ft=8.0, tick=0)
    gid = reg.promote_candidate(cid, tick=0)
    assert gid == "global_player_1"
    assert reg.players["global_player_1"].roster_status == "provisional"
    assert cid not in reg.candidates  # 晋升后出候选池
    # 过期清理
    cid2 = reg.find_or_create_candidate(
        view_id="cam_1", view_player_id="Player_2", identity_epoch=0,
        canonical_x_ft=5.0, canonical_y_ft=8.0, tick=0,
    )
    reg.expire_candidates(tick=10)  # 超过 expire 窗口
    assert cid2 not in reg.candidates
    assert "global_player_1" in reg.players  # 清理不影响 roster


# ---- Associator（tasks 3.4）----


def test_roster_active_no_new_global_after_cap():
    reg = _seed_roster(2)
    reg.roster_state = "ROSTER_ACTIVE"
    assoc = GlobalPlayerAssociator(reg, max_association_distance_ft=3.0)
    # 一个离所有 roster 玩家都很远的观测 → unresolved，不创建 global
    obs = _obs("cam_1", 100.0, 100.0, pid="Z", tid=99, frame=0)
    updates = assoc.process_tick([obs], 0.0, {"cam_1": IDENTITY}, tick=0)
    assert updates == []
    assert len(reg.players) <= 2  # 硬断言：不创建 G3


def test_reassociation_requires_n_frames_strong_evidence():
    reg = _seed_roster(2)  # G1 (5,8), G2 (15,8)
    assoc = GlobalPlayerAssociator(reg, max_association_distance_ft=3.0, switch_margin=0.15, reassociation_frames=5)
    # 先让 Player_A 稳定绑定 G1（观测在 G1 附近）
    for t in range(3):
        obs = _obs("cam_1", 5.0 + t * 0.1, 8.0, pid="A", tid=1, ts=t / 30.0, frame=t)
        updates = assoc.process_tick([obs], t / 30.0, {"cam_1": IDENTITY}, tick=t)
        assert {u.global_id for u in updates} == {"global_player_1"}
        reg.absorb_measurement("global_player_1", 5.0 + t * 0.1, 8.0, t / 30.0)
    # Player_A 移到 G2 附近：N-1 = 4 帧保持 G1，第 5 帧才切换
    for i in range(4):
        t = 10 + i
        obs = _obs("cam_1", 14.5, 8.0, pid="A", tid=1, ts=t / 30.0, frame=t)
        updates = assoc.process_tick([obs], t / 30.0, {"cam_1": IDENTITY}, tick=t)
        u = [u for u in updates if u.observation.view_player_id == "A"]
        assert u and u[0].global_id == "global_player_1"  # N-1 帧不切换
    t = 14
    obs = _obs("cam_1", 14.5, 8.0, pid="A", tid=1, ts=t / 30.0, frame=t)
    updates = assoc.process_tick([obs], t / 30.0, {"cam_1": IDENTITY}, tick=t)
    u = [u for u in updates if u.observation.view_player_id == "A"]
    assert u and u[0].global_id == "global_player_2"  # 第 N 帧强证据才切换


def test_marginal_advantage_does_not_accumulate():
    reg = _seed_roster(2, positions=[(5.0, 8.0), (6.0, 8.0)])  # G1, G2 很近
    assoc = GlobalPlayerAssociator(reg, max_association_distance_ft=3.0, switch_margin=0.15, reassociation_frames=5)
    for t in range(3):
        obs = _obs("cam_1", 5.0 + t * 0.1, 8.0, pid="A", tid=1, ts=t / 30.0, frame=t)
        assoc.process_tick([obs], t / 30.0, {"cam_1": IDENTITY}, tick=t)
        reg.absorb_measurement("global_player_1", 5.0 + t * 0.1, 8.0, t / 30.0)
    # obs 在 G1/G2 之间：challenger G2 只略优（< switch_margin）→ 永不累积
    for i in range(6):
        t = 10 + i
        obs = _obs("cam_1", 5.55, 8.0, pid="A", tid=1, ts=t / 30.0, frame=t)
        updates = assoc.process_tick([obs], t / 30.0, {"cam_1": IDENTITY}, tick=t)
        u = [u for u in updates if u.observation.view_player_id == "A"]
        assert u and u[0].global_id == "global_player_1"  # 微弱优势不累积换人


def test_reassociation_challenger_change_resets_counter():
    reg = _seed_roster(3, positions=[(5.0, 8.0), (6.0, 8.0), (7.0, 8.0)])  # G1, G2, G3
    assoc = GlobalPlayerAssociator(reg, max_association_distance_ft=3.0, switch_margin=0.15, reassociation_frames=5)
    for t in range(3):
        obs = _obs("cam_1", 5.0 + t * 0.1, 8.0, pid="A", tid=1, ts=t / 30.0, frame=t)
        assoc.process_tick([obs], t / 30.0, {"cam_1": IDENTITY}, tick=t)
        reg.absorb_measurement("global_player_1", 5.0 + t * 0.1, 8.0, t / 30.0)
    # 第 1 帧 challenger=G2；第 2 帧 challenger=G3（变化）→ 计数清零，不切换
    obs = _obs("cam_1", 5.9, 8.0, pid="A", tid=1, ts=10 / 30.0, frame=10)
    assoc.process_tick([obs], 10 / 30.0, {"cam_1": IDENTITY}, tick=10)
    obs = _obs("cam_1", 6.9, 8.0, pid="A", tid=1, ts=11 / 30.0, frame=11)
    updates = assoc.process_tick([obs], 11 / 30.0, {"cam_1": IDENTITY}, tick=11)
    u = [u for u in updates if u.observation.view_player_id == "A"]
    assert u and u[0].global_id == "global_player_1"  # challenger 变化 → 保持


# ---- Roster 重建边界（tasks 4.4）----


def test_epoch_reset_does_not_rebuild_roster():
    reg = _seed_roster(1)
    assoc = GlobalPlayerAssociator(reg, max_association_distance_ft=3.0)
    # epoch reset 的观测：弱历史绑定可重回原 global，但 registry 不重建
    obs = _obs("cam_1", 5.2, 8.1, pid="Player_1", tid=1, ts=1 / 30.0, epoch=1, frame=5)
    updates = assoc.process_tick([obs], 1 / 30.0, {"cam_1": IDENTITY}, tick=5)
    assert {u.global_id for u in updates} == {"global_player_1"}
    assert reg.roster_state == "BOOTSTRAPPING"  # 未重建
    assert "global_player_1" in reg.players


def test_reset_roster_enters_fresh_bootstrapping():
    reg = _seed_roster(2)
    reg.roster_state = "ROSTER_ACTIVE"
    reg.reset_roster()
    assert reg.players == {}
    assert reg.candidates == {}
    assert reg.roster_state == "BOOTSTRAPPING"


# ---- Guided 强约束 + base 优先 + stale（tasks 5.4）----


def test_guided_expected_binds_expected_not_lower_cost():
    reg = _seed_roster(2, positions=[(5.0, 8.0), (5.1, 8.0)])  # G1 expected, G2 更近
    assoc = GlobalPlayerAssociator(reg, max_association_distance_ft=3.0)
    obs = _obs("cam_1", 5.2, 8.0, pid="A", tid=1, frame=0, origin="guided_roi", expected="global_player_1")
    updates = assoc.process_tick([obs], 0.0, {"cam_1": IDENTITY}, tick=0)
    assert {u.global_id for u in updates} == {"global_player_1"}  # 绑 expected，不转投更近的 G2


def test_guided_expected_infeasible_rejects_without_switch():
    reg = _seed_roster(2, positions=[(5.0, 8.0), (5.1, 8.0)])
    assoc = GlobalPlayerAssociator(reg, max_association_distance_ft=3.0)
    obs = _obs("cam_1", 20.0, 30.0, pid="A", tid=1, frame=0, origin="guided_roi", expected="global_player_1")
    updates = assoc.process_tick([obs], 0.0, {"cam_1": IDENTITY}, tick=0)
    assert updates == []  # G1 几何不可行 → reject，不转投 G2
    assert assoc.diagnostics.get("guided_expected_rejected", 0) == 1


def test_base_evidence_wins_over_guidance():
    reg = _seed_roster(2, positions=[(5.0, 8.0), (5.1, 8.0)])
    assoc = GlobalPlayerAssociator(reg, max_association_distance_ft=3.0)
    base = _obs("cam_1", 5.1, 8.0, pid="B", tid=2, frame=0, origin="base")
    guided = _obs("cam_1", 5.2, 8.0, pid="C", tid=3, frame=0, origin="guided_roi", expected="global_player_1")
    updates = assoc.process_tick([base, guided], 0.0, {"cam_1": IDENTITY}, tick=0)
    by_pid = {u.observation.view_player_id: u.global_id for u in updates}
    assert by_pid["C"] == "global_player_1"  # guided 绑 expected
    assert by_pid["B"] == "global_player_2"  # base 走普通关联（最近），guidance 不覆盖


def test_stale_player_not_absorbing_and_strong_reacquire_works():
    reg = _seed_roster(2, positions=[(5.0, 8.0), (15.0, 8.0)])
    assoc = GlobalPlayerAssociator(reg, max_association_distance_ft=3.0)
    # G1 变 stale
    reg.players["global_player_1"].last_seen_s = 0.0
    reg.update_stale_eligibility(100.0)
    assert reg.players["global_player_1"].association_eligible is False
    # 普通观测（在 G1 位置）不吸附 stale 的 G1；离唯一 eligible 的 G2 也远 → 无 update（不吸附）
    obs = _obs("cam_1", 5.2, 8.0, pid="A", tid=1, frame=0)
    updates = assoc.process_tick([obs], 100.0, {"cam_1": IDENTITY}, tick=0)
    assert "global_player_1" not in {u.global_id for u in updates}  # stale 不吸附
    assert updates == []  # 未匹配任何 eligible 玩家
    # 强恢复路径：弱历史绑定 (cam_1, Player_1) 仍可找回 G1
    reg.historical_bindings[("cam_1", "Player_1")] = "global_player_1"
    obs2 = _obs("cam_1", 5.2, 8.0, pid="Player_1", tid=1, frame=1)
    updates2 = assoc.process_tick([obs2], 101.0, {"cam_1": IDENTITY}, tick=1)
    assert {u.global_id for u in updates2} == {"global_player_1"}  # 强恢复回归


# ---- F1 冻结 roster（tasks 7.2）----


def test_offline_refinement_frozen_roster_outcome():
    from app.vision.multiview.offline_refinement import (
        F0RefinementSnapshot,
        F0TickSnapshot,
        F0TickViewState,
        run_offline_refinement,
    )

    snapshot = F0RefinementSnapshot(
        run_id="run-1",
        capture_take_id="take-1",
        global_player_ids=("global_player_1",),
        config_snapshot={},
        ticks=(
            F0TickSnapshot(
                canonical_tick=0,
                canonical_timestamp_ms=0.0,
                reference_frame_index=0,
                observations=(
                    (
                        "global_player_1",
                        "cam_1",
                        F0TickViewState(observed=True, quality=0.9, canonical_position=(5.0, 8.0), origin="base"),
                    ),
                    (
                        "global_player_1",
                        "cam_2",
                        F0TickViewState(observed=True, quality=0.9, canonical_position=(5.1, 8.1), origin="base"),
                    ),
                ),
                global_positions=(("global_player_1", (5.0, 8.0)),),
            ),
        ),
    )
    outcome = run_offline_refinement(snapshot=snapshot, views=("cam_1", "cam_2"), reference_view_id="cam_1")
    # 无 recovery 窗口 → skipped，roster 冻结默认保持
    assert outcome.status == "skipped_no_windows"
    assert outcome.roster_frozen is True
    # 若有 refinement 样本，其 gid 必须 ⊆ F0 gids（不新增 slot）
    for sample in outcome.candidate_samples:
        gid = getattr(sample, "global_player_id", None)
        assert gid is None or gid in snapshot.global_player_ids


# ---- fix-multiview-single-view-fallback：单视图活跃豁免（D1）----


def _binding(view_player_id: str, last_seen_ms: float, *, weak_after_ms: float = 300.0, lost_after_ms: float = 1000.0) -> ViewBinding:
    """构造指定 last_seen 的 ViewBinding，visibility 按 gap 判定。"""
    from app.vision.multiview.global_state import ViewBinding as _VB

    b = _VB(view_player_id=view_player_id, last_seen_take_timestamp_ms=last_seen_ms, quality=0.8)
    b.update_visibility(0.0, weak_after_ms=weak_after_ms, lost_after_ms=lost_after_ms)
    return b


def test_single_view_active_not_stale():
    """单视图 binding 活跃（observed 且 last_seen 新鲜）→ 不置 stale，predict_all 返回其预测。"""
    reg = _seed_roster(1)
    reg.absorb_measurement("global_player_1", 5.0, 8.0, 0.0)  # last_seen_s = 0.0
    # 仅 cam_1 binding（observed），cam_2 无 binding → 跨视图缺失
    reg.players["global_player_1"].view_bindings["cam_1"] = _binding("Player_1", last_seen_ms=100.0)  # observed (gap 100ms)
    # now_s = 2.0：last_seen_s=0.0 → age 2s < stale_last_seen_s(10s)，binding observed → 豁免
    reg.update_stale_eligibility(2.0)
    assert reg.players["global_player_1"].association_eligible is True
    assert "global_player_1" in reg.predict_all(2.0)


def test_single_view_active_stale_only_when_binding_expired():
    """单视图 binding 已过期（lost）且 last_seen 超阈值 → 仍置 stale（豁免不适用）。"""
    reg = _seed_roster(1)
    reg.absorb_measurement("global_player_1", 5.0, 8.0, 0.0)  # last_seen_s = 0.0
    reg.players["global_player_1"].view_bindings["cam_1"] = _binding("Player_1", last_seen_ms=5000.0)  # lost (gap 5s > 1s)
    # now_s = 100.0：last_seen age 100s > 10s，binding lost → 豁免不适用 → stale
    reg.update_stale_eligibility(100.0)
    assert reg.players["global_player_1"].association_eligible is False
    assert "global_player_1" not in reg.predict_all(100.0)


def test_single_view_active_uncertainty_high_still_stale():
    """即使单视图 binding observed，uncertainty 超阈值仍置 stale（uncertainty 门控不被豁免覆盖）。"""
    reg = _seed_roster(1)
    reg.absorb_measurement("global_player_1", 5.0, 8.0, 0.0)
    reg.players["global_player_1"].view_bindings["cam_1"] = _binding("Player_1", last_seen_ms=100.0)  # observed
    reg.players["global_player_1"].position_uncertainty_ft = 20.0  # > stale_uncertainty_ft(6.0)
    reg.update_stale_eligibility(2.0)
    assert reg.players["global_player_1"].association_eligible is False


# ---- fix-multiview-single-view-fallback：fusion 单视图 sample 产出（D2）----


def test_single_view_fallback_samples():
    """单视图玩家（仅 cam_1 观测）→ 每 tick 分配到该 global 并产出 single_view_fallback 语义。"""
    reg = GlobalPlayerRegistry(expected_player_count=4, stale_last_seen_s=10.0)
    positions = [(5.0, 8.0), (15.0, 8.0), (5.0, 30.0), (15.0, 30.0)]
    for i, (x, y) in enumerate(positions):
        gid = f"global_player_{i + 1}"
        state = reg.ensure(gid)
        state.roster_status = "confirmed"
        state.position_uncertainty_ft = 1.0
        reg.estimator.update(gid, x, y, 0.0)
        reg.absorb_measurement(gid, x, y, 0.0)
        state.view_bindings["cam_1"] = _binding(f"Player_{i + 1}", last_seen_ms=0.0)
        if i != 3:  # global_player_4 无 cam_2 binding → 单视图
            state.view_bindings["cam_2"] = _binding(f"Player_{i + 1}", last_seen_ms=0.0)

    assoc = GlobalPlayerAssociator(reg)
    n_fallback_samples = 0
    for tick in range(1, 31):
        ts = tick * 0.1
        cam1 = [
            JointObservation(
                view_id="cam_1", source_frame_index=tick, take_timestamp_ms=ts * 1000.0,
                local_x_ft=positions[i][0] + 0.01, local_y_ft=positions[i][1],
                view_player_id=f"Player_{i + 1}", local_identity_epoch=0,
                track_id=i + 1, confidence=0.7,
            )
            for i in range(4)
        ]
        cam2 = [
            JointObservation(
                view_id="cam_2", source_frame_index=tick, take_timestamp_ms=ts * 1000.0,
                local_x_ft=positions[i][0] - 0.01, local_y_ft=positions[i][1],
                view_player_id=f"Player_{i + 1}", local_identity_epoch=0,
                track_id=i + 1, confidence=0.7,
            )
            for i in range(3)
        ]
        reg.update_stale_eligibility(ts)
        updates = assoc.process_tick(cam1 + cam2, ts, {"cam_1": IDENTITY, "cam_2": IDENTITY}, tick=tick)
        fused = assoc.fuse_assignments(updates)
        for gid, (_, _, views) in fused.items():
            # joint_run.py 判定：len(views) >= 2 → dual_observed，否则 single_view_fallback
            status = "dual_observed" if len(views) >= 2 else "single_view_fallback"
            if gid == "global_player_4":
                assert status == "single_view_fallback", f"P2 应 single_view_fallback, got {status}"
                assert views == ["cam_1"]
                n_fallback_samples += 1
        for gid, (x, y, _) in fused.items():
            reg.absorb_measurement(gid, x, y, ts)

    assert n_fallback_samples == 30, f"P2 应有 30 个 single_view_fallback sample, got {n_fallback_samples}"
    assert reg.players["global_player_4"].association_eligible is True
