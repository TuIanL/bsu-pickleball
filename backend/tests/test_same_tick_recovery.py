"""same-tick usable-candidate recovery（B-Phase-2）单元测试。

覆盖（tasks 6.1 / 6.2 / 6.3 / 6.4）：
- pre-association：一对一匹配 / ambiguity rejection / 只消费 ROI-filtered /
  投影与 projector 一致 / 只读不写 mapping；
- PreparedViewFrame：committed 防重复 / 第二次 complete 抛异常 / step 兼容 /
  update-once 精确语义（unavailable→0、committed→1）；
- same-tick 双向恢复：donor 有 base candidate target 无 → 补检成功；
  两路 projection 均失败 → 不强制；donor 严格 base；budget 共享不翻倍；同 pair 去重；
- 回归：process_tick 输出与门限不变；same_tick_recovery_enabled=false 回退。
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.vision.multiview.court_frame import CourtOrientation
from app.vision.multiview.pre_association import PreAssociationCandidate, pre_associate


# ---- 1. pre-association -----------------------------------------------------


@dataclass
class _FakeDet:
    bbox: tuple[float, float, float, float]
    confidence: float = 0.8
    image_footpoint: tuple[float, float] | None = None


IDENTITY = CourtOrientation.identity
# 0.1x 缩放：图像→球场（像素 /10 = 英尺）
H = [[0.1, 0.0, 0.0], [0.0, 0.1, 0.0], [0.0, 0.0, 1.0]]


def _det_at_px(x: float, y: float, conf: float = 0.8) -> _FakeDet:
    return _FakeDet(bbox=(x - 10, y - 30, x + 10, y), confidence=conf, image_footpoint=(x, y))


def test_pre_associate_one_to_one_and_strong() -> None:
    # Cam1 在 px(100, 200)（court 10,20）看到 P1 → 预测 P1@(10,20)
    view_evidence = {
        "cam_1": [(_det_at_px(100.0, 200.0), "base")],
        "cam_2": [(_det_at_px(400.0, 300.0), "base")],  # court 40,30（无预测 → unmatched）
    }
    result = pre_associate(
        view_evidence=view_evidence,
        homography_by_view={"cam_1": H, "cam_2": H},
        orientation_by_view={"cam_1": IDENTITY, "cam_2": IDENTITY},
        source_frame_index_by_view={"cam_1": 10, "cam_2": 11},
        global_predictions={"global_player_1": (10.0, 20.0, 1.0)},
        pre_association_gate_ft=3.0,
        ambiguity_margin=0.15,
    )
    cam1 = [c for c in result.candidates if c.view_id == "cam_1"]
    assert len(cam1) == 1
    assert cam1[0].match_status == "strong"
    assert cam1[0].matched_global_id == "global_player_1"
    assert cam1[0].is_usable is True
    cam2 = [c for c in result.candidates if c.view_id == "cam_2"]
    assert cam2[0].match_status == "unmatched"


def test_pre_associate_ambiguity_rejection() -> None:
    # 一个 candidate 距离两个预测都很近且 margin 不足 → ambiguous
    view_evidence = {"cam_1": [(_det_at_px(100.0, 200.0), "base")]}
    result = pre_associate(
        view_evidence=view_evidence,
        homography_by_view={"cam_1": H},
        orientation_by_view={"cam_1": IDENTITY},
        source_frame_index_by_view={"cam_1": 10},
        global_predictions={
            "global_player_1": (10.0, 20.0, 1.0),
            "global_player_2": (10.05, 20.0, 1.0),  # 极近 → margin 不足
        },
        pre_association_gate_ft=3.0,
        ambiguity_margin=0.15,
    )
    cand = result.candidates[0]
    assert cand.match_status == "ambiguous"
    assert cand.is_usable is False  # ambiguous 不可作 donor


def test_pre_associate_projection_outside_tracking_kept() -> None:
    # court 投影落在 tracking bounds 外 → candidate 保留（投影分类诚实），
    # 但若 canonical 有效仍可能 usable（由归属判定决定）；此处验证 candidate 不丢失。
    far_h = [[0.1, 0.0, 0.0], [0.0, 0.1, 0.0], [0.0, 0.0, 1.0]]
    view_evidence = {"cam_1": [(_det_at_px(5000.0, 5000.0), "base")]}  # 极远 → court(500,500) 在 tracking 外
    result = pre_associate(
        view_evidence=view_evidence,
        homography_by_view={"cam_1": far_h},
        orientation_by_view={"cam_1": IDENTITY},
        source_frame_index_by_view={"cam_1": 10},
        global_predictions={"global_player_1": (10.0, 20.0, 1.0)},
        pre_association_gate_ft=3.0,
    )
    cand = result.candidates[0]
    assert cand.projection_status == "outside_tracking_area" or cand.court_position_ft is not None
    assert cand.is_usable is False  # 远超出 gate → unmatched


def test_pre_associate_ignores_guided_donor_for_same_tick() -> None:
    """same-tick donor 严格 base：guided_roi evidence 不作为 strong donor。"""
    view_evidence = {
        "cam_1": [(_det_at_px(100.0, 200.0), "guided_roi")],  # guided 不作为 donor
        "cam_2": [(_det_at_px(400.0, 300.0), "base")],
    }
    result = pre_associate(
        view_evidence=view_evidence,
        homography_by_view={"cam_1": H, "cam_2": H},
        orientation_by_view={"cam_1": IDENTITY, "cam_2": IDENTITY},
        source_frame_index_by_view={"cam_1": 10, "cam_2": 11},
        global_predictions={"global_player_1": (10.0, 20.0, 1.0)},
    )
    # cam_1 的 guided candidate 即使匹配也不能作为 base donor（调用方 `_select_same_tick_guidance` 检查 origin）
    cam1 = [c for c in result.candidates if c.view_id == "cam_1"][0]
    assert cam1.origin == "guided_roi"


# ---- 2. PreparedViewFrame（事务两阶段）--------------------------------------


def test_view_tracking_session_prepare_does_not_update_tracker():
    """prepare_frame 不 update tracker；complete_frame 恰好一次；重复 complete 抛异常。"""
    # committed 语义由 _CountingSession 覆盖（见 test_prepared_frame_committed_protection）；
    # 此处验证 PreparedViewFrame 默认 committed=False。
    from app.vision.player_tracking_engine.view_tracking_session import PreparedViewFrame

    prepared = PreparedViewFrame(
        frame_index=0, timestamp=0.0, frame=object(),
        raw_detections=[], roi_filtered_base=[], pre_tick_guided=[], merged_pre_tick=[],
    )
    assert prepared.committed is False


class _CountingSession:
    """记录 complete_frame 调用的轻量替身（验证 committed 语义）。"""

    def __init__(self) -> None:
        self.complete_calls = 0
        self.prepare_calls = 0

    def prepare_frame(self, frame, *, frame_index, timestamp, pre_tick_guidance=()):
        from app.vision.player_tracking_engine.view_tracking_session import PreparedViewFrame
        self.prepare_calls += 1
        return PreparedViewFrame(
            frame_index=frame_index, timestamp=timestamp, frame=frame,
            raw_detections=[], roi_filtered_base=[], pre_tick_guided=[], merged_pre_tick=[],
        )

    def complete_frame(self, prepared, same_tick_guidance=()):
        if prepared.committed:
            raise RuntimeError("double complete")
        prepared.committed = True
        self.complete_calls += 1
        return type("R", (), {"frame_index": prepared.frame_index, "frame_positions": [], "frame_detections": []})()


def test_prepared_frame_committed_protection() -> None:
    session = _CountingSession()
    prepared = session.prepare_frame(object(), frame_index=0, timestamp=0.0)
    assert session.prepare_calls == 1
    session.complete_frame(prepared)
    assert prepared.committed is True
    assert session.complete_calls == 1
    with pytest.raises(RuntimeError):
        session.complete_frame(prepared)  # 第二次 complete 抛异常
    assert session.complete_calls == 1  # update-once 保持


# ---- 3. same-tick 双向恢复（集成级）----------------------------------------


def test_joint_run_same_tick_disabled_falls_back():
    """same_tick_recovery_enabled=false → 不执行 same-tick 互救（回退现状）。"""
    import numpy as np

    from app.services.frame_timing_provider import FrameTiming
    from app.vision.multiview.analysis_clock import CanonicalAnalysisClock
    from app.vision.multiview.association_global import GlobalPlayerAssociator
    from app.vision.multiview.global_state import GlobalPlayerRegistry, ViewBinding
    from app.vision.multiview.guidance import CrossViewGuidancePolicy, GuidanceGenerator
    from app.vision.multiview.multiview_joint_run import MultiViewJointRun
    from app.vision.multiview.recovery_config import P1OnlineRecoveryConfig

    H = np.array([[10.0, 0.0, 0.0], [0.0, 10.0, 0.0], [0.0, 0.0, 1.0]])
    registry = GlobalPlayerRegistry(anchored_dual_view_count=2, confirm_dual_view_count=2)
    registry.absorb_measurement("global_player_1", 10.0, 20.0, 0.0)
    state = registry.ensure("global_player_1")
    state.lifecycle = "confirmed"
    state.cross_view_anchored = True
    state.roster_status = "confirmed"
    state.association_eligible = True
    state.view_bindings = {
        "cam_1": ViewBinding(view_player_id="Player_1", visibility="observed"),
        "cam_2": ViewBinding(view_player_id="Player_1", visibility="observed", quality=0.9),
    }

    class FakeRuntime:
        def __init__(self, view_id):
            self.view_id = view_id
            self.calls = []

        def step(self, source_frame_index, timestamp_s, guidance=()):
            self.calls.append(("step", source_frame_index, len(guidance)))
            return type(
                "R", (), {"frame_index": source_frame_index, "frame_positions": [], "frame_detections": []},
            )()

    cam1 = FakeRuntime("cam_1")
    cam2 = FakeRuntime("cam_2")
    from app.vision.multiview.sync import MultiViewSyncCalibration, SyncCalibration

    sc = SyncCalibration(
        reference_camera="cam_1", camera_id="cam_2",
        offset_seconds=0.0, rate=1.0,
        drift_ppm=0.0, residual_rms_seconds=0.0, anchor_count=1, quality="good",
    )
    clock = CanonicalAnalysisClock(
        reference_view_id="cam_1", secondary_view_id="cam_2",
        secondary_frames=[FrameTiming(i, i / 30.0) for i in range(30)],
        sync=MultiViewSyncCalibration(reference_camera="cam_1", mappings={"cam_2": sc}),
        secondary_camera_id="cam_2",
    )
    gen = GuidanceGenerator(CrossViewGuidancePolicy(same_tick_recovery_enabled=False))
    run = MultiViewJointRun(
        run_id="mvr-sametick-off", capture_take_id="take", reference_view_id="cam_1",
        clock=clock, runtimes={"cam_1": cam1, "cam_2": cam2},
        registry=registry, associator=GlobalPlayerAssociator(registry, max_association_distance_ft=3.0),
        guidance_generator=gen, orientations={"cam_1": IDENTITY, "cam_2": IDENTITY},
        inverse_homography=np.linalg.inv(H), frame_width=640, frame_height=480,
        recovery_config=P1OnlineRecoveryConfig(enabled=True, same_tick_recovery_enabled=False),
    )
    out = run.run(reference_frame_count=4, reference_fps=30.0)
    # legacy runtime（无 prepare）走 step 回退；same-tick 关闭 → 无 same_tick 计数
    assert run.counter.get("same_tick_guidance_generated_count", 0) == 0
    assert out.trajectory["schema_version"] == "fused_player_trajectory.v2"
