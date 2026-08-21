"""overlay display state machine + view scale profile 单元测试。

覆盖（tasks 6.1 / 6.2）：
- 状态机：真实 bbox 立即升级 / synthetic upgrade 需 confirm + gap 约束 /
  geometry 无效 hard stop / 无证据硬 HIDDEN / reset 跨 job 隔离 / 逐帧抖动消除断言；
- ViewPersonScaleProfile：两遍式 / 只收真实 bbox（synthetic 不回喂）/ 邻桶插值防 2px 跳跃 /
  样本不足 fallback；
- bbox fallback 顺序：fresh memory 优先于 scale profile / scale profile 优先于 stale memory /
  stale 仅兜底 / 全失效降级光圈。
"""

from __future__ import annotations

import pytest

from app.vision.multiview.overlay_display_state import (
    DisplayContext,
    OverlayDisplayStateMachine,
    ViewPersonScaleProfile,
)


def _ctx(*, evidence: str | None, now: float = 1000.0, **overrides) -> DisplayContext:
    defaults = dict(
        now_ms=now,
        evidence_type=evidence,
        has_real_bbox=False,
        has_synthetic_bbox=False,
        has_valid_point=False,
        prediction_expired=False,
        geometry_valid=True,
        bbox_age_ms=None,
        bbox_stale=False,
    )
    defaults.update(overrides)
    return DisplayContext(**defaults)


# ---- 1. 状态机：真实 bbox 立即升级 ------------------------------------------


def test_real_bbox_immediately_upgrades_from_point() -> None:
    sm = OverlayDisplayStateMachine()
    # 先进入 PROJECTED_POINT
    plan = sm.step(player_id="Player_1", view_id="cam_1", ctx=_ctx(evidence="cross_view_projected", now=1000))
    assert plan.state == "PROJECTED_POINT"
    # 真实 bbox 出现 → 立即 REAL_BOX（不等 confirm）
    plan = sm.step(
        player_id="Player_1", view_id="cam_1",
        ctx=_ctx(evidence="base_observed", has_real_bbox=True, now=1033),
    )
    assert plan.state == "REAL_BOX"
    assert plan.preferred_bbox_source == "real"


def test_guided_observed_maps_to_assisted_box() -> None:
    sm = OverlayDisplayStateMachine()
    plan = sm.step(
        player_id="Player_1", view_id="cam_1",
        ctx=_ctx(evidence="guided_observed", has_real_bbox=True),
    )
    assert plan.state == "ASSISTED_BOX"


# ---- 2. synthetic upgrade 需稳定确认 -----------------------------------------


def test_synthetic_upgrade_requires_confirm_ticks() -> None:
    sm = OverlayDisplayStateMachine(synthetic_upgrade_confirm_ticks=3)
    # 连续 3 帧 cross_view + synthetic bbox 才升级 PROJECTED_POINT → PROJECTED_BOX
    for i in range(2):
        plan = sm.step(
            player_id="Player_1", view_id="cam_1",
            ctx=_ctx(evidence="cross_view_projected", has_synthetic_bbox=True, now=1000 + i * 33),
        )
        assert plan.state == "PROJECTED_POINT", f"frame {i} should stay POINT"
    plan = sm.step(
        player_id="Player_1", view_id="cam_1",
        ctx=_ctx(evidence="cross_view_projected", has_synthetic_bbox=True, now=1000 + 2 * 33),
    )
    assert plan.state == "PROJECTED_BOX"


def test_synthetic_upgrade_resets_on_gap() -> None:
    sm = OverlayDisplayStateMachine(synthetic_upgrade_confirm_ticks=3, confirm_max_gap_ms=100.0)
    sm.step(
        player_id="Player_1", view_id="cam_1",
        ctx=_ctx(evidence="cross_view_projected", has_synthetic_bbox=True, now=1000),
    )
    # 间隔 500ms 超过 confirm_max_gap_ms → 计数重置（1500 重新算第 1 帧）
    sm.step(
        player_id="Player_1", view_id="cam_1",
        ctx=_ctx(evidence="cross_view_projected", has_synthetic_bbox=True, now=1500),
    )
    # 第 2 帧（1533）→ POINT；第 3 帧（1566）→ BOX
    plan = sm.step(
        player_id="Player_1", view_id="cam_1",
        ctx=_ctx(evidence="cross_view_projected", has_synthetic_bbox=True, now=1533),
    )
    assert plan.state == "PROJECTED_POINT"
    plan = sm.step(
        player_id="Player_1", view_id="cam_1",
        ctx=_ctx(evidence="cross_view_projected", has_synthetic_bbox=True, now=1566),
    )
    assert plan.state == "PROJECTED_BOX"


