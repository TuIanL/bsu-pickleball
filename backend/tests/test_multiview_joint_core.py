"""joint_tracking_v2 核心算法模块单元测试。

覆盖 CanonicalAnalysisClock(source-frame 单调不重复)/ GlobalMotionEstimator /
GlobalPlayerAssociator / CrossViewGuidancePolicy / guided pre-gate / artifact v1/v2 reader。
"""

from __future__ import annotations

import numpy as np
import pytest

from app.core.config import get_settings
from app.schemas.analysis import build_match_context
from app.services.dual_camera_sync import FrameTiming, SyncCalibration
from app.services.frame_timing_provider import FrameTimingProvider
from app.schemas.tracking import Detection
from app.vision.court_view import compute_expanded_detection_roi
from app.vision.multiview.analysis_clock import CanonicalAnalysisClock, FrameSample
from app.vision.multiview.association_global import (
    GlobalPlayerAssociator,
    JointObservation,
)
from app.vision.multiview.court_frame import CourtOrientation
from app.vision.multiview.global_state import (
    GlobalMotionEstimator,
    GlobalPlayerRegistry,
    ViewBinding,
)
from app.vision.multiview.guidance import (
    CrossViewGuidancePolicy,
    GuidanceGenerator,
    invert_homography,
)
from app.vision.multiview.guided_detection import (
    guided_candidate_pre_gate,
    merge_base_and_guided,
)
from app.vision.multiview.joint_artifact import (
    FusedSample,
    load_fused_trajectory,
    write_fused_v2,
)
from app.vision.multiview.joint_types import JointViewInput
from app.vision.multiview.joint_view_runtime import JointViewRuntime
from app.vision.multiview.multiview_joint_run import MultiViewJointRun
from app.vision.multiview.sync import MultiViewSyncCalibration
from app.vision.player_tracking_engine.view_tracking_session import (
    build_view_tracking_config,
    build_view_tracking_session,
)

IDENTITY = CourtOrientation.identity

# 球场缩放 homography:image*0.05 → court
SCALE_H = [[0.05, 0.0, 0.0], [0.0, 0.05, 0.0], [0.0, 0.0, 1.0]]


def _sync(rate: float = 1.0, offset: float = 0.0) -> MultiViewSyncCalibration:
    sc = SyncCalibration(
        reference_camera="cam_1", camera_id="cam_2",
        offset_seconds=offset, rate=rate,
        drift_ppm=0.0, residual_rms_seconds=0.0, anchor_count=1, quality="good",
    )
    return MultiViewSyncCalibration(reference_camera="cam_1", mappings={"cam_2": sc})


# ---- CanonicalAnalysisClock --------------------------------------------------


def test_clock_tick_independent_of_detection():
    cam2_frames = [FrameTiming(i, i / 30.0) for i in range(100)]
    clock = CanonicalAnalysisClock(
        reference_view_id="cam_1", secondary_view_id="cam_2",
        secondary_frames=cam2_frames, sync=None, secondary_camera_id="cam_2",
    )
    bundle = clock.tick(reference_frame_index=7, reference_timestamp_seconds=7 / 30.0)
    # reference 视角始终 available,即使"没有检测到人"(tick 与检测无关)
    assert bundle.frame_status["cam_1"] == "available"
    assert bundle.views["cam_1"].source_frame_index == 7
    # 无 sync → cam_2 unavailable
    assert bundle.frame_status["cam_2"] == "unavailable_no_sync"
    assert bundle.views["cam_2"] is None


def test_clock_single_view_no_sync_is_unavailable():
    cam2_frames = [FrameTiming(i, i / 30.0) for i in range(100)]
    clock = CanonicalAnalysisClock(
        reference_view_id="cam_1", secondary_view_id="cam_2",
        secondary_frames=cam2_frames, sync=None, secondary_camera_id="cam_2",
        max_pairing_error_ms=33.3,
    )
    b = clock.tick(reference_frame_index=0, reference_timestamp_seconds=0.0)
    assert b.frame_status["cam_2"] == "unavailable_no_sync"


