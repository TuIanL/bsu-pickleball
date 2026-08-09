"""offline_refinement(F1)单元测试。

覆盖:窗口挖掘 / tick 两级资格(source frame 存在 + per-tick donor)/ 离线重检
(pre-gate + donor gate)/ RecoveryTracklet / RefinementAcceptanceGate。
"""

from __future__ import annotations

from app.schemas.tracking import Detection
from app.vision.multiview.court_frame import CourtOrientation
from app.vision.multiview.guidance import invert_homography
from app.vision.multiview.offline_refinement import (
    F0TickViewState,
    OfflineRecovery,
    RecoveredViewObservation,
    RecoveryTickPlan,
    RecoveryTracklet,
    RefinementAcceptanceGate,
    RefinementMetrics,
    build_recovery_tick_plans,
    mine_recovery_windows,
)

IDENTITY = CourtOrientation.identity
# image*0.05 → court
SCALE_H = [[0.05, 0.0, 0.0], [0.0, 0.05, 0.0], [0.0, 0.0, 1.0]]


def _obs(quality=0.9, observed=True, origin="base", pos=(5.0, 8.0)):
    return F0TickViewState(observed=observed, quality=quality, canonical_position=pos, origin=origin)


# ---- 窗口挖掘 ----------------------------------------------------------------


def test_mine_window_donor_strong_target_weak():
    f0 = {
        "g1": {
            "cam_1": {t: _obs(observed=False, quality=0.0, pos=None) for t in range(3)},
            "cam_2": {t: _obs(quality=0.9) for t in range(3)},
        }
    }
    windows = mine_recovery_windows(f0, missing_after_ticks=3, donor_min_quality=0.5)
    assert len(windows) == 1
    assert windows[0].target_view == "cam_1"
    assert windows[0].donor_view == "cam_2"


def test_mine_no_window_both_weak():
    f0 = {
        "g1": {
            "cam_1": {t: _obs(observed=False, quality=0.0, pos=None) for t in range(3)},
            "cam_2": {t: _obs(observed=False, quality=0.0, pos=None) for t in range(3)},
        }
    }
    assert mine_recovery_windows(f0, missing_after_ticks=3, donor_min_quality=0.5) == []


# ---- tick 资格 --------------------------------------------------------------


def test_tick_plan_requires_source_frame_and_base_donor():
    f0 = {
        "g1": {
            "cam_1": {0: _obs(observed=False, quality=0.0, pos=None)},
            "cam_2": {0: _obs(quality=0.9)},
        }
    }
    # donor 为 predicted → 不可 recover
    f0_pred = {
        "g1": {
            "cam_1": {0: _obs(observed=False, quality=0.0, pos=None)},
            "cam_2": {0: _obs(origin="predicted", quality=0.9)},
        }
    }
    from app.vision.multiview.offline_refinement import RecoveryWindow

    # source frame 不存在 → 无 plan
    w = RecoveryWindow("g1", "cam_1", "cam_2", 0, 0, [])
    build_recovery_tick_plans(w, f0, f0_source_frames={"cam_1": {}, "cam_2": {}}, f0_global_positions={})
    assert w.ticks == []

    # donor predicted → 无 plan
    w2 = RecoveryWindow("g1", "cam_1", "cam_2", 0, 0, [])
    build_recovery_tick_plans(w2, f0_pred, f0_source_frames={"cam_1": {0: 10}, "cam_2": {0: 20}}, f0_global_positions={})
    assert w2.ticks == []

    # target frame 存在 + donor base → 生成 plan
    w3 = RecoveryWindow("g1", "cam_1", "cam_2", 0, 0, [])
    build_recovery_tick_plans(w3, f0, f0_source_frames={"cam_1": {0: 10}, "cam_2": {0: 20}}, f0_global_positions={})
    assert len(w3.ticks) == 1
    assert w3.ticks[0].target_source_frame_index == 10


# ---- 离线重检 ---------------------------------------------------------------


