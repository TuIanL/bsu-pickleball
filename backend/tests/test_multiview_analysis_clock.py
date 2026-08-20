"""fix-multiview-anchor-span-debug-frame-mapping 的时钟层单测。

覆盖验收硬指标 1/2/3/4/6：
- pre/post 锚点区间外 Cam-2 拿到随时间递增的真实媒体帧（不再固定第一锚点帧）；
- 映射越出 Cam-2 媒体 PTS → unavailable_out_of_media_range；
- 最近帧 selection error 超质量门 → unavailable_selection_error（外推不放松 frame-selection）；
- available_extrapolated 不推进 last_consumed 游标（D3），authoritative available / no_new_frame 守卫不变；
- 历史 valid_start_seconds/end_seconds calibration artifact 仍能读写。
"""

from __future__ import annotations

from app.services.dual_camera_sync import (
    FrameTiming,
    SyncCalibration,
    calibration_from_dict,
    calibration_to_dict,
)
from app.vision.multiview.analysis_clock import CanonicalAnalysisClock
from app.vision.multiview.multiview_joint_run import MultiViewJointRun
from app.vision.multiview.sync import MultiViewSyncCalibration

_FPS = 30.0
_PAIRING_ERROR_MS = 1000.0 / 30.0  # ≈33.33ms，与时钟默认一致


def _make_clock(
    *,
    valid_start_seconds: float,
    valid_end_seconds: float,
    frame_count: int = 300,
    offset_seconds: float = 0.0,
    rate: float = 1.0,
    max_pairing_error_ms: float = _PAIRING_ERROR_MS,
) -> CanonicalAnalysisClock:
    secondary_frames = [
        FrameTiming(frame_index=i, pts_seconds=i / _FPS) for i in range(frame_count)
    ]
    calibration = SyncCalibration(
        reference_camera="cam_1",
        camera_id="cam_2",
        offset_seconds=offset_seconds,
        rate=rate,
        drift_ppm=0.0,
        residual_rms_seconds=0.0,
        anchor_count=3,
        quality="good",
        reason=None,
        valid_start_seconds=valid_start_seconds,
        valid_end_seconds=valid_end_seconds,
    )
    sync = MultiViewSyncCalibration(
        reference_camera="cam_1",
        mappings={"cam_2": calibration},
    )
    return CanonicalAnalysisClock(
        reference_view_id="cam_1",
        secondary_view_id="cam_2",
        secondary_frames=secondary_frames,
        sync=sync,
        secondary_camera_id="cam_2",
        max_pairing_error_ms=max_pairing_error_ms,
    )


def _tick_sec(clock: CanonicalAnalysisClock, t: float) -> tuple[str, int | None, str | None]:
    bundle = clock.tick(reference_frame_index=int(round(t * _FPS)), reference_timestamp_seconds=t)
    status = bundle.frame_status["cam_2"]
    sample = bundle.views["cam_2"]
    idx = sample.source_frame_index if sample is not None else None
    mode = sample.mapping_mode if sample is not None else None
    return status, idx, mode


def test_pre_anchor_extrapolation_advances_source_index():
    """指标 1：pre-anchor 段 Cam-2 源帧索引随时间正常递增，不固定在第一锚点帧。"""
    clock = _make_clock(valid_start_seconds=6.7, valid_end_seconds=10.0)
    statuses, indices = [], []
    for t in [0.0, 0.1, 0.2, 0.3, 1.0, 3.0, 6.5]:
        status, idx, mode = _tick_sec(clock, t)
        statuses.append(status)
        indices.append(idx)
        assert mode == "pre_anchor_extrapolation"
    assert all(s == "available_extrapolated" for s in statuses)
    assert indices == [0, 3, 6, 9, 30, 90, 195]
    # 不允许出现“全部固定为同一帧”的 clamp 回归
    assert len(set(indices)) == len(indices)