def test_clock_same_secondary_frame_not_processed_twice():
    """两个 canonical tick 映射到同一 Cam2 frame → 第二个 no_new_frame(不重复喂 tracker)。"""
    # reference tick 0/0.02/0.04,cam2 30fps(0/0.033/0.067)
    cam2_frames = [FrameTiming(i, i / 30.0) for i in range(100)]
    clock = CanonicalAnalysisClock(
        reference_view_id="cam_1", secondary_view_id="cam_2",
        secondary_frames=cam2_frames, sync=_sync(rate=1.0, offset=0.0),
        secondary_camera_id="cam_2", max_pairing_error_ms=33.3,
    )
    t0 = clock.tick(reference_frame_index=0, reference_timestamp_seconds=0.0)        # → f0
    t1 = clock.tick(reference_frame_index=1, reference_timestamp_seconds=0.02)       # → f1
    t2 = clock.tick(reference_frame_index=2, reference_timestamp_seconds=0.04)       # → f1 已消费
    assert t0.frame_status["cam_2"] == "available"
    assert t0.views["cam_2"].source_frame_index == 0
    assert t1.frame_status["cam_2"] == "available"
    assert t1.views["cam_2"].source_frame_index == 1
    assert t2.frame_status["cam_2"] == "no_new_frame"
    assert t2.views["cam_2"] is None
    # 单调:last_consumed 停在 f1
    assert clock.last_consumed_source_frame_index["cam_2"] == 1


def test_clock_reports_interval_range_selection_error_and_provenance():
    calibration = SyncCalibration(
        reference_camera="cam_1",
        camera_id="cam_2",
        offset_seconds=0.0,
        rate=1.0,
        drift_ppm=250.0,
        residual_rms_seconds=0.02,
        anchor_count=3,
        quality="degraded",
        valid_start_seconds=0.2,
        valid_end_seconds=0.8,
    )
    sync = MultiViewSyncCalibration(reference_camera="cam_1", mappings={"cam_2": calibration})
    reference_provider = FrameTimingProvider(
        frames=(FrameTiming(0, 10.0), FrameTiming(1, 10.05)),
        provenance=FrameTimingProvider.nominal(frame_count=1, fps=20.0).provenance.__class__(
            authority="source_pts"
        ),
        fps=20.0,
    )
    clock = CanonicalAnalysisClock(
        reference_view_id="cam_1",
        secondary_view_id="cam_2",
        secondary_frames=[FrameTiming(0, 0.2), FrameTiming(1, 0.8)],
        sync=sync,
        secondary_camera_id="cam_2",
        max_pairing_error_ms=10.0,
        reference_timing_provider=reference_provider,
        reference_timing_authority="source_pts",
        secondary_timing_authority="source_pts",
    )
    before = clock.tick(reference_frame_index=0, reference_timestamp_seconds=0.1)
    # 2026-08-13 起：窗口开头（< valid_start）回退到有效起点帧，status=fallback_valid_start
    assert before.frame_status["cam_2"] == "fallback_valid_start"
    assert before.mapping_diagnostics["reason"] == "fallback_valid_start"
    assert before.views["cam_2"] is not None
    assert before.views["cam_2"].source_frame_index == 0  # 回退到 valid_start 最近的帧

    error = clock.tick(reference_frame_index=1, reference_timestamp_seconds=0.5)
    assert error.frame_status["cam_2"] == "unavailable_selection_error"
    assert error.mapping_diagnostics["selection_error_ms"] is not None
    assert error.views["cam_1"].source_timestamp_ms == pytest.approx(10050.0)
    assert error.views["cam_1"].timing_authority == "source_pts"
    assert error.views["cam_1"].sync_quality == "degraded"


