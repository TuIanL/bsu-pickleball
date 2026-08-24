"""Canonical tick 球链路契约测试。"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from app.vision.multiview.analysis_clock import FrameSample, SynchronizedFrameBundle
from app.vision.multiview.ball_stereo.canonical_runner import (
    CanonicalBallStereoProcessor,
    _ensure_unique_event_ids,
)
from app.vision.pickleball_game_analysis.reconstruction_schemas import TrajectoryEvent, TrajectoryEventType


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

    def filter_candidates(self, candidates, frame_shape):
        decisions = [
            SimpleNamespace(
                candidate_id=f"candidate_{index + 1}",
                image_xy=candidate.image_xy,
                accepted=True,
                reason="accepted",
                diagnostics={"frame_shape": list(frame_shape)},
            )
            for index, candidate in enumerate(candidates)
        ]
        return SimpleNamespace(candidates=tuple(candidates), decisions=tuple(decisions))

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


def _bundle_at(tick: int) -> SynchronizedFrameBundle:
    frame = np.zeros((32, 48, 3), dtype=np.uint8)
    timestamp_ms = tick * 1000.0 / 30.0
    return SynchronizedFrameBundle(
        take_timestamp_ms=timestamp_ms,
        views={
            "cam_1": FrameSample(tick * 2, timestamp_ms, timestamp_ms, frame=frame),
            "cam_2": FrameSample(tick * 2 + 1, timestamp_ms + 3.0, timestamp_ms, frame=frame),
        },
        frame_status={"cam_1": "available", "cam_2": "available"},
    )


def _processor(*, secondary_available: bool = True, max_duration_seconds: float | None = None, hybrid_enabled: bool = True):
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
        hybrid_enabled=hybrid_enabled,
    )
    return processor, detectors, trackers


def test_detector_runs_once_per_available_view_and_tracker_shares_snapshot():
    processor, detectors, trackers = _processor()

    processor.process_tick(tick_id=7, bundle=_bundle())

    assert detectors["cam_1"].calls == 1
    assert detectors["cam_2"].calls == 1
    assert len(trackers["cam_1"].candidate_snapshots) == 1
    assert len(trackers["cam_2"].candidate_snapshots) == 1
    assert processor.candidate_filtering[0]["decisions"][0]["reason"] == "accepted"
    assert processor.candidate_filtering[1]["decisions"][0]["reason"] == "accepted"
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
    assert result.v3_trajectory["schema_version"] == "reconstructed_ball_trajectory.v4"
    assert result.v3_trajectory["display_trajectory_status"] in {"available", "degraded", "unavailable"}

    assert result.status == "unavailable"
    assert "超时" in result.detail
    assert result.diagnostics["counters"]["timed_out"] == 1


def test_finish_reconstructs_independent_event_segments_instead_of_one_full_window():
    processor, _, _ = _processor()
    processor.add_serve_reset_event(
        TrajectoryEvent("hit-4", TrajectoryEventType.HIT, 4, 4 / 30.0, confidence=0.9)
    )
    processor.add_serve_reset_event(
        TrajectoryEvent("bounce-8", TrajectoryEventType.BOUNCE, 8, 8 / 30.0, confidence=0.9)
    )
    for tick in range(12):
        processor.process_tick(tick_id=tick, bundle=_bundle_at(tick))

    result = processor.finish()
    segment_ids = [segment["segment_id"] for segment in result.v3_trajectory["segments"]]
    assert segment_ids == ["flight-1", "flight-2", "flight-3"]
    assert "seg_canonical_1" not in segment_ids
    windows = result.diagnostics["segment_windows"]
    assert windows[0]["end_event_id"] == "hit-4"
    assert windows[1]["start_event_id"] == "hit-4"
    assert windows[1]["end_event_id"] == "bounce-8"
    assert windows[0]["primary_view_id"] in {"cam_1", "cam_2"}
    assert set(windows[0]["view_metrics"]["cam_1"]) >= {
        "observation_coverage",
        "continuity",
        "mean_detection_confidence",
        "fit_residual_px",
        "predicted_ratio",
        "static_false_positive_ratio",
        "visibility_score",
        "score",
    }
    assert {event["event_type"] for event in result.v3_trajectory["events"]} >= {"hit", "bounce"}
    evidence = result.stereo_evidence
    assert evidence["observations"]
    assert all(observation["segment_id"] is not None for observation in evidence["observations"])
    assert all(pairing["segment_id"] is not None for pairing in evidence["pairings"])
    assert all(measurement["segment_id"] is not None for measurement in evidence["measurements"])


def test_cross_view_duplicate_event_ids_are_disambiguated_without_changing_timestamps():
    events = [
        TrajectoryEvent(
            "bounce-1",
            TrajectoryEventType.BOUNCE,
            30,
            1.0,
            confidence=0.9,
            diagnostics={"view_id": "cam_1"},
        ),
        TrajectoryEvent(
            "bounce-1",
            TrajectoryEventType.BOUNCE,
            90,
            3.0,
            confidence=0.8,
            diagnostics={"view_id": "cam_2"},
        ),
    ]

    unique = _ensure_unique_event_ids(events)

    assert [event.event_id for event in unique] == ["bounce-1", "bounce-1@cam_2"]
    assert [event.timestamp_sec for event in unique] == [1.0, 3.0]


def test_hybrid_feature_flag_rolls_publication_back_to_historical_v3_contract():
    processor, _, _ = _processor(hybrid_enabled=False)
    for tick in range(8):
        processor.process_tick(tick_id=tick, bundle=_bundle_at(tick))

    result = processor.finish()

    assert result.v3_trajectory["schema_version"] == "reconstructed_ball_trajectory.v3"
    assert result.v3_trajectory["reconstruction_mode"] == "multiview_estimated_3d"
    assert "display_trajectory_status" not in result.v3_trajectory
    assert result.diagnostics["hybrid_enabled"] is False