def test_pre_anchor_no_clamp_to_valid_start():
    """指标 1 强化：pre-anchor 首个 tick 的源帧不应等于 valid_start 对应的锚点帧。"""
    clock = _make_clock(valid_start_seconds=6.7, valid_end_seconds=10.0)
    _, idx, _ = _tick_sec(clock, 0.0)
    # valid_start=6.7s 对应帧 ≈ 201；pre-anchor t=0 必须落到第 0 帧而非被钳到 201。
    assert idx == 0
    assert idx != 201


def test_post_anchor_extrapolation_within_media():
    """指标 2：post-anchor 段，只要 affine 映射仍落在 Cam-2 媒体内就持续有真实画面。"""
    # 媒体覆盖到 ~19.97s（frame_count=600），valid_end=10.0 → post 段有真实帧。
    clock = _make_clock(valid_start_seconds=6.7, valid_end_seconds=10.0, frame_count=600)
    status, idx, mode = _tick_sec(clock, 12.0)
    assert status == "available_extrapolated"
    assert mode == "post_anchor_extrapolation"
    assert idx == 360  # 12.0s * 30fps


def test_extrapolation_out_of_media_unavailable():
    """指标 3：映射真的越出 Cam-2 媒体 PTS 时才细分 unavailable，而非黑屏/冻结。"""
    # 媒体只到 ~9.97s（frame_count=300），valid_start/end 设到很远使 canonical 仍处 pre 段。
    clock = _make_clock(valid_start_seconds=200.0, valid_end_seconds=300.0, frame_count=300)
    # canonical=1.0 仍在 pre 段且映射落在媒体内 → 正常外推
    status_in, _, _ = _tick_sec(clock, 1.0)
    assert status_in == "available_extrapolated"
    # canonical=100 映射 local=100s 远超媒体 → 细分 unavailable_out_of_media_range
    status_out, idx_out, _ = _tick_sec(clock, 100.0)
    assert status_out == "unavailable_out_of_media_range"
    assert idx_out is None


def test_extrapolation_selection_error_gate():
    """外推复用 authoritative 质量门：最近帧 selection error 超限仍细分 unavailable。"""
    # Cam-2 媒体为整秒间隔（1s/帧），默认 pairing error 门 ≈33ms。
    secondary_frames = [FrameTiming(frame_index=i, pts_seconds=float(i)) for i in range(20)]
    calibration = SyncCalibration(
        reference_camera="cam_1",
        camera_id="cam_2",
        offset_seconds=0.0,
        rate=1.0,
        drift_ppm=0.0,
        residual_rms_seconds=0.0,
        anchor_count=3,
        quality="good",
        reason=None,
        valid_start_seconds=0.5,
        valid_end_seconds=100.0,
    )
    sync = MultiViewSyncCalibration(reference_camera="cam_1", mappings={"cam_2": calibration})
    clock = CanonicalAnalysisClock(
        reference_view_id="cam_1",
        secondary_view_id="cam_2",
        secondary_frames=secondary_frames,
        sync=sync,
        secondary_camera_id="cam_2",
        max_pairing_error_ms=_PAIRING_ERROR_MS,
    )
    # canonical=0.3（pre-anchor），local=0.3，最近整秒帧 error 0.3s >> 33ms
    status_bad, idx_bad, _ = _tick_sec(clock, 0.3)
    assert status_bad == "unavailable_selection_error"
    assert idx_bad is None
    # 对照：canonical 正好落在整秒帧上（error≈0）应正常外推，证明只是质量门拦截异常缺口
    status_ok, idx_ok, _ = _tick_sec(clock, 0.0)
    assert status_ok == "available_extrapolated"
    assert idx_ok == 0


def test_available_extrapolated_does_not_advance_last_consumed():
    """指标 4 / D3 边界：pre-anchor 视觉帧 195→196→197 不推进 last_consumed；
    进入 anchor span 后首个 authoritative available=204 才更新游标。"""
    clock = _make_clock(valid_start_seconds=6.7, valid_end_seconds=10.0, frame_count=300)
    seq = []
    for t in [6.5, 6.5333, 6.5667]:
        status, idx, mode = _tick_sec(clock, t)
        seq.append((status, idx, mode))
        # pre-anchor 阶段游标必须保持未设置
        assert clock.last_consumed_source_frame_index.get("cam_2") is None
    assert seq[0] == ("available_extrapolated", 195, "pre_anchor_extrapolation")
    assert seq[1] == ("available_extrapolated", 196, "pre_anchor_extrapolation")
    assert seq[2] == ("available_extrapolated", 197, "pre_anchor_extrapolation")

    # 进入 anchor span：首个 authoritative available 帧 204，游标在此才被推进
    status_in, idx_in, _ = _tick_sec(clock, 6.8)
    assert status_in == "available"
    assert idx_in == 204
    assert clock.last_consumed_source_frame_index["cam_2"] == 204