def test_clock_window_start_falls_back_to_valid_start_frame():
    """窗口开头（canonical 早于 valid_start）回退到有效起点帧，status=fallback_valid_start。

    debug replay 前段因此有副摄画面（2026-08-13 修复），且不消费 tracker（单调不变量保持）。
    """
    calibration = SyncCalibration(
        reference_camera="cam_1",
        camera_id="cam_2",
        offset_seconds=0.0,
        rate=1.0,
        drift_ppm=0.0,
        residual_rms_seconds=0.001,
        anchor_count=3,
        quality="good",
        valid_start_seconds=3.4,
        valid_end_seconds=50.0,
    )
    sync = MultiViewSyncCalibration(reference_camera="cam_1", mappings={"cam_2": calibration})
    # cam_2 60fps，帧 0..5999（0-100s）
    cam2_frames = [FrameTiming(i, i / 60.0) for i in range(6000)]
    clock = CanonicalAnalysisClock(
        reference_view_id="cam_1",
        secondary_view_id="cam_2",
        secondary_frames=cam2_frames,
        sync=sync,
        secondary_camera_id="cam_2",
        max_pairing_error_ms=16.7,
    )
    # 窗口开头：t=0 早于 valid_start 3.4s → 回退到 valid_start 附近的帧
    early = clock.tick(reference_frame_index=0, reference_timestamp_seconds=0.0)
    assert early.frame_status["cam_2"] == "fallback_valid_start"
    assert early.views["cam_2"] is not None
    assert early.views["cam_2"].source_frame_index == round(3.4 * 60)  # ≈204
    assert early.mapping_diagnostics["reason"] == "fallback_valid_start"
    assert early.mapping_diagnostics["fallback_selection_error_ms"] is not None

    # 有效区间内：正常 available
    inside = clock.tick(reference_frame_index=300, reference_timestamp_seconds=5.0)
    assert inside.frame_status["cam_2"] == "available"
    assert inside.views["cam_2"].source_frame_index == 300

    # 无有效区间（valid_start=None）：保持细分不可用
    no_range_sync = MultiViewSyncCalibration(
        reference_camera="cam_1",
        mappings={
            "cam_2": SyncCalibration(
                reference_camera="cam_1", camera_id="cam_2",
                offset_seconds=0.0, rate=1.0, drift_ppm=0.0,
                residual_rms_seconds=0.001, anchor_count=3, quality="good",
            )
        },
    )
    clock2 = CanonicalAnalysisClock(
        reference_view_id="cam_1", secondary_view_id="cam_2",
        secondary_frames=cam2_frames, sync=no_range_sync, secondary_camera_id="cam_2",
    )
    # 无 valid_start 时 selection 走 out_of_media_range（target=0 在帧范围内则 selection ok）：
    # 此处 target=0、local=0、最近帧=0 → ok，故直接 available
    ok_bundle = clock2.tick(reference_frame_index=0, reference_timestamp_seconds=0.0)
    assert ok_bundle.frame_status["cam_2"] == "available"


# ---- GlobalMotionEstimator ---------------------------------------------------


def test_motion_estimator_predict_and_measurement():
    est = GlobalMotionEstimator(process_noise=1.0, measurement_noise=1.0)
    for i in range(10):
        est.update("g1", 1.0 + i * 0.5, 2.0 + i * 0.3, i / 30.0)
    p = est.predict("g1", 0.5)
    assert p is not None
    x, y, uncertainty = p
    # 预测位置沿恒定速度方向前进
    assert x > 3.0
    assert uncertainty > 0


def test_lifecycle_confirmed_requires_dual_consistent():
    reg = GlobalPlayerRegistry(anchored_dual_view_count=3, confirm_dual_view_count=3)
    # 仅单摄吸收测量:lifecycle 仍 tentative,anchored false
    for i in range(5):
        reg.absorb_measurement("g1", 5.0 + i, 6.0 + i, i / 30.0)
    s = reg.get("g1")
    assert s.lifecycle == "tentative"
    assert not s.cross_view_anchored
    # 双视角一致 → anchored + confirmed
    for i in range(3):
        reg.record_dual_consistent("g1")
    assert s.lifecycle == "confirmed"
    assert s.cross_view_anchored


# ---- GlobalPlayerAssociator --------------------------------------------------


def _obs(view_id, x, y, pid="", tid=None, ts=0.0):
    return JointObservation(
        view_id=view_id, source_frame_index=0, take_timestamp_ms=ts * 1000.0,
        local_x_ft=x, local_y_ft=y, view_player_id=pid, track_id=tid, confidence=0.9,
    )


