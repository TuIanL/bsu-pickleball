"""fused 轨迹时间戳契约测试（2026-08-13 修复：缺 timestamp_seconds → 速度/小地图失效）。

- `write_fused_v2` 必须写 `timestamp_seconds`（优先样本值，回退 take_timestamp_ms/1000）
- composer `fused_to_projected_tracks` 读取优先级：timestamp_seconds → take_timestamp_ms/1000 → 0.0
- 时间戳正确时速度/厨房停留指标非 0
"""

from __future__ import annotations

from app.services.multiview_result_composer import MultiViewResultComposer
from app.vision.multiview.joint_artifact import FusedSample, load_fused_trajectory, write_fused_v2

composer = MultiViewResultComposer(storage=None)


def _sample(**overrides) -> dict[str, object]:
    base = {
        "global_player_id": "global_player_1",
        "take_timestamp_ms": 1000.0,
        "reference_frame_index": 30,
        "x_ft": 5.0,
        "y_ft": 10.0,
        "fusion_status": "dual_observed",
        "metric_eligible": True,
    }
    base.update(overrides)
    return base


def test_writer_derives_timestamp_seconds_from_take_ms():
    """write_fused_v2 在样本无显式 timestamp_seconds 时由 take_timestamp_ms 派生。"""
    samples = [FusedSample(
        global_player_id="global_player_1",
        take_timestamp_ms=2500.0,
        reference_frame_index=30,
        x_ft=5.0,
        y_ft=10.0,
        fusion_status="dual_observed",
        metric_eligible=True,
    )]
    payload = write_fused_v2(run_id="mvr_t", capture_take_id="ct", reference_view_id="cam_1", samples=samples)
    raw = payload["samples"][0]
    assert raw["timestamp_seconds"] == 2.5


def test_writer_keeps_explicit_timestamp_seconds():
    """write_fused_v2 保留样本显式 timestamp_seconds（优先于 take_timestamp_ms）。"""
    samples = [FusedSample(
        global_player_id="global_player_1",
        take_timestamp_ms=1000.0,
        reference_frame_index=30,
        x_ft=5.0,
        y_ft=10.0,
        fusion_status="dual_observed",
        metric_eligible=True,
        timestamp_seconds=7.5,
    )]
    payload = write_fused_v2(run_id="mvr_t", capture_take_id="ct", reference_view_id="cam_1", samples=samples)
    assert payload["samples"][0]["timestamp_seconds"] == 7.5


def test_reader_roundtrip_timestamp_seconds():
    """normalize 读取 timestamp_seconds 并保留在 FusedSample。"""
    payload = write_fused_v2(
        run_id="mvr_t", capture_take_id="ct", reference_view_id="cam_1",
        samples=[FusedSample(
            global_player_id="g1", take_timestamp_ms=4000.0, reference_frame_index=10,
            x_ft=1.0, y_ft=2.0, fusion_status="dual_observed", metric_eligible=True,
        )],
    )
    normalized = load_fused_trajectory(payload)
    assert normalized.samples[0].timestamp_seconds == 4.0


def test_projected_tracks_fallback_to_take_ms():
    """缺 timestamp_seconds 的历史样本回退 take_timestamp_ms/1000。"""
    fused = {"samples": [
        _sample(take_timestamp_ms=3000.0),  # 无 timestamp_seconds
    ]}
    tracks = composer.fused_to_projected_tracks(fused)
    assert len(tracks) == 1
    assert tracks[0].timestamp_seconds == 3.0


def test_projected_tracks_prefer_explicit_timestamp():
    """有 timestamp_seconds 时使用显式值（即使 take_timestamp_ms 不同）。"""
    fused = {"samples": [
        _sample(take_timestamp_ms=1000.0, timestamp_seconds=9.25),
    ]}
    tracks = composer.fused_to_projected_tracks(fused)
    assert tracks[0].timestamp_seconds == 9.25


def test_projected_tracks_zero_when_both_missing():
    """两者都缺才落到 0.0。"""
    fused = {"samples": [_sample(take_timestamp_ms=None)]}
    tracks = composer.fused_to_projected_tracks(fused)
    assert tracks[0].timestamp_seconds == 0.0


def test_speed_metrics_nonzero_with_timestamps():
    """时间戳正确时速度指标非 0（回归：此前全 0 导致平均速度 0.0 ft/s）。"""
    from app.schemas.analysis import build_match_context

    fused = {"samples": [
        _sample(global_player_id="g1", reference_frame_index=0, take_timestamp_ms=0.0,
                x_ft=0.0, y_ft=0.0),
        _sample(global_player_id="g1", reference_frame_index=30, take_timestamp_ms=1000.0,
                x_ft=10.0, y_ft=0.0),
    ]}
    metrics = composer.recompute_metrics(fused, build_match_context("doubles"))
    speed = next((s for s in metrics.speeds if s.track_id == "g1"), None)
    assert speed is not None
    assert speed.average_speed_ft_per_s > 0.0