def test_reference_available_and_no_new_frame_guard_preserved():
    """指标 5 前置：anchor span 内 authoritative available / no_new_frame 守卫完全不变。"""
    clock = _make_clock(valid_start_seconds=6.7, valid_end_seconds=10.0, frame_count=300)
    b1 = clock.tick(reference_frame_index=int(round(7.0 * _FPS)), reference_timestamp_seconds=7.0)
    assert b1.frame_status["cam_2"] == "available"
    assert clock.last_consumed_source_frame_index["cam_2"] == 210
    # 紧邻 tick 仍映射到同一源帧 → 单调不重复守卫触发 no_new_frame，不重复喂 tracker
    b2 = clock.tick(reference_frame_index=int(round(7.01 * _FPS)), reference_timestamp_seconds=7.01)
    assert b2.frame_status["cam_2"] == "no_new_frame"


def test_historical_calibration_artifact_roundtrip():
    """指标 6：历史 valid_start_seconds/end_seconds calibration artifact 仍能读写。"""
    payload = {
        "reference_camera": "cam_1",
        "camera_id": "cam_2",
        "offset_ms": 120.0,
        "rate": 1.0,
        "drift_ppm": 0.0,
        "residual_rms_ms": 0.0,
        "anchor_count": 3,
        "quality": "good",
        "reason": None,
        "valid_start_seconds": 6.7,
        "valid_end_seconds": 10.0,
    }
    cal = calibration_from_dict(payload)
    assert cal.valid_start_seconds == 6.7
    assert cal.valid_end_seconds == 10.0
    serialized = calibration_to_dict(cal)
    assert serialized["valid_start_seconds"] == 6.7
    assert serialized["valid_end_seconds"] == 10.0


def test_anchor_span_extrapolation_excluded_from_authoritative_perception():
    """指标 4/5 集成契约：区间外 available_extrapolated 不参与 authoritative joint perception。

    下游感知门控（multiview_joint_run L378 `status != "available"` 与 `_tick_is_authoritative`）
    均基于 ``frame_status == "available"`` 硬比较；本 change 不动该门控（D5），因此
    available_extrapolated 天然被跳过——此处用真实 ``_tick_is_authoritative`` 验证该契约，
    确保 Scope A 没有把外推帧喂给 tracker/fusion。
    """
    clock = _make_clock(valid_start_seconds=6.7, valid_end_seconds=10.0, frame_count=300)
    # 绕过 __init__（其重型依赖与本契约测试无关），仅注入 _tick_is_authoritative 所需字段。
    run = MultiViewJointRun.__new__(MultiViewJointRun)
    run.runtimes = {"cam_1", "cam_2"}
    run.reference_view_id = "cam_1"
    run.authoritative_joint_eligible = True
    run.clock = clock
    run._tick_authoritative_by_index = {}

    # pre-anchor tick：cam_2 = available_extrapolated → 不参与 authoritative joint
    pre_bundle = clock.tick(reference_frame_index=int(6.5 * _FPS), reference_timestamp_seconds=6.5)
    assert pre_bundle.frame_status["cam_2"] == "available_extrapolated"
    assert run._tick_is_authoritative(pre_bundle) is False

    # anchor-span tick：cam_2 = available → 参与 authoritative joint（资格由误差/authority 决定）
    in_bundle = clock.tick(reference_frame_index=int(7.0 * _FPS), reference_timestamp_seconds=7.0)
    assert in_bundle.frame_status["cam_2"] == "available"
    assert run._tick_is_authoritative(in_bundle) is True