def test_global_centric_assignment_and_single_view_missing():
    reg = GlobalPlayerRegistry()
    assoc = GlobalPlayerAssociator(reg, max_association_distance_ft=3.0)
    # roster 化：前 2 tick 双视角 P1 一致 → 先成 candidate，第 2 tick 晋升为 global（provisional occupant）
    for t in range(2):
        obs = [
            _obs("cam_1", 5.0 + t * 0.1, 8.0, pid="P1", tid=1, ts=t / 30.0),
            _obs("cam_2", 5.2 + t * 0.1, 8.1, pid="P1", tid=11, ts=t / 30.0),
        ]
        assoc.process_tick(obs, t / 30.0, {"cam_1": IDENTITY, "cam_2": IDENTITY}, tick=t)
    gids = {gid for gid in reg.players if reg.players[gid].roster_status in ("provisional", "confirmed")}
    assert len(gids) == 1  # 双视角一致 2 tick → 晋升占用一个 roster slot
    gid0 = next(iter(gids))
    # 吸收一次测量(模拟 joint run 的 fusion 更新),使 global 有 motion state
    reg.absorb_measurement(gid0, 5.1, 8.05, 0.0)
    reg.record_dual_consistent(gid0)
    # tick3:cam_1 P1 缺失,仅 cam_2 可见 → 仍分配到该 global（弱历史绑定 + 连续性）
    obs2 = [_obs("cam_2", 5.3, 8.2, pid="P1", tid=11, ts=3 / 30.0)]
    updates2 = assoc.process_tick(obs2, 3 / 30.0, {"cam_1": IDENTITY, "cam_2": IDENTITY}, tick=3)
    assert {u.global_id for u in updates2} == {gid0}


def test_association_geometry_gate_independent():
    reg = GlobalPlayerRegistry()
    assoc = GlobalPlayerAssociator(reg, max_association_distance_ft=3.0)
    # P1 在 cam_1(5,8);cam_2 有两个候选:近(5.2,8.1)与远(20,30)
    for t in range(2):
        obs = [
            _obs("cam_1", 5.0, 8.0, pid="P1", tid=1, ts=t / 30.0),
            _obs("cam_2", 5.2, 8.1, pid="X", tid=11, ts=t / 30.0),
            _obs("cam_2", 20.0, 30.0, pid="Y", tid=12, ts=t / 30.0),
        ]
        assoc.process_tick(obs, t / 30.0, {"cam_1": IDENTITY, "cam_2": IDENTITY}, tick=t)
    # 近候选 X 与 P1 双视角一致 2 tick → 晋升同一 global；远候选 Y 单视角候选未达晋升阈值
    gids = sorted(g for g in reg.players if reg.players[g].roster_status in ("provisional", "confirmed"))
    assert len(gids) == 1
    assert len(reg.candidates) == 1  # Y 仍在候选池（hit=2 < 5，且无双视角一致）


# ---- CrossViewGuidancePolicy -------------------------------------------------


def test_guidance_requires_confirmed_and_anchored():
    reg = GlobalPlayerRegistry(anchored_dual_view_count=1, confirm_dual_view_count=1)
    reg.absorb_measurement("g1", 5.0, 8.0, 0.0)
    reg.record_dual_consistent("g1")
    s = reg.get("g1")
    # binding 过期(丢失) → 可触发 guidance
    reg.set_binding("g1", "cam_2", ViewBinding(last_seen_take_timestamp_ms=-2000.0), 0.0)
    gen = GuidanceGenerator(CrossViewGuidancePolicy())
    pred = (5.1, 8.1, 1.5)
    g = gen.generate(
        global_state=s, target_view="cam_2", orientation=IDENTITY,
        inverse_homography=invert_homography(SCALE_H), now_take_ms=0.0, tick=0,
        frame_width=640, frame_height=480, prediction=pred,
    )
    assert g is not None
    assert g.target_view == "cam_2"
    assert g.roi[0] < g.roi[2]  # 合法 ROI


