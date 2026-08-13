"""offline_refinement(F1)单元测试。

覆盖:窗口挖掘 / tick 两级资格(source frame 存在 + per-tick donor)/ 离线重检
(pre-gate + donor gate)/ RecoveryTracklet / RefinementAcceptanceGate。
"""

from __future__ import annotations

from app.schemas.tracking import Detection
from app.vision.multiview.court_frame import CourtOrientation
from app.vision.multiview.guidance import invert_homography
from app.vision.multiview.offline_refinement import (
    F0RefinementSnapshot,
    F0TickSnapshot,
    F0TickViewState,
    OfflineRecovery,
    RefinementConfigSnapshot,
    RefinementViewContext,
    RecoveredViewObservation,
    RecoveryTickPlan,
    RecoveryTracklet,
    RefinementAcceptanceGate,
    RefinementMetrics,
    build_recovery_tick_plans,
    mine_recovery_windows,
    refusion_frozen_snapshot,
    run_offline_refinement,
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


def test_mine_window_requires_contiguous_ticks_and_records_unavailable_frames():
    f0 = {
        "g1": {
            "cam_1": {
                0: _obs(observed=False, quality=0.0, pos=None),
                2: _obs(observed=False, quality=0.0, pos=None),
                3: _obs(observed=False, quality=0.0, pos=None),
            },
            "cam_2": {0: _obs(quality=0.9), 2: _obs(quality=0.9), 3: _obs(quality=0.9)},
        }
    }
    windows = mine_recovery_windows(f0, missing_after_ticks=2, donor_min_quality=0.5)
    assert len(windows) == 1
    assert windows[0].start_tick == 2
    assert windows[0].end_tick == 3


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


# ---- re-fusion -------------------------------------------------------------


def test_refuse_f1_merges_recovered_and_original_strong_priority():
    from app.vision.multiview.offline_refinement import RecoveredViewObservation, refuse_f1
    from app.vision.multiview.joint_artifact import FusedSample

    f0 = [FusedSample(
        global_player_id="g1", take_timestamp_ms=100.0, reference_frame_index=3,
        x_ft=5.0, y_ft=8.0, fusion_status="dual_observed", metric_eligible=True,
    )]
    recovered = [RecoveredViewObservation(
        view_id="cam_1", take_timestamp_ms=200.0, source_frame_index=6,
        canonical_x_ft=6.0, canonical_y_ft=9.0, bbox=[1, 2, 3, 4], confidence=0.8,
        global_player_id="g1",
    )]
    f1 = refuse_f1(f0, recovered)
    assert len(f1) == 2
    assert f1[1].observation_origin == "offline_refinement"
    # original 强观测优先:同一 global 同 tick 的 recovered 不追加
    dup = [RecoveredViewObservation(
        view_id="cam_1", take_timestamp_ms=100.0, source_frame_index=3,
        canonical_x_ft=9.0, canonical_y_ft=9.0, bbox=[1, 2, 3, 4], confidence=0.8,
        global_player_id="g1",
    )]
    assert len(refuse_f1(f0, dup)) == 1


def test_f0_snapshot_round_trip_is_immutable_and_preserves_canonical_timing():
    snapshot = F0RefinementSnapshot(
        run_id="run-1",
        capture_take_id="take-1",
        global_player_ids=("g1",),
        config_snapshot={"nested": {"min_donor_quality": 0.73}},
        ticks=(
            F0TickSnapshot(
                canonical_tick=7,
                canonical_timestamp_ms=1234.5,
                reference_frame_index=70,
                observations=(
                    (
                        "g1",
                        "cam_1",
                        F0TickViewState(
                            observed=False,
                            quality=0.0,
                            origin="missing",
                            source_frame_index=701,
                            source_timestamp_ms=2334.5,
                            mapped_take_timestamp_ms=1234.5,
                            view_status="available",
                            observation_status="missing",
                        ),
                    ),
                    (
                        "g1",
                        "cam_2",
                        F0TickViewState(
                            observed=True,
                            quality=0.9,
                            canonical_position=(5.0, 8.0),
                            source_frame_index=702,
                            source_timestamp_ms=2335.0,
                            mapped_take_timestamp_ms=1234.5,
                            timing_authority="source_pts",
                        ),
                    ),
                ),
                global_positions=(("g1", (5.0, 8.0)),),
            ),
        ),
    )
    payload = snapshot.to_dict()
    restored = F0RefinementSnapshot.from_dict(payload)
    assert restored.tick(7).canonical_timestamp_ms == 1234.5
    assert restored.state_for("g1", "cam_1", 7).source_frame_index == 701
    assert restored.state_for("g1", "cam_2", 7).mapped_take_timestamp_ms == 1234.5
    try:
        snapshot.config_snapshot["nested"] = {}  # type: ignore[index]
    except TypeError:
        pass
    else:
        raise AssertionError("F0 config snapshot must be immutable")


def _context(view_id, homography, detector, width, height):
    return RefinementViewContext(
        view_id=view_id,
        frame_provider=lambda _index: object(),
        detector=detector,
        homography=homography,
        inverse_homography=invert_homography(homography),
        orientation=IDENTITY,
        frame_width=width,
        frame_height=height,
        timing_metadata={"authority": "source_pts"},
    )


def test_bidirectional_target_recovery_uses_target_view_contexts_and_refuses_append_fusion():
    cam1_detector = type("D1", (), {
        "detect_regions": lambda self, frame, regions: [
            Detection(bbox=[100.0, 150.0, 120.0, 200.0], confidence=0.8, class_name="person")
        ],
    })()
    cam2_detector = type("D2", (), {
        "detect_regions": lambda self, frame, regions: [
            Detection(bbox=[50.0, 80.0, 60.0, 100.0], confidence=0.85, class_name="person")
        ],
    })()
    snapshot = F0RefinementSnapshot(
        global_player_ids=("g1",),
        view_ids=("cam_1", "cam_2"),
        ticks=(
            F0TickSnapshot(
                canonical_tick=3,
                canonical_timestamp_ms=333.25,
                reference_frame_index=30,
                observations=(
                    ("g1", "cam_1", F0TickViewState(False, 0.0, None, "missing", 10, 10.0, 333.25, view_status="available", observation_status="missing")),
                    ("g1", "cam_2", F0TickViewState(True, 0.9, (5.0, 8.0), "base", 20, 20.0, 333.25, timing_authority="source_pts")),
                ),
                global_positions=(("g1", (5.0, 8.0)),),
            ),
        ),
    )
    outcome = run_offline_refinement(
        snapshot=snapshot,
        view_contexts={
            "cam_1": _context("cam_1", SCALE_H, cam1_detector, 640, 480),
            "cam_2": _context("cam_2", [[0.1, 0.0, 0.0], [0.0, 0.1, 0.0], [0.0, 0.0, 1.0]], cam2_detector, 320, 240),
        },
        config=RefinementConfigSnapshot(missing_after_ticks=1, min_donor_quality=0.5),
        reference_view_id="cam_1",
        secondary_view_id="cam_2",
    )
    assert outcome.recovered
    assert outcome.recovered[0].take_timestamp_ms == 333.25
    assert outcome.candidate_samples
    sample = outcome.candidate_samples[0]
    assert sample.fusion_status == "dual_observed"
    assert sample.fusion_status != "offline_refinement"
    assert sample.view_observations["cam_1"]["observation_origin"] == "offline_refinement"
    assert sample.metric_eligible is True


def test_formal_refusion_rejects_predicted_as_metric_and_keeps_original_strong():
    from app.vision.multiview.joint_artifact import FusedSample

    snapshot = F0RefinementSnapshot(
        global_player_ids=("g1",),
        view_ids=("cam_1", "cam_2"),
        ticks=(
            F0TickSnapshot(
                canonical_tick=1,
                canonical_timestamp_ms=100.0,
                reference_frame_index=1,
                observations=(
                    ("g1", "cam_1", F0TickViewState(True, 0.95, (5.0, 8.0), "base", 1, 100.0, 100.0)),
                    ("g1", "cam_2", F0TickViewState(False, 0.0, None, "missing", 2, 100.0, 100.0, observation_status="missing")),
                ),
                global_positions=(("g1", (5.0, 8.0)),),
            ),
        ),
    )
    recovered = [RecoveredViewObservation(
        view_id="cam_1", take_timestamp_ms=100.0, source_frame_index=1,
        canonical_x_ft=7.0, canonical_y_ft=9.0, bbox=[1, 2, 3, 4], confidence=0.9,
        global_player_id="g1", canonical_tick=1, residual_ft=1.0,
    )]
    result = refusion_frozen_snapshot(
        snapshot=snapshot,
        recovered=recovered,
        f0_samples=[FusedSample(
            global_player_id="g1", take_timestamp_ms=100.0, reference_frame_index=1,
            x_ft=5.0, y_ft=8.0, fusion_status="single_view_fallback", metric_eligible=True,
        )],
    )
    assert result.suppressed[0]["reason"] == "suppressed_original_strong_priority"
    assert result.samples[0].x_ft == 5.0
    assert result.samples[0].observation_origin == "base"


def test_original_strong_preservation_uses_snapshot_keys_not_detail_row_count():
    from app.vision.multiview.joint_artifact import FusedSample

    snapshot = F0RefinementSnapshot(
        global_player_ids=("g1",),
        view_ids=("cam_1", "cam_2"),
        ticks=(
            F0TickSnapshot(
                canonical_tick=1,
                canonical_timestamp_ms=100.0,
                reference_frame_index=1,
                observations=(
                    ("g1", "cam_1", F0TickViewState(True, 0.9, (5.0, 8.0), "base")),
                    ("g1", "cam_2", F0TickViewState(False, 0.0, None, "missing")),
                ),
                global_positions=(("g1", (5.0, 8.0)),),
            ),
        ),
    )
    sample = FusedSample(
        global_player_id="g1",
        take_timestamp_ms=100.0,
        reference_frame_index=1,
        x_ft=5.0,
        y_ft=8.0,
        fusion_status="single_view_fallback",
        metric_eligible=True,
        view_observations={
            "cam_1": {
                "view_id": "cam_1",
                "observation_origin": "base",
                "quality": 0.9,
            },
            # Duplicate detail rows must not inflate preservation.
            "cam_2": {
                "view_id": "cam_2",
                "observation_origin": "base",
                "quality": 0.1,
            },
        },
    )
    result = refusion_frozen_snapshot(snapshot=snapshot, recovered=[], f0_samples=[sample])
    assert result.metrics.original_strong_preserved == 1


def test_cam2_target_uses_cam2_context_and_decode_failure_has_no_side_effect():
    seen: list[object] = []

    class Cam2Detector:
        def detect_regions(self, frame, regions):
            seen.append(frame)
            return [Detection(bbox=[100.0, 150.0, 120.0, 200.0], confidence=0.8, class_name="person")]

    plan = RecoveryTickPlan(
        tick_id="g1:cam_2:4",
        take_timestamp_ms=456.75,
        global_player_id="g1",
        target_view="cam_2",
        target_source_frame_index=44,
        target_source_timestamp_ms=1456.75,
        donor_view="cam_1",
        donor_source_frame_index=14,
        donor_canonical_position=(5.0, 8.0),
        donor_quality=0.9,
        f0_global_position=(5.0, 8.0),
        canonical_tick=4,
        target_mapped_take_timestamp_ms=456.75,
        target_timing_authority="source_pts",
    )
    context = _context("cam_2", SCALE_H, Cam2Detector(), 640, 480)
    recovery = OfflineRecovery(view_contexts={"cam_2": context}, max_residual_ft=3.0)
    item = recovery.recover(plan=plan, frame="cam2-frame", tracklet=RecoveryTracklet("w-cam2"))
    assert item is not None
    assert seen == ["cam2-frame"]
    assert item.view_id == "cam_2"
    assert item.take_timestamp_ms == 456.75
    failed_context = RefinementViewContext(
        view_id="cam_2",
        frame_provider=lambda _index: None,
        detector=context.detector,
        homography=SCALE_H,
        inverse_homography=invert_homography(SCALE_H),
        orientation=IDENTITY,
        frame_width=640,
        frame_height=480,
    )
    assert OfflineRecovery(view_contexts={"cam_2": failed_context}).recover(plan=plan, frame=None) is None


def test_offline_recovery_uses_rotated_target_geometry_and_target_resolution():
    """A rotated, smaller target view must gate in local space and recover canonical coordinates."""
    seen_regions: list[tuple[float, float, float, float]] = []

    class RotatedDetector:
        def detect_regions(self, _frame, regions):
            seen_regions.extend(regions)
            # footpoint (150, 360) -> target-local (15, 36) -> canonical (5, 8)
            return [Detection(bbox=[140.0, 320.0, 160.0, 360.0], confidence=0.82, class_name="person")]

    rotated_h = [[0.1, 0.0, 0.0], [0.0, 0.1, 0.0], [0.0, 0.0, 1.0]]
    context = RefinementViewContext(
        view_id="cam_2",
        frame_provider=None,
        detector=RotatedDetector(),
        homography=rotated_h,
        inverse_homography=invert_homography(rotated_h),
        orientation=CourtOrientation.rotate_180,
        frame_width=320,
        frame_height=400,
    )
    plan = RecoveryTickPlan(
        tick_id="g1:cam_2:5",
        take_timestamp_ms=512.25,
        global_player_id="g1",
        target_view="cam_2",
        target_source_frame_index=55,
        target_source_timestamp_ms=1512.25,
        donor_view="cam_1",
        donor_source_frame_index=15,
        donor_canonical_position=(5.0, 8.0),
        donor_quality=0.9,
        f0_global_position=(5.0, 8.0),
        canonical_tick=5,
        target_mapped_take_timestamp_ms=512.25,
        target_timing_authority="source_pts",
    )

    item = OfflineRecovery(view_contexts={"cam_2": context}, max_residual_ft=0.5).recover(
        plan=plan,
        frame="cam2-small-frame",
        tracklet=RecoveryTracklet("w-rotated"),
    )
    assert item is not None
    assert (item.canonical_x_ft, item.canonical_y_ft) == (5.0, 8.0)
    assert item.view_id == "cam_2"
    assert seen_regions
    assert seen_regions[0][2] <= 320.0
    assert seen_regions[0][3] <= 400.0


def test_offline_recovery_rejects_candidate_with_wrong_target_geometry():
    """A detector candidate in the wrong geometry must not become F1 evidence."""
    class WrongGeometryDetector:
        def detect_regions(self, _frame, _regions):
            # The supplied identity calibration maps this candidate far from
            # the expected target position (5, 8).
            return [Detection(bbox=[100.0, 150.0, 120.0, 200.0], confidence=0.9, class_name="person")]

    context = _context(
        "cam_1",
        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        WrongGeometryDetector(),
        640,
        480,
    )
    plan = RecoveryTickPlan(
        tick_id="g1:cam_1:6",
        take_timestamp_ms=600.0,
        global_player_id="g1",
        target_view="cam_1",
        target_source_frame_index=60,
        target_source_timestamp_ms=1600.0,
        donor_view="cam_2",
        donor_source_frame_index=20,
        donor_canonical_position=(5.0, 8.0),
        donor_quality=0.9,
        f0_global_position=(5.0, 8.0),
        canonical_tick=6,
    )
    assert OfflineRecovery(view_contexts={"cam_1": context}, max_residual_ft=0.5).recover(
        plan=plan,
        frame="wrong-geometry-frame",
        tracklet=RecoveryTracklet("w-wrong-geometry"),
    ) is None