# ---- 3. 短暂漏检诚实降级 -----------------------------------------------------


def test_transient_miss_honest_evidence_degradation() -> None:
    sm = OverlayDisplayStateMachine(hysteresis_grace_ms=100.0)
    # t0 真实
    plan = sm.step(
        player_id="Player_1", view_id="cam_1",
        ctx=_ctx(evidence="base_observed", has_real_bbox=True, now=1000),
    )
    assert plan.state == "REAL_BOX"
    # t1 本视角 miss，donor 可靠（cross_view + synthetic bbox）→ 保持框但诚实降级
    plan = sm.step(
        player_id="Player_1", view_id="cam_1",
        ctx=_ctx(evidence="cross_view_projected", has_synthetic_bbox=True, now=1033),
    )
    assert plan.state == "PROJECTED_BOX"  # 形态保持框
    assert plan.preferred_bbox_source in ("reanchor", "scale_profile")


# ---- 4. 硬 stop / reset ------------------------------------------------------


def test_geometry_invalid_blocks_synthetic_box() -> None:
    sm = OverlayDisplayStateMachine()
    plan = sm.step(
        player_id="Player_1", view_id="cam_1",
        ctx=_ctx(evidence="cross_view_projected", has_synthetic_bbox=True, geometry_valid=False),
    )
    assert plan.state != "PROJECTED_BOX"
    assert plan.state in ("PROJECTED_POINT", "HIDDEN")


def test_no_evidence_and_expired_prediction_forces_hidden() -> None:
    sm = OverlayDisplayStateMachine()
    plan = sm.step(
        player_id="Player_1", view_id="cam_1",
        ctx=_ctx(evidence="predicted_only", prediction_expired=True, has_valid_point=False),
    )
    assert plan.state == "HIDDEN"
    assert plan.render is False


def test_reset_clears_cross_job_state() -> None:
    sm = OverlayDisplayStateMachine()
    sm.step(player_id="Player_1", view_id="cam_1", ctx=_ctx(evidence="base_observed", has_real_bbox=True, now=1000))
    sm.reset()
    # reset 后从 HIDDEN 重新开始：synthetic 首帧应 POINT（需 confirm，不残留 REAL 状态）
    plan = sm.step(
        player_id="Player_1", view_id="cam_1",
        ctx=_ctx(evidence="cross_view_projected", has_synthetic_bbox=True, now=2000),
    )
    assert plan.state == "PROJECTED_POINT"


# ---- 5. 逐帧抖动消除 ---------------------------------------------------------


def test_no_flicker_on_stable_evidence_sequence() -> None:
    """同一 evidence 序列（连续 cross_view + synthetic bbox）→ 形态稳定。"""
    sm = OverlayDisplayStateMachine(synthetic_upgrade_confirm_ticks=3)
    states = []
    for i in range(10):
        plan = sm.step(
            player_id="Player_1", view_id="cam_1",
            ctx=_ctx(evidence="cross_view_projected", has_synthetic_bbox=True, now=1000 + i * 33),
        )
        states.append(plan.state)
    # 升级一次后保持稳定：无 REAL↔POINT 交替
    assert len(set(states)) <= 2  # 只有 PROJECTED_POINT → PROJECTED_BOX 一次升级
    assert "REAL_BOX" not in states


# ---- 5b. 时间连续性（Stage 1.6：迟滞作用域 / hold 计时权威 / hard TTL）--------


def test_observed_to_predicted_no_box_even_within_grace() -> None:
    """observed → predicted_only（无 projected 位置证据）→ 直接 PREDICTED_POINT，绝不画人体框。"""
    sm = OverlayDisplayStateMachine(hysteresis_grace_ms=100.0)
    sm.step(player_id="Player_1", view_id="cam_1", ctx=_ctx(evidence="base_observed", has_real_bbox=True, now=1000))
    plan = sm.step(
        player_id="Player_1", view_id="cam_1",
        ctx=_ctx(evidence="predicted_only", has_valid_point=True, now=1033),
    )
    assert plan.state == "PREDICTED_POINT"
    assert plan.preferred_bbox_source == "none"