def test_guidance_observed_binding_no_trigger_and_cooldown():
    reg = GlobalPlayerRegistry(anchored_dual_view_count=1, confirm_dual_view_count=1)
    reg.absorb_measurement("g1", 5.0, 8.0, 0.0)
    reg.record_dual_consistent("g1")
    s = reg.get("g1")
    # observed binding → 不触发
    reg.set_binding("g1", "cam_2", ViewBinding(
        last_seen_take_timestamp_ms=0.0, visibility="observed",
    ), 0.0, weak_after_ms=5000.0)
    gen = GuidanceGenerator(CrossViewGuidancePolicy())
    g = gen.generate(
        global_state=s, target_view="cam_2", orientation=IDENTITY,
        inverse_homography=invert_homography(SCALE_H), now_take_ms=0.0, tick=0,
        frame_width=640, frame_height=480, prediction=(5.1, 8.1, 1.5),
    )
    assert g is None


# ---- guided pre-gate ---------------------------------------------------------


def test_guided_pre_gate_rejects_and_never_touches_tracker():
    det = Detection(bbox=[280, 150, 310, 300], confidence=0.8, class_name="person")
    c = guided_candidate_pre_gate(
        det, homography=SCALE_H, predicted_canonical=(5.0, 8.0),
        max_residual_ft=3.0, frame_width=640, frame_height=480,
    )
    # foot (295,300) → court (14.75,15) vs pred (5,8) → residual ~12 > 3 → 拒绝
    assert not c.accepted
    assert c.reject_reason == "residual_too_large"


def test_guided_merge_dedup_and_accept():
    # 近距离候选:bbox foot → court 接近预测 → accepted
    det = Detection(bbox=[100, 150, 120, 200], confidence=0.8, class_name="person")
    c = guided_candidate_pre_gate(
        det, homography=SCALE_H, predicted_canonical=(5.0, 8.0),
        max_residual_ft=3.0, frame_width=640, frame_height=480,
    )
    assert c.accepted
    # 与 base 合并去重:完全重叠的 guided 被丢弃
    base = [Detection(bbox=[100, 150, 120, 200], confidence=0.9, class_name="person")]
    merged = merge_base_and_guided(base, [det], iou_threshold=0.5)
    assert len(merged) == 1


# ---- artifact v1/v2 reader ---------------------------------------------------


def test_artifact_version_aware_loader():
    v2 = write_fused_v2(
        run_id="mvr_1", capture_take_id="take_1", reference_view_id="cam_1",
        samples=[FusedSample(
            global_player_id="global_player_1", take_timestamp_ms=33.3,
            reference_frame_index=1, x_ft=5.0, y_ft=8.0,
            fusion_status="dual_observed", metric_eligible=True,
            observation_origin="guided_roi",
            view_observations={"cam_1": {"origin": "base"}, "cam_2": {"origin": "guided_roi"}},
        )],
    )
    loaded = load_fused_trajectory(v2)
    assert loaded.schema_version == "fused_player_trajectory.v2"
    assert loaded.samples[0].observation_origin == "guided_roi"
    # v1 兼容
    v1 = {"schema_version": "fused_player_trajectory.v1", "run_id": "x",
          "samples": [{"global_player_id": "p", "take_timestamp_ms": 0.0,
                       "reference_frame_index": 0, "x_ft": 1.0, "y_ft": 2.0,
                       "fusion_status": "predicted", "metric_eligible": False}]}
    loaded_v1 = load_fused_trajectory(v1)
    assert loaded_v1.schema_version == "fused_player_trajectory.v1"
    assert loaded_v1.samples[0].observation_origin == "base"


# ---- MultiViewJointRun 端到端 ------------------------------------------------


class ScriptedDetector:
    supports_region_detection = False

    def __init__(self, script):
        self.script = script

    def detect_frame(self, frame, frame_index: int | None = None) -> list[Detection]:
        return self.script.get(int(frame_index or 0), [])

    def detect(self, frame) -> list[Detection]:
        return []


def _det(bbox, conf: float = 0.8) -> Detection:
    return Detection(bbox=list(bbox), confidence=conf, class_name="person")


