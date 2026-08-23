"""Canonical tick 球链路契约测试。"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from app.vision.multiview.analysis_clock import FrameSample, SynchronizedFrameBundle
from app.vision.multiview.ball_stereo.canonical_runner import CanonicalBallStereoProcessor


class _Detector:
    def __init__(self, candidates):
        self.candidates = candidates
        self.calls = 0

    def detect(self, frame, conf):
        self.calls += 1
        return list(self.candidates)


class _Tracker:
    def __init__(self):
        self.config = SimpleNamespace(confidence=0.18)
        self.candidate_snapshots = []

    def update_from_candidates(self, *, frame_index, timestamp_sec, view_candidates, frame_shape, homography):
        self.candidate_snapshots.append(view_candidates)
        candidate = view_candidates[0]
        return SimpleNamespace(accepted=True, image_xy=(candidate.image_xy[0], candidate.image_xy[1]))


def _projection_pair() -> tuple[np.ndarray, np.ndarray]:
    # 两个带水平基线的简化 pinhole 相机，点 (0, 0, 5) 映射为 (0,0) / (-0.2,0)。
    return (
        np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0]]),
        np.array([[1.0, 0.0, 0.0, -1.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0]]),
    )


def _bundle(*, secondary_available: bool = True) -> SynchronizedFrameBundle:
    frame = np.zeros((32, 48, 3), dtype=np.uint8)
    views = {
        "cam_1": FrameSample(10, 100.0, 100.0, frame=frame),
        "cam_2": FrameSample(20, 103.0, 100.0, frame=frame) if secondary_available else None,
    }
    return SynchronizedFrameBundle(
        take_timestamp_ms=100.0,
        views=views,
        frame_status={"cam_1": "available", "cam_2": "available" if secondary_available else "unavailable_selection_error"},
    )


def _processor(*, secondary_available: bool = True, max_duration_seconds: float | None = None):
    projection_1, projection_2 = _projection_pair()
    candidates = [SimpleNamespace(image_xy=(0.0, 0.0), confidence=0.9)]
    detectors = {"cam_1": _Detector(candidates), "cam_2": _Detector([SimpleNamespace(image_xy=(-0.2, 0.0), confidence=0.8)])}
    trackers = {"cam_1": _Tracker(), "cam_2": _Tracker()}
    processor = CanonicalBallStereoProcessor(
        job_id="job-canonical",
        take_id="take-canonical",
        reference_view_id="cam_1",
        secondary_view_id="cam_2",
        detectors=detectors,
        trackers=trackers,
        projections={"cam_1": projection_1, "cam_2": projection_2},
        frame_stride=2,
        max_time_gate_ms=40.0,
        max_duration_seconds=max_duration_seconds,
    )
    return processor, detectors, trackers


def test_detector_runs_once_per_available_view_and_tracker_shares_snapshot():
    processor, detectors, trackers = _processor()

    processor.process_tick(tick_id=7, bundle=_bundle())

    assert detectors["cam_1"].calls == 1
    assert detectors["cam_2"].calls == 1
    assert len(trackers["cam_1"].candidate_snapshots) == 1
    assert len(trackers["cam_2"].candidate_snapshots) == 1
    assert processor.counters["stereo_measurements"] == 1
    measurement = processor.measurements[0]
    assert measurement.canonical_tick == 7
    assert measurement.cam1_source_frame_index == 10
    assert measurement.cam2_source_frame_index == 20
    assert processor.finish().stereo_evidence["measurements"][0]["cam1_timestamp_ms"] == 100.0


def test_stereo_gate_uses_sync_mapped_time_not_raw_source_offset():
    processor, _, _ = _processor()
    processor.max_time_gate_ms = 1.0

    # Cam2 原始 PTS 比 Cam1 晚 3 ms，但两路已映射到同一个 canonical 时刻。
    # 这验证固定 offset 不会被误判为不同步。
    processor.process_tick(tick_id=8, bundle=_bundle())

    assert processor.counters["stereo_measurements"] == 1
    measurement = processor.measurements[0]
    assert measurement.cam1_timestamp_ms == 100.0
    assert measurement.cam2_timestamp_ms == 100.0


def test_unavailable_secondary_frame_never_enters_stereo_measurement():
    processor, detectors, _ = _processor(secondary_available=False)

    processor.process_tick(tick_id=1, bundle=_bundle(secondary_available=False))

    assert detectors["cam_1"].calls == 1
    assert detectors["cam_2"].calls == 0
    assert processor.counters["stereo_measurements"] == 0
    assert processor.counters["unmatched_ticks"] == 1


def test_ball_budget_timeout_degrades_ball_stage_without_raising(monkeypatch):
    import app.vision.multiview.ball_stereo.canonical_runner as canonical_runner

    clock = iter([100.0, 102.0])
    monkeypatch.setattr(canonical_runner.time, "monotonic", lambda: next(clock))
    processor, _, _ = _processor(max_duration_seconds=1.0)

    processor.process_tick(tick_id=1, bundle=_bundle())
    result = processor.finish()

    assert result.status == "unavailable"
    assert "超时" in result.detail
    assert result.diagnostics["counters"]["timed_out"] == 1