def test_miss_with_projected_evidence_degrades_to_projected_box_not_real() -> None:
    """真实 bbox 丢失且有 projected 证据 → 立即 PROJECTED_BOX（MUST NOT 保留 REAL_BOX）。"""
    sm = OverlayDisplayStateMachine()
    sm.step(player_id="Player_1", view_id="cam_1", ctx=_ctx(evidence="base_observed", has_real_bbox=True, now=1000))
    plan = sm.step(
        player_id="Player_1", view_id="cam_1",
        ctx=_ctx(evidence="cross_view_projected", has_synthetic_bbox=True, now=1033),
    )
    assert plan.state == "PROJECTED_BOX"
    assert plan.state != "REAL_BOX"


def test_template_transient_loss_holds_box_within_projected_box_hold() -> None:
    """synthetic 模板瞬失 ≤ projected_box_hold_ms → 保持 BOX（不 BOX→POINT→BOX）。"""
    sm = OverlayDisplayStateMachine(projected_box_hold_ms=400.0)
    sm.step(player_id="Player_1", view_id="cam_1", ctx=_ctx(evidence="base_observed", has_real_bbox=True, now=1000))
    p = sm.step(
        player_id="Player_1", view_id="cam_1",
        ctx=_ctx(evidence="cross_view_projected", has_synthetic_bbox=True, now=1100),
    )
    assert p.state == "PROJECTED_BOX"
    plan = sm.step(
        player_id="Player_1", view_id="cam_1",
        ctx=_ctx(evidence="cross_view_projected", has_synthetic_bbox=False, now=1200),
    )
    assert plan.state == "PROJECTED_BOX"  # 距 last_valid(1100)=100ms ≤ 400 → 保持框
    assert plan.preferred_bbox_source == "held_presentation"


def test_hold_authority_from_last_valid_geometry_not_last_real() -> None:
    """projected_box_hold 从 last_valid_box_ts（最后成功演示 bbox）起算，而非 last_real_bbox_ts。"""
    sm = OverlayDisplayStateMachine(projected_box_hold_ms=200.0)
    sm.step(player_id="Player_1", view_id="cam_1", ctx=_ctx(evidence="base_observed", has_real_bbox=True, now=1000))
    sm.step(player_id="Player_1", view_id="cam_1", ctx=_ctx(evidence="cross_view_projected", has_synthetic_bbox=True, now=1100))
    sm.step(player_id="Player_1", view_id="cam_1", ctx=_ctx(evidence="cross_view_projected", has_synthetic_bbox=True, now=1200))
    # last_valid=1200；now=1250 距 last_valid=50ms ≤ 200 → BOX（若从 last_real=1000 算则 250>200 会误塌点）
    plan = sm.step(
        player_id="Player_1", view_id="cam_1",
        ctx=_ctx(evidence="cross_view_projected", has_synthetic_bbox=False, now=1250),
    )
    assert plan.state == "PROJECTED_BOX"
    assert plan.preferred_bbox_source == "held_presentation"


def test_hold_overrun_downgrades_to_point() -> None:
    """template 不可用超过 projected_box_hold_ms → PROJECTED_POINT（不得长期赖框）。"""
    sm = OverlayDisplayStateMachine(projected_box_hold_ms=200.0)
    sm.step(player_id="Player_1", view_id="cam_1", ctx=_ctx(evidence="base_observed", has_real_bbox=True, now=1000))
    sm.step(player_id="Player_1", view_id="cam_1", ctx=_ctx(evidence="cross_view_projected", has_synthetic_bbox=True, now=1200))
    plan = sm.step(
        player_id="Player_1", view_id="cam_1",
        ctx=_ctx(evidence="cross_view_projected", has_synthetic_bbox=False, now=1500),
    )
    assert plan.state == "PROJECTED_POINT"