def _joint_script() -> dict[int, list[Detection]]:
    # A / B 双球员,两视角同一合成 canonical,轻微位移
    return {
        0: [_det([280, 150, 310, 300]), _det([340, 160, 370, 350])],
        1: [_det([280, 150, 310, 305]), _det([340, 160, 370, 355])],
        2: [_det([280, 150, 310, 305]), _det([340, 160, 370, 355])],
        3: [_det([280, 150, 310, 308]), _det([340, 160, 370, 358])],
        4: [_det([280, 150, 310, 308]), _det([340, 160, 370, 358])],
        5: [_det([280, 150, 310, 310]), _det([340, 160, 370, 360])],
    }


def _joint_config():
    settings = get_settings()
    config = build_view_tracking_config(
        settings, build_match_context(None), fps=30.0, frame_stride=1,
        frame_width=640, frame_height=480,
    )
    config.player_lock_bootstrap_min_frames = 1
    config.player_lock_bootstrap_max_frames = 4
    config.identity_lost_buffer_frames = 5
    config.player_lock_enable_appearance_score = False
    return config


def test_joint_run_end_to_end():
    """双摄 joint 端到端:2 摄 4 球员(每摄 2 人)→ 形成 global、写 v2、两视角都 step。"""
    config = _joint_config()
    script = _joint_script()
    roi = compute_expanded_detection_roi(None, 640, 480)
    cam1_session = build_view_tracking_session(
        detector=ScriptedDetector(script), homography=SCALE_H, roi_artifact=roi, config=config,
    )
    cam2_session = build_view_tracking_session(
        detector=ScriptedDetector(script), homography=SCALE_H, roi_artifact=roi, config=config,
    )
    frames = {i: object() for i in range(10)}
    cam1_rt = JointViewRuntime(
        view_input=JointViewInput(camera_slot="cam_1", camera_id="c1"),
        capture=frames, fps=30.0, frame_size=(640, 480), homography=SCALE_H,
        roi_artifact=roi, tracking_session=cam1_session, scope="full",
    )
    cam2_rt = JointViewRuntime(
        view_input=JointViewInput(camera_slot="cam_2", camera_id="c2"),
        capture=frames, fps=30.0, frame_size=(640, 480), homography=SCALE_H,
        roi_artifact=roi, tracking_session=cam2_session, scope="perception",
    )
    cam2_frames = [FrameTiming(i, i / 30.0) for i in range(10)]
    clock = CanonicalAnalysisClock(
        reference_view_id="cam_1", secondary_view_id="cam_2",
        secondary_frames=cam2_frames, sync=_sync(rate=1.0, offset=0.0),
        secondary_camera_id="cam_2", max_pairing_error_ms=33.3,
    )
    registry = GlobalPlayerRegistry(anchored_dual_view_count=2, confirm_dual_view_count=2)
    associator = GlobalPlayerAssociator(registry, max_association_distance_ft=3.0)
    gen = GuidanceGenerator(CrossViewGuidancePolicy())
    run = MultiViewJointRun(
        run_id="mvr_test", capture_take_id="take", reference_view_id="cam_1",
        clock=clock, runtimes={"cam_1": cam1_rt, "cam_2": cam2_rt},
        registry=registry, associator=associator, guidance_generator=gen,
        orientations={"cam_1": IDENTITY, "cam_2": IDENTITY},
        inverse_homography=invert_homography(SCALE_H),
        frame_width=640, frame_height=480,
    )
    out = run.run(reference_frame_count=6, reference_fps=30.0)
    assert out.trajectory["schema_version"] == "fused_player_trajectory.v2"
    assert out.normalized.samples  # 至少一个 global
    assert out.diagnostics["global_player_count"] >= 1
    assert cam1_rt.counters.get("stepped_frames", 0) >= 1
    assert cam2_rt.counters.get("stepped_frames", 0) >= 1