def test_offline_recovery_pre_gate_and_donor_center():
    detector = type("D", (), {
        "detect_regions": lambda self, frame, regions: [
            Detection(bbox=[100.0, 150.0, 120.0, 200.0], confidence=0.8, class_name="person")
        ],
    })()
    rec = OfflineRecovery(homography=SCALE_H, frame_width=640, frame_height=480, max_residual_ft=3.0)
    plan = RecoveryTickPlan(
        tick_id="t", take_timestamp_ms=0.0, global_player_id="g1", target_view="cam_1",
        target_source_frame_index=10, target_source_timestamp_ms=0.0, donor_view="cam_2",
        donor_source_frame_index=20, donor_canonical_position=(5.0, 8.0), donor_quality=0.9,
        f0_global_position=(5.0, 8.0),
    )
    tracklet = RecoveryTracklet("w1")
    # bbox [100,150,120,200] → foot(110,200) → court(5.5,10) vs donor(5,8) → residual ~2.1 < 3 → accepted
    recovered = rec.recover(
        plan=plan, frame=object(), detector=detector,
        inverse_homography=invert_homography(SCALE_H), orientation=IDENTITY,
        forward_position=(5.0, 8.0), backward_position=(5.2, 8.1), tracklet=tracklet,
    )
    assert recovered is not None
    assert recovered.detection_origin == "offline_refinement"
    assert tracklet.consecutive_hits == 1


def test_offline_recovery_rejects_far_candidate():
    detector = type("D", (), {
        "detect_regions": lambda self, frame, regions: [
            Detection(bbox=[300.0, 150.0, 330.0, 300.0], confidence=0.8, class_name="person")
        ],
    })()
    rec = OfflineRecovery(homography=SCALE_H, frame_width=640, frame_height=480, max_residual_ft=3.0)
    plan = RecoveryTickPlan(
        tick_id="t", take_timestamp_ms=0.0, global_player_id="g1", target_view="cam_1",
        target_source_frame_index=10, target_source_timestamp_ms=0.0, donor_view="cam_2",
        donor_source_frame_index=20, donor_canonical_position=(5.0, 8.0), donor_quality=0.9,
        f0_global_position=(5.0, 8.0),
    )
    # foot(315,300) → court(15.75,15) vs donor(5,8) → residual ~12 > 3 → 拒绝
    assert rec.recover(
        plan=plan, frame=object(), detector=detector,
        inverse_homography=invert_homography(SCALE_H), orientation=IDENTITY,
    ) is None


# ---- RefinementAcceptanceGate -----------------------------------------------


def test_acceptance_gate_accepts_good_refinement():
    gate = RefinementAcceptanceGate()
    f0 = RefinementMetrics(eligible_coverage=0.8, jump_count=1, conflict_count=0)
    f1 = RefinementMetrics(
        eligible_coverage=0.9, jump_count=1, conflict_count=0, recovered_count=2,
        recovered_residual_p50=1.5,
    )
    v = gate.decide(f0, f1)
    assert v.accepted
    assert v.reason == "accepted"


def test_acceptance_gate_rejects_when_no_recovered():
    gate = RefinementAcceptanceGate()
    v = gate.decide(RefinementMetrics(), RefinementMetrics(recovered_count=0))
    assert not v.accepted
    assert v.reason == "no_recovered_observations"


def test_acceptance_gate_rejects_on_donor_inconsistency():
    gate = RefinementAcceptanceGate()
    f0 = RefinementMetrics(eligible_coverage=0.8, jump_count=1)
    f1 = RefinementMetrics(
        eligible_coverage=0.9, jump_count=1, recovered_count=1,
        donor_inconsistency_count=1,
    )
    v = gate.decide(f0, f1)
    assert not v.accepted
    assert v.reason == "donor_inconsistent"


def test_acceptance_gate_rejects_on_coverage_decrease():
    gate = RefinementAcceptanceGate()
    f0 = RefinementMetrics(eligible_coverage=0.9, jump_count=1)
    f1 = RefinementMetrics(eligible_coverage=0.7, jump_count=1, recovered_count=1)
    assert not gate.decide(f0, f1).accepted