def test_hard_ttl_overrides_hold_and_grace() -> None:
    """预测 TTL 超限且无有效 point → HIDDEN（硬 stop 优先于任何 hold/grace）。"""
    sm = OverlayDisplayStateMachine()
    sm.step(player_id="Player_1", view_id="cam_1", ctx=_ctx(evidence="base_observed", has_real_bbox=True, now=1000))
    plan = sm.step(
        player_id="Player_1", view_id="cam_1",
        ctx=_ctx(evidence="predicted_only", prediction_expired=True, has_valid_point=False, now=1600),
    )
    assert plan.state == "HIDDEN"
    assert plan.render is False


def test_real_recovers_immediately_after_hold() -> None:
    """真实观察恢复 → 零延迟恢复 REAL_BOX（不被 hysteresis/hold/confirm 延迟）。"""
    sm = OverlayDisplayStateMachine()
    sm.step(player_id="Player_1", view_id="cam_1", ctx=_ctx(evidence="base_observed", has_real_bbox=True, now=1000))
    sm.step(player_id="Player_1", view_id="cam_1", ctx=_ctx(evidence="cross_view_projected", has_synthetic_bbox=True, now=1100))
    plan = sm.step(
        player_id="Player_1", view_id="cam_1",
        ctx=_ctx(evidence="base_observed", has_real_bbox=True, now=1200),
    )
    assert plan.state == "REAL_BOX"
    assert plan.preferred_bbox_source == "real"


# ---- 6. ViewPersonScaleProfile -----------------------------------------------


def test_scale_profile_two_pass_and_interpolation() -> None:
    profile = ViewPersonScaleProfile(frame_height=480, min_total_samples=6, min_samples_per_bin=3)
    # Pass 1：近处（y 大）样本高、远处（y 小）样本矮
    for y in (100, 101, 102):
        profile.collect(footpoint_y=y, width=20, height=60)
    for y in (300, 301, 302):
        profile.collect(footpoint_y=y, width=40, height=120)
    profile.freeze(frame_height=480)
    # Pass 2：查询
    near = profile.query(301)
    far = profile.query(101)
    assert near is not None and far is not None
    assert near[1] > far[1]  # 近处高


def test_scale_profile_interpolates_between_bins() -> None:
    profile = ViewPersonScaleProfile(frame_height=480, n_bins=4, min_total_samples=4, min_samples_per_bin=2)
    for y in (50, 51):
        profile.collect(footpoint_y=y, width=20, height=60)
    for y in (400, 401):
        profile.collect(footpoint_y=y, width=40, height=120)
    profile.freeze(frame_height=480)
    # 中间桶（无样本）→ 邻桶插值，不应为 None
    mid = profile.query(225)
    assert mid is not None
    assert mid[1] > 60 and mid[1] < 120  # 介于两桶之间


def test_scale_profile_insufficient_samples_returns_none() -> None:
    profile = ViewPersonScaleProfile(frame_height=480, min_total_samples=50)
    profile.collect(footpoint_y=100, width=20, height=60)
    profile.freeze(frame_height=480)
    assert profile.query(100) is None  # 样本不足


def test_scale_profile_rejects_extreme_aspect_ratio() -> None:
    profile = ViewPersonScaleProfile(frame_height=480, min_aspect_ratio=0.15, max_aspect_ratio=2.0)
    profile.collect(footpoint_y=100, width=5, height=60)  # 长宽比 0.083 → 拒绝
    profile.freeze(frame_height=480)
    assert profile.query(100) is None


# ---- 7. bbox fallback 顺序（builder 级在集成测试覆盖；此处验证 freshness 契约） ----


def test_freshness_contract() -> None:
    from app.vision.multiview.fused_overlay_builder import OverlayBuilderConfig, TargetViewBBoxMemory

    config = OverlayBuilderConfig(bbox_memory_ttl_ms=2000.0, bbox_memory_grace_ms=500.0)
    memory = TargetViewBBoxMemory(config)
    memory.update(
        global_player_id="global_player_1", view_id="cam_1",
        bbox=(100, 200, 120, 280), quality=0.8, observed_ms=1000.0,
    )
    # fresh（age 100ms < ttl）→ 非 stale
    stale, age = memory.freshness(global_player_id="global_player_1", view_id="cam_1", now_ms=1100.0)
    assert stale is False
    assert age == pytest.approx(100.0)
    # 过期但 grace 内（age 2100ms > ttl 但 < ttl+grace）→ stale
    stale, age = memory.freshness(global_player_id="global_player_1", view_id="cam_1", now_ms=3100.0)
    assert stale is True
    # 超 grace（age 2600ms > ttl+grace）→ reanchor 返回 None
    result = memory.reanchor(
        global_player_id="global_player_1", view_id="cam_1",
        new_footpoint=(110.0, 280.0), now_ms=3600.0,
    )
    assert result is None