def test_joint_run_window_limits_ticks_and_excludes_warmup_samples():
    from types import SimpleNamespace

    class FakeRuntime:
        def __init__(self, view_id):
            self.view_id = view_id
            self.calls = []

        def step(self, source_frame_index, timestamp_s, guidance=()):
            self.calls.append(source_frame_index)
            return SimpleNamespace(frame_index=source_frame_index, frame_positions=[])

    cam1 = FakeRuntime("cam_1")
    cam2 = FakeRuntime("cam_2")
    clock = CanonicalAnalysisClock(
        reference_view_id="cam_1", secondary_view_id="cam_2",
        secondary_frames=[FrameTiming(i, i / 30.0) for i in range(30)],
        sync=_sync(), secondary_camera_id="cam_2",
    )
    registry = GlobalPlayerRegistry()
    run = MultiViewJointRun(
        run_id="mvr-window", capture_take_id="take", reference_view_id="cam_1",
        clock=clock, runtimes={"cam_1": cam1, "cam_2": cam2},
        registry=registry, associator=GlobalPlayerAssociator(registry, max_association_distance_ft=3.0),
        guidance_generator=GuidanceGenerator(CrossViewGuidancePolicy()),
        orientations={"cam_1": IDENTITY, "cam_2": IDENTITY},
        inverse_homography=np.eye(3), frame_width=640, frame_height=480,
    )
    out = run.run(
        reference_fps=30.0,
        frame_stride=1,
        reference_frame_start=3,
        reference_frame_end=9,
        metric_frame_start=5,
        metric_frame_end=9,
    )

    assert cam1.calls == [3, 4, 5, 6, 7, 8]
    assert cam2.calls == [3, 4, 5, 6, 7, 8]
    assert out.diagnostics["processed_tick_count"] == 6
    assert out.diagnostics["metric_frame_range"] == {"start": 5, "end": 9}
    assert out.normalized.samples == []


# ---- ReferenceRichAnalysisContext(full scope 富分析)-------------------------


def test_reference_rich_analysis_uses_same_decode():
    from types import SimpleNamespace

    from app.vision.multiview.reference_rich_analysis import ReferenceRichAnalysisContext

    class FakeResult:
        frame_index = 3
        frame_detections = [object()]
        frame_positions = [object()]
        player_motion_pixels = 5.0

    class FakePose:
        called_with = None

        def estimate_frame(self, frame, subjects, frame_index, timestamp_seconds):
            self.called_with = frame
            return SimpleNamespace(subjects=[SimpleNamespace(keypoints=[1])])

    ctx = ReferenceRichAnalysisContext(
        runtime=object(), frame="THE_FRAME", frame_index=3,
        timestamp_s=0.1, view_result=FakeResult(),
    )
    pose = FakePose()
    ctx.run_pose(pose)
    # 消费同一次 reference frame decode,不二次解码
    assert pose.called_with == "THE_FRAME"
    assert len(ctx.pose_frames) == 1
    assert ctx.debug_signature()["position_sample_count"] == 1


# ---- execution-mode A/B 去重 ------------------------------------------------


def test_execution_mode_dedup_ab():
    """同一 take 的 late/joint inputSignature 不同 → 不被幂等去重丢弃。"""
    from app.schemas.analysis import (
        AnalysisJobCreate,
        AnalysisUploadMetadata,
        MultiViewCreateRequest,
        MultiViewViewPayload,
    )
    from app.services.job_orchestration import analysis_signature

    def _meta(take):
        return AnalysisUploadMetadata(
            fileName=f"{take}_cam1.mp4", sourceFps=30.0, matchTitle="t", venue="v",
            matchDate="2026-01-01", matchFormat="doubles", cameraAngle="baseline",
            athleteLabel="a", level="l", capture_take_id=take,
        )

    def _payload(mode):
        return AnalysisJobCreate(
            metadata=_meta("take_1"),
            analysisKind="multiview",
            multiview=MultiViewCreateRequest(
                referenceViewId="cam_1",
                executionMode=mode,
                views=[
                    MultiViewViewPayload(viewId="cam_1", videoId="v1", calibrationId="c1", courtOrientation="identity"),
                    MultiViewViewPayload(viewId="cam_2", videoId="v2", calibrationId="c2", courtOrientation="identity"),
                ],
            ),
        )

    sig_late = analysis_signature(_payload("late_fusion_v1"))
    sig_joint = analysis_signature(_payload("joint_tracking_v2"))
    assert sig_late != sig_joint  # A/B 不被幂等去重当成同一任务

    acceptance_payload = _payload("joint_tracking_v2")
    acceptance_payload.multiview.debugTraceEnabled = True
    assert analysis_signature(acceptance_payload) != sig_joint


