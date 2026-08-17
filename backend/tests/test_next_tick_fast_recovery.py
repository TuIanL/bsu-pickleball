"""next-tick fast player recovery 单元测试。

覆盖（tasks 5.1 / 5.2）：
- `record_attempt` 幂等（同 tick 重复调用不重复记账）；
- available-miss 记账（attempted available + 无 AssociationUpdate → 递增；有 → 清零）；
- `is_target_recovery_eligible`（visibility age / fast path / 双满足 / 开关关闭）；
- guidance fast path（misses>=1 且 observed 触发；无 miss 不触发；cooldown 仍生效；
  donor/uncertainty 门限仍生效；fast_recovery_enabled=false 回退现状）；
- `GuidanceDecision.trigger_source/reason` 分离（fast path 有资格但 donor 拒绝
  → trigger_source=available_miss, reason=donor_low_quality）。
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.vision.multiview.court_frame import CourtOrientation
from app.vision.multiview.global_state import ViewBinding
from app.vision.multiview.guidance import CrossViewGuidancePolicy, GuidanceGenerator
from app.vision.multiview.recovery_config import is_target_recovery_eligible

IDENTITY_ORIENTATION = CourtOrientation.identity

TEST_INVERSE_HOMOGRAPHY = [
    [10.0, 0.0, 0.0],
    [0.0, 10.0, 0.0],
    [0.0, 0.0, 1.0],
]

POLICY = CrossViewGuidancePolicy(
    base_roi_margin_px=40.0,
    uncertainty_to_px_scale=12.0,
    max_roi_margin_px=160.0,
    min_donor_quality=0.55,
    donor_max_age_ms=300.0,
    guidance_cooldown_ticks=3,
    fast_recovery_enabled=True,
)




def _mvsync():
    """MultiViewSyncCalibration with identity mapping for cam_2."""
    from app.vision.multiview.sync import MultiViewSyncCalibration, SyncCalibration

    sc = SyncCalibration(
        reference_camera="cam_1", camera_id="cam_2",
        offset_seconds=0.0, rate=1.0,
        drift_ppm=0.0, residual_rms_seconds=0.0, anchor_count=1, quality="good",
    )
    return MultiViewSyncCalibration(reference_camera="cam_1", mappings={"cam_2": sc})



# ---- 1. record_attempt：幂等 / 递增 / 清零 -----------------------------------


def test_record_attempt_increments_and_clears() -> None:
    binding = ViewBinding(visibility="observed")
    binding.record_attempt(observed=False, take_ms=7000.0, tick=210)
    assert binding.consecutive_available_misses == 1
    assert binding.last_attempted_tick == 210
    assert binding.last_attempted_take_timestamp_ms == 7000.0

    binding.record_attempt(observed=False, take_ms=7200.0, tick=211)
    assert binding.consecutive_available_misses == 2

    binding.record_attempt(observed=True, take_ms=7300.0, tick=212)
    assert binding.consecutive_available_misses == 0
    assert binding.last_observed_tick == 212
    assert binding.last_attempted_tick == 212


def test_record_attempt_idempotent_same_tick() -> None:
    binding = ViewBinding(visibility="observed")
    binding.record_attempt(observed=False, take_ms=7000.0, tick=210)
    binding.record_attempt(observed=False, take_ms=7100.0, tick=210)  # 幂等
    assert binding.consecutive_available_misses == 1
    assert binding.last_attempted_take_timestamp_ms == 7000.0  # 不被第二次覆盖


# ---- 2. is_target_recovery_eligible -----------------------------------------


def test_predicate_visibility_age_always_eligible() -> None:
    for vis in ("weak", "missing", "lost"):
        assert is_target_recovery_eligible(ViewBinding(visibility=vis), False) is True
        assert is_target_recovery_eligible(ViewBinding(visibility=vis), True) is True


def test_predicate_fast_path_requires_enabled() -> None:
    binding = ViewBinding(visibility="observed", consecutive_available_misses=1)
    assert is_target_recovery_eligible(binding, True) is True
    assert is_target_recovery_eligible(binding, False) is False


def test_predicate_observed_no_miss_not_eligible() -> None:
    binding = ViewBinding(visibility="observed", consecutive_available_misses=0)
    assert is_target_recovery_eligible(binding, True) is False
    assert is_target_recovery_eligible(None, True) is False


# ---- 3. guidance fast path 触发 ----------------------------------------------


def _make_state(*, visibility: str = "observed", misses: int = 0) -> "object":
    return type(
        "S",
        (),
        {
            "global_player_id": "global_player_1",
            "lifecycle": "confirmed",
            "cross_view_anchored": True,
            "view_bindings": {"cam_1": ViewBinding(visibility=visibility, consecutive_available_misses=misses)},
        },
    )()


def _donor(*, quality: float = 0.8, age_ms: float = 100.0) -> "object":
    return type(
        "D",
        (),
        {
            "observation_origin": "base",
            "visibility": "observed",
            "last_seen_take_timestamp_ms": 6900.0 if age_ms < 300 else 5000.0,
            "quality": quality,
            "view_player_id": "Player_1",
            "last_source_frame_index": 200,
        },
    )()


def _generate(generator: GuidanceGenerator, *, state, donor=None, now_ms: float = 7000.0, tick: int = 211) -> "object | None":
    return generator.generate(
        global_state=state,
        target_view="cam_1",
        orientation=IDENTITY_ORIENTATION,
        inverse_homography=TEST_INVERSE_HOMOGRAPHY,
        now_take_ms=now_ms,
        tick=tick,
        frame_width=640,
        frame_height=480,
        prediction=(10.0, 20.0, 2.0),
        donor_view="cam_2" if donor is not None else None,
        donor_binding=donor,
        target_frame_available=True,
        strict_donor=donor is not None,
    )


def test_fast_path_triggers_when_observed_with_miss() -> None:
    generator = GuidanceGenerator(policy=POLICY)
    result = _generate(generator, state=_make_state(visibility="observed", misses=1))
    assert result is not None
    decision = generator.last_decisions[-1]
    assert decision.status == "generated"
    assert decision.trigger_source == "available_miss"


def test_no_miss_observed_not_triggered() -> None:
    generator = GuidanceGenerator(policy=POLICY)
    result = _generate(generator, state=_make_state(visibility="observed", misses=0))
    assert result is None
    decision = generator.last_decisions[-1]
    assert decision.status == "not_eligible"
    assert decision.reason == "target_not_missing"
    assert decision.trigger_source is None


def test_visibility_age_trigger_source_priority() -> None:
    generator = GuidanceGenerator(policy=POLICY)
    result = _generate(generator, state=_make_state(visibility="weak", misses=1))
    assert result is not None
    decision = generator.last_decisions[-1]
    assert decision.trigger_source == "visibility_age"


def test_fast_path_disabled_falls_back() -> None:
    policy = CrossViewGuidancePolicy(fast_recovery_enabled=False)
    generator = GuidanceGenerator(policy=policy)
    result = _generate(generator, state=_make_state(visibility="observed", misses=1))
    assert result is None
    assert generator.last_decisions[-1].reason == "target_not_missing"


def test_fast_path_eligible_but_donor_rejected_separates_trigger_and_reason() -> None:
    generator = GuidanceGenerator(policy=POLICY)
    result = _generate(
        generator,
        state=_make_state(visibility="observed", misses=1),
        donor=_donor(quality=0.31),  # 低于 min_donor_quality=0.55
    )
    assert result is None
    decision = generator.last_decisions[-1]
    assert decision.trigger_source == "available_miss"
    assert decision.reason == "donor_low_quality"


def test_cooldown_still_effective_for_fast_path() -> None:
    generator = GuidanceGenerator(policy=POLICY)
    first = _generate(generator, state=_make_state(visibility="observed", misses=1), tick=210)
    assert first is not None
    # cooldown 仅在 ROI 真正调用后 commit 消费（与现有语义一致）
    generator.commit(first, 210)
    # 同一 (global, view) 在 cooldown 内再触发 → 被 cooldown 拦截
    second = _generate(generator, state=_make_state(visibility="observed", misses=1), tick=211)
    assert second is None
    assert generator.last_decisions[-1].reason == "cooldown"
    assert generator.last_decisions[-1].trigger_source == "available_miss"


def test_uncertainty_gate_still_effective_for_fast_path() -> None:
    generator = GuidanceGenerator(policy=POLICY)
    state = _make_state(visibility="observed", misses=1)
    result = generator.generate(
        global_state=state,
        target_view="cam_1",
        orientation=IDENTITY_ORIENTATION,
        inverse_homography=TEST_INVERSE_HOMOGRAPHY,
        now_take_ms=7000.0,
        tick=211,
        frame_width=640,
        frame_height=480,
        prediction=(10.0, 20.0, 99.0),  # 超 max_uncertainty_ft=8
        strict_donor=False,
    )
    assert result is None
    assert generator.last_decisions[-1].reason == "prediction_uncertain"


# ---- 4. 集成测试：ledger 接入 + 幽灵 guidance 消除（tasks 5.3）---------------


def test_joint_run_records_ledger_and_syncs_opportunity(tmp_path):
    """端到端：fast path 触发的 guidance 必须同步建立 episode/opportunity。"""
    import numpy as np

    from app.services.frame_timing_provider import FrameTiming
    from app.vision.multiview.analysis_clock import CanonicalAnalysisClock
    from app.vision.multiview.association_global import GlobalPlayerAssociator
    from app.vision.multiview.global_state import GlobalPlayerRegistry
    from app.vision.multiview.guidance import CrossViewGuidancePolicy, GuidanceGenerator
    from app.vision.multiview.multiview_joint_run import MultiViewJointRun
    from app.vision.multiview.recovery_config import P1OnlineRecoveryConfig

    IDENTITY = CourtOrientation.identity
    H = np.array([[10.0, 0.0, 0.0], [0.0, 10.0, 0.0], [0.0, 0.0, 1.0]])

    # 预置 registry：cam_1 binding observed + 1 available miss → fast path 可触发
    registry = GlobalPlayerRegistry(anchored_dual_view_count=2, confirm_dual_view_count=2)
    # 先吸收一次测量，使 estimator 有状态（predict_all 才有预测）
    registry.absorb_measurement("global_player_1", 10.0, 20.0, 0.0)
    state = registry.ensure("global_player_1")
    state.lifecycle = "confirmed"
    state.cross_view_anchored = True
    state.roster_status = "confirmed"
    state.association_eligible = True
    cam1_binding = ViewBinding(
        view_player_id="Player_1", visibility="observed", consecutive_available_misses=1,
        last_seen_take_timestamp_ms=0.0,
    )
    cam2_binding = ViewBinding(
        view_player_id="Player_1", visibility="observed", quality=0.9,
        last_seen_take_timestamp_ms=0.0,
    )
    state.view_bindings = {"cam_1": cam1_binding, "cam_2": cam2_binding}

    class FakeRuntime:
        def __init__(self, view_id):
            self.view_id = view_id
            self.calls = []

        def step(self, source_frame_index, timestamp_s, guidance=()):
            self.calls.append((source_frame_index, list(guidance)))
            return type(
                "R",
                (),
                {"frame_index": source_frame_index, "frame_positions": [], "frame_detections": []},
            )()

    cam1 = FakeRuntime("cam_1")
    cam2 = FakeRuntime("cam_2")
    clock = CanonicalAnalysisClock(
        reference_view_id="cam_1", secondary_view_id="cam_2",
        secondary_frames=[FrameTiming(i, i / 30.0) for i in range(30)],
        sync=_mvsync(),
        secondary_camera_id="cam_2",
    )
    policy = CrossViewGuidancePolicy(fast_recovery_enabled=True)
    gen = GuidanceGenerator(policy)
    recovery_config = P1OnlineRecoveryConfig(enabled=True, fast_recovery_enabled=True)
    run = MultiViewJointRun(
        run_id="mvr-fast", capture_take_id="take", reference_view_id="cam_1",
        clock=clock, runtimes={"cam_1": cam1, "cam_2": cam2},
        registry=registry, associator=GlobalPlayerAssociator(registry, max_association_distance_ft=3.0),
        guidance_generator=gen, orientations={"cam_1": IDENTITY, "cam_2": IDENTITY},
        inverse_homography=np.linalg.inv(H), frame_width=640, frame_height=480,
        recovery_config=recovery_config,
    )
    out = run.run(reference_frame_count=6, reference_fps=30.0)
    # guidance 生成（fast path）：cam_1 有 1 available miss + donor cam_2 合格
    assert gen.last_decisions
    generated = [d for d in gen.last_decisions if d.status == "generated"]
    # 至少一次 guidance 生成（fast path 或 visibility age）
    assert generated, "fast path 应生成至少一次 guidance"
    # 幽灵 guidance 检查：若 guidance 生成，opportunity 必须同步计入
    if generated:
        assert run.recovery_funnel.get("recovery_opportunity_count", 0) >= 1, (
            "guidance 已生成但 opportunity 未计入（幽灵 guidance）"
        )
        assert run.recovery_funnel.get("guidance_generated_count", 0) >= 1
    # display diagnostics 产物存在且含 available_miss_streak
    assert out.display_diagnostics_payload is not None
    rows = out.display_diagnostics_payload.get("rows", [])
    if rows:
        for row in rows:
            assert "available_miss_streak" in row
    # 核心结果不破坏
    assert out.trajectory["schema_version"] == "fused_player_trajectory.v2"


def test_joint_run_fast_path_disabled_no_fast_guidance():
    """fast_recovery_enabled=false 时 observed+miss 不触发（回退现状）。"""
    import numpy as np

    from app.services.frame_timing_provider import FrameTiming
    from app.vision.multiview.analysis_clock import CanonicalAnalysisClock
    from app.vision.multiview.association_global import GlobalPlayerAssociator
    from app.vision.multiview.global_state import GlobalPlayerRegistry
    from app.vision.multiview.guidance import CrossViewGuidancePolicy, GuidanceGenerator
    from app.vision.multiview.multiview_joint_run import MultiViewJointRun
    from app.vision.multiview.recovery_config import P1OnlineRecoveryConfig

    IDENTITY = CourtOrientation.identity
    H = np.array([[10.0, 0.0, 0.0], [0.0, 10.0, 0.0], [0.0, 0.0, 1.0]])

    registry = GlobalPlayerRegistry(anchored_dual_view_count=2, confirm_dual_view_count=2)
    registry.absorb_measurement("global_player_1", 10.0, 20.0, 0.0)
    state = registry.ensure("global_player_1")
    state.lifecycle = "confirmed"
    state.cross_view_anchored = True
    state.roster_status = "confirmed"
    state.association_eligible = True
    state.view_bindings = {
        "cam_1": ViewBinding(view_player_id="Player_1", visibility="observed", consecutive_available_misses=1),
        "cam_2": ViewBinding(view_player_id="Player_1", visibility="observed", quality=0.9),
    }

    class FakeRuntime:
        def __init__(self, view_id):
            self.view_id = view_id
            self.calls = []

        def step(self, source_frame_index, timestamp_s, guidance=()):
            self.calls.append((source_frame_index, list(guidance)))
            return type(
                "R", (), {"frame_index": source_frame_index, "frame_positions": [], "frame_detections": []},
            )()

    cam1 = FakeRuntime("cam_1")
    cam2 = FakeRuntime("cam_2")
    clock = CanonicalAnalysisClock(
        reference_view_id="cam_1", secondary_view_id="cam_2",
        secondary_frames=[FrameTiming(i, i / 30.0) for i in range(30)],
        sync=_mvsync(),
        secondary_camera_id="cam_2",
    )
    gen = GuidanceGenerator(CrossViewGuidancePolicy(fast_recovery_enabled=False))
    run = MultiViewJointRun(
        run_id="mvr-nofast", capture_take_id="take", reference_view_id="cam_1",
        clock=clock, runtimes={"cam_1": cam1, "cam_2": cam2},
        registry=registry, associator=GlobalPlayerAssociator(registry, max_association_distance_ft=3.0),
        guidance_generator=gen, orientations={"cam_1": IDENTITY, "cam_2": IDENTITY},
        inverse_homography=np.linalg.inv(H), frame_width=640, frame_height=480,
        recovery_config=P1OnlineRecoveryConfig(enabled=True, fast_recovery_enabled=False),
    )
    out = run.run(reference_frame_count=6, reference_fps=30.0)
    # observed + misses=1 且 fast 关闭 → 不应生成 guidance
    fast_generated = [
        d for d in gen.last_decisions
        if d.status == "generated" and d.trigger_source == "available_miss"
    ]
    assert not fast_generated, "fast_recovery_enabled=false 时不应有 available_miss 触发的 guidance"
    assert out.trajectory["schema_version"] == "fused_player_trajectory.v2"