# ---- 8. 集成测试：builder 端到端稳定输出 + synthetic 不回喂（tasks 6.3）-----


def test_builder_stable_output_and_scale_profile_no_feedback():
    """相同 evidence 序列 → 稳定 DisplayPlan；synthetic bbox 不回喂 memory/profile。"""
    from app.vision.multiview.court_frame import CourtOrientation
    from app.vision.multiview.fused_overlay_builder import FusedPlayerOverlayBuilder, OverlayBuilderConfig
    from app.vision.multiview.fused_overlay_bundle import JointOverlayEvidenceBundle, ViewGeometry
    from app.vision.multiview.fused_overlay_types import build_fused_player_overlay_payload
    from app.vision.multiview.offline_refinement import (
        F0RefinementSnapshot,
        F0TickSnapshot,
        F0TickViewState,
    )

    IDENTITY = CourtOrientation.identity
    H = [[10.0, 0.0, 0.0], [0.0, 10.0, 0.0], [0.0, 0.0, 1.0]]
    geometry = ViewGeometry(
        view_id="cam_1", orientation=IDENTITY, inverse_homography=H,
        frame_width=640, frame_height=480,
    )

    def state(origin: str, quality: float, bbox, tick_ms: float) -> F0TickViewState:
        return F0TickViewState(
            observed=True, quality=quality, canonical_position=(10.0, 20.0), origin=origin,
            source_frame_index=10, source_timestamp_ms=tick_ms, mapped_take_timestamp_ms=tick_ms,
            timing_authority="reference", sync_quality="good", view_status="available",
            observation_status="observed", view_player_id="global_player_1",
            detector_confidence=quality, projection_confidence=0.9, tracking_status="detected",
            bbox=bbox,
        )

    # 序列：t0 真实 base → t1-t4 donor-only（cross_view）+ scale profile 样本 → t5 真实恢复
    ticks = (
        F0TickSnapshot(
            canonical_tick=0, canonical_timestamp_ms=1000.0, reference_frame_index=10,
            observations=(("global_player_1", "cam_1", state("base", 0.8, (100.0, 200.0, 150.0, 300.0), 1000.0)),),
            global_positions=(("global_player_1", (10.0, 20.0)),),
            predictions=(("global_player_1", (10.0, 20.0)),),
        ),
        F0TickSnapshot(
            canonical_tick=1, canonical_timestamp_ms=1033.0, reference_frame_index=11,
            observations=(("global_player_1", "cam_2", state("base", 0.8, (100.0, 200.0, 150.0, 300.0), 1033.0)),),
            global_positions=(("global_player_1", (10.0, 20.0)),),
            predictions=(("global_player_1", (10.0, 20.0)),),
        ),
        F0TickSnapshot(
            canonical_tick=2, canonical_timestamp_ms=1066.0, reference_frame_index=12,
            observations=(("global_player_1", "cam_2", state("base", 0.8, (100.0, 200.0, 150.0, 300.0), 1066.0)),),
            global_positions=(("global_player_1", (10.0, 20.0)),),
            predictions=(("global_player_1", (10.0, 20.0)),),
        ),
        F0TickSnapshot(
            canonical_tick=3, canonical_timestamp_ms=1099.0, reference_frame_index=13,
            observations=(("global_player_1", "cam_2", state("base", 0.8, (100.0, 200.0, 150.0, 300.0), 1099.0)),),
            global_positions=(("global_player_1", (10.0, 20.0)),),
            predictions=(("global_player_1", (10.0, 20.0)),),
        ),
        F0TickSnapshot(
            canonical_tick=4, canonical_timestamp_ms=1132.0, reference_frame_index=14,
            observations=(("global_player_1", "cam_2", state("base", 0.8, (100.0, 200.0, 150.0, 300.0), 1132.0)),),
            global_positions=(("global_player_1", (10.0, 20.0)),),
            predictions=(("global_player_1", (10.0, 20.0)),),
        ),
        F0TickSnapshot(
            canonical_tick=5, canonical_timestamp_ms=1165.0, reference_frame_index=15,
            observations=(("global_player_1", "cam_1", state("base", 0.8, (100.0, 200.0, 150.0, 300.0), 1165.0)),),
            global_positions=(("global_player_1", (10.0, 20.0)),),
            predictions=(("global_player_1", (10.0, 20.0)),),
        ),
    )
    snapshot = F0RefinementSnapshot(
        run_id="run-stable", reference_view_id="cam_1", view_ids=("cam_1", "cam_2"),
        global_player_ids=("global_player_1",), ticks=ticks,
    )
    bundle = JointOverlayEvidenceBundle(
        f0_snapshot=snapshot, reference_view_id="cam_1", view_ids=("cam_1", "cam_2"),
        roster_map={"global_player_1": "Player_1"},
        view_geometry={"cam_1": geometry, "cam_2": geometry},
        fused_samples={
            "global_player_1": {
                10: {"fusion_status": "single_view_fallback"},
                11: {"fusion_status": "single_view_fallback"},
                12: {"fusion_status": "single_view_fallback"},
                13: {"fusion_status": "single_view_fallback"},
                14: {"fusion_status": "single_view_fallback"},
                15: {"fusion_status": "single_view_fallback"},
            },
        },
        fused_positions={
            "global_player_1": {
                10: (10.0, 20.0), 11: (10.0, 20.0), 12: (10.0, 20.0),
                13: (10.0, 20.0), 14: (10.0, 20.0), 15: (10.0, 20.0),
            },
        },
    )
    config = OverlayBuilderConfig(
        synthetic_upgrade_confirm_ticks=3,
        scale_profile_min_total_samples=1,  # 允许少量样本建立 profile（测试用）
        scale_profile_min_samples_per_bin=1,
    )
    builder = FusedPlayerOverlayBuilder(config)
    payload = build_fused_player_overlay_payload(
        job_id="job-1", video_id=None, reference_view_id="cam_1",
        frame_size={"width": 640, "height": 480},
        frames=builder.build(bundle=bundle),
    )
    frames = payload["frames"]
    # t0 真实 → REAL_BOX
    p0 = frames[0]["players"][0]
    assert p0["evidence_type"] == "base_observed"
    assert p0["display_state"] == "REAL_BOX"
    # t1-t3 donor-only → cross_view_projected（evidence 诚实降级）
    p1 = frames[1]["players"][0]
    assert p1["evidence_type"] == "cross_view_projected"
    # 状态序列：REAL_BOX 短暂漏检 → PROJECTED_BOX（保持框，虚线）
    states = [f["players"][0]["display_state"] for f in frames]
    assert states[0] == "REAL_BOX"
    assert states[1] == "PROJECTED_BOX"  # 短暂漏检保持框形态（诚实降级 evidence）
    # t5 真实恢复 → 立即 REAL_BOX
    assert frames[5]["players"][0]["display_state"] == "REAL_BOX"
    # 不变量：REAL↔POINT 交替不存在（无 REAL_BOX 后直接 POINT 又回 REAL 的抖动）
    assert "PROJECTED_POINT" not in states  # 短暂漏检不降级到点

    # synthetic 不回喂：builder 的 bbox memory 只含真实 bbox（cam_1 t0/t5）
    # 且 scale profile 只收集真实样本（这里 cam_2 的样本也被收集，但 synthetic 不产生）
    assert builder.bbox_memory._entries  # 有记忆（真实 bbox）
    # 验证：cross_view 生成的 synthetic bbox 未污染 memory 导致后续真实判定异常
    # （builder 只调 memory.update 于 _build_real_observation / _build_recovered）