# ---- joint parent restart 幂等 + compose(GlobalPlayer 标签)------------------


def test_joint_parent_restart_rebuildable_and_compose():
    from app.schemas.analysis import AnalysisJobSummary, AnalysisUploadMetadata
    from app.services.job_orchestration import JobStore
    from app.services.multiview_result_composer import MultiViewResultComposer
    from app.vision.multiview.joint_artifact import FusedSample, NormalizedFusedTrajectory

    meta = AnalysisUploadMetadata(
        fileName="t_cam1.mp4", sourceFps=30.0, matchTitle="t", venue="v",
        matchDate="2026-01-01", matchFormat="doubles", cameraAngle="baseline",
        athleteLabel="a", level="l", capture_take_id="take_1",
    )

    def _job(**updates) -> AnalysisJobSummary:
        base = {
            "id": "job-joint", "status": "queued", "canonicalStatus": "queued",
            "displayStatus": "queued", "stage": "queue", "progress": 10,
            "createdAt": "2026-08-01T00:00:00Z", "updatedAt": "2026-08-01T00:00:00Z",
            "metadata": meta.model_dump(), "stages": [], "reportId": "PV-J",
            "analysisMode": "real", "videoId": "v1", "calibrationId": "cal1",
            "analysisKind": "multiview", "executionMode": "joint_tracking_v2",
            "orchestrationStatus": "joint_ready", "jointViewInputs": [
                {"cameraSlot": "cam_1", "cameraId": "c1", "videoId": "v1",
                 "calibrationId": "cal1", "courtOrientation": "identity"},
                {"cameraSlot": "cam_2", "cameraId": "c2", "videoId": "v2",
                 "calibrationId": "cal2", "courtOrientation": "rotate_180"},
            ],
        }
        base.update(updates)
        return AnalysisJobSummary.model_validate(base)

    store = JobStore()
    # restart 幂等基础:joint_ready 可直接 claim(无 child);waiting_sources 不可
    assert store.is_runnable(_job())
    assert not store.is_runnable(_job(orchestrationStatus="waiting_sources"))
    # late_fusion 仍要求 fusion_ready(不与 joint 语义混淆)
    late = _job(executionMode="late_fusion_v1", orchestrationStatus="waiting_sources")
    assert not store.is_runnable(late)

    # compose_joint_result:GlobalPlayer 标签 + completed
    output = type("Out", (), {
        "trajectory": {"schema_version": "fused_player_trajectory.v2", "run_id": "r",
                       "capture_take_id": "take_1", "reference_view_id": "cam_1"},
        "diagnostics": {"global_player_count": 2, "degraded": "healthy"},
        "normalized": NormalizedFusedTrajectory(
            schema_version="fused_player_trajectory.v2", run_id="r",
            capture_take_id="take_1", reference_view_id="cam_1",
            samples=[
                FusedSample(global_player_id="global_player_1", take_timestamp_ms=100.0,
                            reference_frame_index=3, x_ft=5.0, y_ft=8.0,
                            fusion_status="dual_observed", metric_eligible=True),
                FusedSample(global_player_id="global_player_2", take_timestamp_ms=100.0,
                            reference_frame_index=3, x_ft=10.0, y_ft=20.0,
                            fusion_status="single_view_fallback", metric_eligible=True),
            ],
        ),
    })
    result = MultiViewResultComposer().compose_joint_result(
        job=_job(), joint_output=output, reference_view_id="cam_1",
        message="joint done",
    )
    assert result.status == "completed"
    labels = {t.track_id for t in result.tracks}
    assert "global_player_1" in labels and "global_player_2" in labels  # GlobalPlayer 标签