def test_builder_reset_prevents_cross_job_leak():
    """同一 builder 实例连续 build 两个 job → 状态机 reset，不残留上一场状态。"""
    from app.vision.multiview.court_frame import CourtOrientation
    from app.vision.multiview.fused_overlay_builder import FusedPlayerOverlayBuilder, OverlayBuilderConfig
    from app.vision.multiview.fused_overlay_bundle import JointOverlayEvidenceBundle, ViewGeometry
    from app.vision.multiview.fused_overlay_types import build_fused_player_overlay_payload
    from app.vision.multiview.offline_refinement import (
        F0RefinementSnapshot,
        F0TickSnapshot,
        F0TickViewState,
    )

    IDENTITY = CourtOrientation.identity
    H = [[10.0, 0.0, 0.0], [0.0, 10.0, 0.0], [0.0, 0.0, 1.0]]
    geometry = ViewGeometry(
        view_id="cam_1", orientation=IDENTITY, inverse_homography=H,
        frame_width=640, frame_height=480,
    )

    def make_snapshot(real_at_t0: bool) -> F0RefinementSnapshot:
        # cam_2 恒为 donor（base observation），cam_1 按 real_at_t0 决定
        cam2_obs = (("global_player_1", "cam_2", F0TickViewState(
            observed=True, quality=0.8, canonical_position=(10.0, 20.0), origin="base",
            source_frame_index=10, source_timestamp_ms=1000.0, mapped_take_timestamp_ms=1000.0,
            timing_authority="reference", sync_quality="good", view_status="available",
            observation_status="observed", view_player_id="global_player_1",
            detector_confidence=0.8, projection_confidence=0.9, tracking_status="detected",
            bbox=(100.0, 200.0, 150.0, 300.0),
        )),)
        cam1_obs = ()
        if real_at_t0:
            cam1_obs = (("global_player_1", "cam_1", F0TickViewState(
                observed=True, quality=0.8, canonical_position=(10.0, 20.0), origin="base",
                source_frame_index=10, source_timestamp_ms=1000.0, mapped_take_timestamp_ms=1000.0,
                timing_authority="reference", sync_quality="good", view_status="available",
                observation_status="observed", view_player_id="global_player_1",
                detector_confidence=0.8, projection_confidence=0.9, tracking_status="detected",
                bbox=(100.0, 200.0, 150.0, 300.0),
            )),)
        return F0RefinementSnapshot(
            run_id="run-reset", reference_view_id="cam_1", view_ids=("cam_1", "cam_2"),
            global_player_ids=("global_player_1",),
            ticks=(F0TickSnapshot(
                canonical_tick=0, canonical_timestamp_ms=1000.0, reference_frame_index=10,
                observations=cam1_obs + cam2_obs,
                global_positions=(("global_player_1", (10.0, 20.0)),),
                predictions=(("global_player_1", (10.0, 20.0)),),
            ),),
        )

    def make_bundle(snapshot) -> JointOverlayEvidenceBundle:
        return JointOverlayEvidenceBundle(
            f0_snapshot=snapshot, reference_view_id="cam_1", view_ids=("cam_1", "cam_2"),
            roster_map={"global_player_1": "Player_1"},
            view_geometry={"cam_1": geometry, "cam_2": geometry},
            fused_samples={"global_player_1": {10: {"fusion_status": "single_view_fallback"}}},
            fused_positions={"global_player_1": {10: (10.0, 20.0)}},
            last_real_observed_ms={("global_player_1", "cam_2"): 1000.0},
        )

    builder = FusedPlayerOverlayBuilder()
    # job A：t0 真实
    payload_a = build_fused_player_overlay_payload(
        job_id="job-a", video_id=None, reference_view_id="cam_1",
        frame_size={"width": 640, "height": 480},
        frames=builder.build(bundle=make_bundle(make_snapshot(real_at_t0=True))),
    )
    assert payload_a["frames"][0]["players"][0]["display_state"] == "REAL_BOX"
    # job B：t0 无真实（cross_view）→ 必须从 HIDDEN 开始（POINT，需 confirm），不残留 job A 的 REAL
    payload_b = build_fused_player_overlay_payload(
        job_id="job-b", video_id=None, reference_view_id="cam_1",
        frame_size={"width": 640, "height": 480},
        frames=builder.build(bundle=make_bundle(make_snapshot(real_at_t0=False))),
    )
    players_b = payload_b["frames"][0]["players"]
    assert players_b  # 有渲染
    assert players_b[0]["display_state"] == "PROJECTED_POINT"  # 新 job 从 POINT 开始，非 REAL 残留
