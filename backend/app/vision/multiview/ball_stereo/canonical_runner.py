"""Canonical-tick 双摄球处理器。

该模块只负责把 joint 的同步帧捆绑转换成球侧 evidence/v3。它不拥有视频时间轴，
也不重新打开视频；每个 tick 使用调用方已经确定的 ``SynchronizedFrameBundle``。
球 detector 每个视角每个 tick 只调用一次，tracker 通过 ``update_from_candidates``
消费同一份候选集合。
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field, replace
from typing import Any, Mapping

import numpy as np

from app.vision.multiview.ball_stereo.artifact_builders import (
    build_stereo_evidence_v1,
    build_v3_trajectory,
)
from app.vision.multiview.ball_stereo.association import associate_views
from app.vision.multiview.ball_stereo.metrics import compute_metrics
from app.vision.multiview.ball_stereo.hybrid_segment_builder import build_hybrid_segment
from app.vision.multiview.ball_stereo.segment_reconstruction import (
    Observation,
    Reconstructed3DSegment,
    reconstruct_segment,
)
from app.vision.multiview.ball_stereo.segment_view_selection import (
    compute_view_segment_metrics,
    select_main_view,
)
from app.vision.multiview.ball_stereo.stereo_measurement import BallStereoMeasurement, measure_stereo
from app.vision.pickleball_game_analysis.ball_contact_event_detector import (
    BallContactEventDetector,
    ContactDetectorConfig,
)
from app.vision.pickleball_game_analysis.ball_event_resolver import BallEventResolver
from app.vision.pickleball_game_analysis.ball_flight_segmenter import BallFlightSegmenter
from app.vision.pickleball_game_analysis.bounce_detector import BounceDetector, BounceDetectorConfig
from app.vision.pickleball_game_analysis.reconstruction_schemas import (
    ReconstructionConfig,
    TrajectoryEvent,
    event_to_payload,
)
from app.vision.pickleball_game_analysis.schemas import TrajectoryPoint


@dataclass
class CanonicalBallAnalysisOutput:
    """球路阶段给 Composer 的稳定内存契约。"""

    v3_trajectory: dict[str, Any]
    stereo_evidence: dict[str, Any]
    diagnostics: dict[str, Any] = field(default_factory=dict)
    status: str = "unavailable"  # succeeded / degraded / unavailable / failed
    detail: str = "双摄球路分析不可用"


def _candidate_tuple(candidate: Any) -> tuple[float, float, float]:
    image_xy = getattr(candidate, "image_xy", None)
    if image_xy is None:
        image_xy = (
            getattr(candidate, "image_x", 0.0),
            getattr(candidate, "image_y", 0.0),
        )
    return (float(image_xy[0]), float(image_xy[1]), float(getattr(candidate, "confidence", 0.0)))


def _canonical_timestamp_ms(frame_sample: Any) -> float:
    """返回经过双摄同步映射的 canonical 时间，兼容历史样本。"""
    mapped = getattr(frame_sample, "mapped_take_timestamp_ms", None)
    if mapped is not None and math.isfinite(float(mapped)):
        return float(mapped)
    return float(frame_sample.source_timestamp_ms)


def _ensure_unique_event_ids(events: list[TrajectoryEvent]) -> list[TrajectoryEvent]:
    """消除不同视角产生的同名事件，避免分段端点解析到另一时刻。"""
    seen: set[str] = set()
    output: list[TrajectoryEvent] = []
    for index, event in enumerate(events):
        base_id = event.event_id or f"{event.event_type.value}-{index + 1}"
        event_id = base_id
        if event_id in seen:
            view_id = str(event.diagnostics.get("view_id") or "merged").replace("@", "-")
            event_id = f"{base_id}@{view_id}"
            suffix = 2
            while event_id in seen:
                event_id = f"{base_id}@{view_id}-{suffix}"
                suffix += 1
            event = replace(event, event_id=event_id)
        seen.add(event_id)
        output.append(event)
    return output


class CanonicalBallStereoProcessor:
    """消费 canonical tick，生成不可变 evidence 和 v3 轨迹。"""

    def __init__(
        self,
        *,
        job_id: str,
        take_id: str,
        reference_view_id: str,
        secondary_view_id: str,
        detectors: Mapping[str, Any] | None,
        trackers: Mapping[str, Any] | None,
        projections: Mapping[str, Any] | None,
        runtimes: Mapping[str, Any] | None = None,
        frame_stride: int = 1,
        source_fps: float = 30.0,
        max_time_gate_ms: float = 40.0,
        max_duration_seconds: float | None = None,
        disabled_reason: str | None = None,
        hybrid_enabled: bool = True,
    ) -> None:
        self.job_id = job_id
        self.take_id = take_id
        self.reference_view_id = reference_view_id
        self.secondary_view_id = secondary_view_id
        self.detectors = dict(detectors or {})
        self.trackers = dict(trackers or {})
        self.projections = dict(projections or {})
        self.runtimes = dict(runtimes or {})
        self.frame_stride = max(1, int(frame_stride))
        self.source_fps = max(float(source_fps), 1.0)
        self.effective_fps = self.source_fps / self.frame_stride
        self.max_time_gate_ms = float(max_time_gate_ms)
        self.max_duration_seconds = (
            float(max_duration_seconds)
            if max_duration_seconds is not None and float(max_duration_seconds) > 0
            else None
        )
        self._started_monotonic = time.monotonic()
        self.disabled_reason = disabled_reason
        self.hybrid_enabled = bool(hybrid_enabled)
        self.measurements: list[BallStereoMeasurement] = []
        self.observations: list[Observation] = []
        self.pairings: list[dict[str, Any]] = []
        self.candidate_filtering: list[dict[str, Any]] = []
        self.trajectory_points_by_view: dict[str, list[TrajectoryPoint]] = {
            self.reference_view_id: [],
            self.secondary_view_id: [],
        }
        self.serve_reset_events: list[TrajectoryEvent] = []
        self.counters: dict[str, int] = {
            "canonical_ticks": 0,
            "available_view_frames": 0,
            "detector_calls": 0,
            "candidate_count": 0,
            "accepted_view_observations": 0,
            "stereo_measurements": 0,
            "unmatched_ticks": 0,
            "rejected_time_gate": 0,
            "timed_out": 0,
        }
        self._failure_reason: str | None = disabled_reason
        self._disabled = disabled_reason is not None
        self._last_trusted_xyz: tuple[float, float, float] | None = None

    @classmethod
    def unavailable(cls, *, job_id: str, take_id: str, reason: str) -> "CanonicalBallStereoProcessor":
        return cls(
            job_id=job_id,
            take_id=take_id,
            reference_view_id="cam_1",
            secondary_view_id="cam_2",
            detectors={},
            trackers={},
            projections={},
            disabled_reason=reason,
        )

    def process_tick(self, *, tick_id: int, bundle: Any) -> None:
        """处理一个 canonical tick；任何球侧异常都降级，不打断球员主链。"""
        self.counters["canonical_ticks"] += 1
        if self._disabled:
            return
        if (
            self.max_duration_seconds is not None
            and time.monotonic() - self._started_monotonic > self.max_duration_seconds
        ):
            self.counters["timed_out"] += 1
            self._disable("双摄球路分析阶段超时，已保留球员分析结果")
            return

        candidates_by_view: dict[str, list[tuple[float, float, float]]] = {}
        samples_by_view: dict[str, Any] = {}
        snapshots_by_view: dict[str, Any] = {}
        for view_id in (self.reference_view_id, self.secondary_view_id):
            if bundle.frame_status.get(view_id) != "available":
                continue
            frame_sample = bundle.views.get(view_id)
            if frame_sample is None:
                self.counters["missing_bundle_frames"] = self.counters.get("missing_bundle_frames", 0) + 1
                continue
            frame = getattr(frame_sample, "frame", None)
            if frame is None:
                runtime = self.runtimes.get(view_id)
                frame = runtime.get_frame(frame_sample.source_frame_index) if runtime is not None else None
            if frame is None:
                self.counters["decode_missing_frames"] = self.counters.get("decode_missing_frames", 0) + 1
                continue
            detector = self.detectors.get(view_id)
            tracker = self.trackers.get(view_id)
            if detector is None or tracker is None:
                self._disable("球 detector/tracker 未配置")
                return
            try:
                raw_candidates = list(
                    detector.detect(frame, conf=float(getattr(tracker.config, "confidence", 0.18)))
                )
                self.counters["detector_calls"] += 1
                self.counters["candidate_count"] += len(raw_candidates)
                if hasattr(tracker, "filter_candidates"):
                    filter_result = tracker.filter_candidates(raw_candidates, frame.shape)
                    shared_candidates = list(filter_result.candidates)
                    decisions = [
                        {
                            "candidate_id": decision.candidate_id,
                            "image_xy": list(decision.image_xy),
                            "accepted": decision.accepted,
                            "reason": decision.reason,
                            "diagnostics": dict(decision.diagnostics),
                        }
                        for decision in filter_result.decisions
                    ]
                else:
                    # 测试/旧注入 tracker 的兼容路径；正式 BallTracker 均提供共享过滤器。
                    shared_candidates = raw_candidates
                    decisions = []
                self.candidate_filtering.append(
                    {"tick_id": tick_id, "view_id": view_id, "decisions": decisions}
                )
                snapshots_by_view[view_id] = (
                    tracker.pre_tick_snapshot(_canonical_timestamp_ms(frame_sample) / 1000.0)
                    if hasattr(tracker, "pre_tick_snapshot")
                    else None
                )
                sample = tracker.update_from_candidates(
                    frame_index=int(frame_sample.source_frame_index),
                    timestamp_sec=_canonical_timestamp_ms(frame_sample) / 1000.0,
                    view_candidates=shared_candidates,
                    frame_shape=frame.shape,
                    homography=None,
                )
            except Exception as exc:  # noqa: BLE001 - 球侧不可用不得破坏球员主链
                self._disable(f"球检测运行失败：{exc}")
                return
            self.counters["available_view_frames"] += 1
            candidates_by_view[view_id] = [_candidate_tuple(item) for item in shared_candidates]
            samples_by_view[view_id] = sample
            if getattr(sample, "accepted", False) and getattr(sample, "image_xy", None) is not None:
                self.counters["accepted_view_observations"] += 1

        self._append_canonical_trajectory_points(tick_id, bundle, samples_by_view)

        if (
            self.reference_view_id not in candidates_by_view
            or self.secondary_view_id not in candidates_by_view
            or self.reference_view_id not in self.projections
            or self.secondary_view_id not in self.projections
        ):
            self._append_single_view_observations(bundle, samples_by_view)
            self.counters["unmatched_ticks"] += 1
            return

        ref_sample = bundle.views[self.reference_view_id]
        sec_sample = bundle.views[self.secondary_view_id]
        # source_timestamp_ms 是各摄像机自己的媒体时钟；跨视角配对必须使用
        # 同步标定映射后的 canonical 时间，否则一个已知的固定 offset 会被误判为
        # “不同步”（例如 60 FPS 下 36 ms offset > 16.7 ms gate）。
        ref_ts = _canonical_timestamp_ms(ref_sample)
        sec_ts = _canonical_timestamp_ms(sec_sample)
        if abs(ref_ts - sec_ts) > self.max_time_gate_ms:
            self._append_single_view_observations(bundle, samples_by_view)
            self.counters["rejected_time_gate"] += 1
            return
        pairs = associate_views(
            cam1_candidates=candidates_by_view[self.reference_view_id],
            cam2_candidates=candidates_by_view[self.secondary_view_id],
            projection_cam1=self.projections[self.reference_view_id],
            projection_cam2=self.projections[self.secondary_view_id],
            cam1_timestamp_ms=ref_ts,
            cam2_timestamp_ms=sec_ts,
            max_time_gate_ms=self.max_time_gate_ms,
            cam1_continuity=float(getattr(snapshots_by_view.get(self.reference_view_id), "continuity_score", 0.0)),
            cam2_continuity=float(getattr(snapshots_by_view.get(self.secondary_view_id), "continuity_score", 0.0)),
            cam1_scale_consistency=(
                1.0 if getattr(snapshots_by_view.get(self.reference_view_id), "recent_area_ratio", None) is not None else 0.5
            ),
            cam2_scale_consistency=(
                1.0 if getattr(snapshots_by_view.get(self.secondary_view_id), "recent_area_ratio", None) is not None else 0.5
            ),
            cam1_direction_consistency=(
                1.0 if getattr(snapshots_by_view.get(self.reference_view_id), "recent_velocity_px_per_sec", None) is not None else 0.5
            ),
            cam2_direction_consistency=(
                1.0 if getattr(snapshots_by_view.get(self.secondary_view_id), "recent_velocity_px_per_sec", None) is not None else 0.5
            ),
            previous_xyz=self._last_trusted_xyz,
        )
        if not pairs:
            self._append_single_view_observations(bundle, samples_by_view)
            self.counters["unmatched_ticks"] += 1
            return
        pair = pairs[0]
        try:
            measurement = measure_stereo(
                projection_cam1=self.projections[self.reference_view_id],
                projection_cam2=self.projections[self.secondary_view_id],
                image_xy1=pair.cam1_candidate[:2],
                image_xy2=pair.cam2_candidate[:2],
                cam1_timestamp_ms=ref_ts,
                cam2_timestamp_ms=sec_ts,
                take_timestamp_ms=float(bundle.take_timestamp_ms),
                sync_error_ms=abs(ref_ts - sec_ts),
                max_time_delta_ms=self.max_time_gate_ms,
            )
        except (ValueError, FloatingPointError, np.linalg.LinAlgError):
            self.counters["triangulation_rejected"] = self.counters.get("triangulation_rejected", 0) + 1
            return
        if not measurement.depth_valid:
            self.counters["depth_rejected"] = self.counters.get("depth_rejected", 0) + 1
            return
        measurement = measurement.__class__(
            **{
                **measurement.__dict__,
                "canonical_tick": tick_id,
                "cam1_source_frame_index": int(ref_sample.source_frame_index),
                "cam2_source_frame_index": int(sec_sample.source_frame_index),
                "high_quality_anchor": pair.anchor_eligible,
                "quality_components": dict(pair.quality_components),
            }
        )
        self.measurements.append(measurement)
        if pair.anchor_eligible:
            self._last_trusted_xyz = (
                measurement.estimated_x_ft,
                measurement.estimated_y_ft,
                measurement.estimated_z_ft,
            )
        self.observations.extend(
            [
                Observation(
                    ref_ts / 1000.0,
                    0,
                    float(pair.cam1_candidate[0]),
                    float(pair.cam1_candidate[1]),
                    self.projections[self.reference_view_id],
                    paired=pair.anchor_eligible,
                    source_view_id=self.reference_view_id,
                    quality_components=dict(pair.quality_components),
                ),
                Observation(
                    sec_ts / 1000.0,
                    1,
                    float(pair.cam2_candidate[0]),
                    float(pair.cam2_candidate[1]),
                    self.projections[self.secondary_view_id],
                    paired=pair.anchor_eligible,
                    source_view_id=self.secondary_view_id,
                    quality_components=dict(pair.quality_components),
                ),
            ]
        )
        self.counters["stereo_measurements"] += 1
        self.pairings.append(
            {
                "tick_id": tick_id,
                "cam1_source_frame_index": int(ref_sample.source_frame_index),
                "cam2_source_frame_index": int(sec_sample.source_frame_index),
                "cam1_timestamp_ms": ref_ts,
                "cam2_timestamp_ms": sec_ts,
                "cam1_source_timestamp_ms": float(ref_sample.source_timestamp_ms),
                "cam2_source_timestamp_ms": float(sec_sample.source_timestamp_ms),
                "take_timestamp_ms": float(bundle.take_timestamp_ms),
                "sync_error_ms": abs(ref_ts - sec_ts),
                "association_score": pair.score,
                "quality_label": pair.quality_label,
                "anchor_eligible": pair.anchor_eligible,
                "quality_components": dict(pair.quality_components),
                "time_gate_ms": self.max_time_gate_ms,
            }
        )

    def _append_canonical_trajectory_points(
        self,
        tick_id: int,
        bundle: Any,
        samples_by_view: Mapping[str, Any],
    ) -> None:
        """每个 canonical tick 为两路各保存一个点（含显式缺失）。"""
        timestamp_sec = float(bundle.take_timestamp_ms) / 1000.0
        for view_id in (self.reference_view_id, self.secondary_view_id):
            sample = samples_by_view.get(view_id)
            accepted = bool(sample is not None and getattr(sample, "accepted", False))
            image_xy = getattr(sample, "image_xy", None) if accepted else None
            self.trajectory_points_by_view[view_id].append(
                TrajectoryPoint(
                    frame_index=int(tick_id),
                    timestamp_sec=timestamp_sec,
                    image_xy=(float(image_xy[0]), float(image_xy[1])) if image_xy is not None else None,
                    court_xy=getattr(sample, "court_xy", None) if accepted else None,
                    confidence=getattr(sample, "confidence", None) if accepted else None,
                    source=getattr(sample, "source", "missing") if sample is not None else "missing",
                    diagnostics={
                        "view_id": view_id,
                        "source_frame_index": (
                            int(bundle.views[view_id].source_frame_index)
                            if bundle.views.get(view_id) is not None
                            else None
                        ),
                    },
                )
            )

    def add_serve_reset_event(self, event: TrajectoryEvent) -> None:
        """允许调用方把已验证的 serve reset 注入 canonical 切段时间轴。"""
        self.serve_reset_events.append(event)

    def _resolve_events(self) -> tuple[list[TrajectoryEvent], dict[str, Any]]:
        """按视角检测事件，再在 canonical 时间上确定性去重。"""
        all_events: list[TrajectoryEvent] = []
        diagnostics: dict[str, Any] = {"views": {}}
        for view_id, points in self.trajectory_points_by_view.items():
            contact_detector = BallContactEventDetector(
                ContactDetectorConfig(
                    effective_fps=self.effective_fps,
                    frame_stride=1,
                    max_context_gap_sec=max(0.12, 1.75 / self.effective_fps),
                )
            )
            hit_candidates = contact_detector.detect(points, fps=self.effective_fps, frame_stride=1)
            bounce_events = BounceDetector(BounceDetectorConfig(fps=self.effective_fps)).detect(points)
            events = BallEventResolver().resolve(hit_candidates, bounce_events, fps=self.effective_fps)
            for event in events:
                event.diagnostics["view_id"] = view_id
            all_events.extend(events)
            diagnostics["views"][view_id] = {
                "hit_candidates": len(hit_candidates),
                "confirmed_hits": sum(candidate.status == "confirmed_hit" for candidate in hit_candidates),
                "bounce_events": len(bounce_events),
                "resolved_events": len(events),
            }
        all_events.extend(self.serve_reset_events)
        merged: list[TrajectoryEvent] = []
        for event in sorted(all_events, key=lambda item: (item.timestamp_sec, item.event_type.value, -item.confidence)):
            duplicate_index = next(
                (
                    index
                    for index, kept in enumerate(merged)
                    if kept.event_type == event.event_type
                    and abs(kept.timestamp_sec - event.timestamp_sec) <= 0.08
                ),
                None,
            )
            if duplicate_index is None:
                merged.append(event)
            elif event.confidence > merged[duplicate_index].confidence:
                merged[duplicate_index] = event
        merged.sort(key=lambda item: (item.frame_index, item.timestamp_sec, item.event_type.value))
        merged = _ensure_unique_event_ids(merged)
        diagnostics["merged_event_count"] = len(merged)
        return merged, diagnostics

    def _canonical_points(self) -> list[TrajectoryPoint]:
        """切段时间轴优先使用参考视角，缺失 tick 才借用副视角。"""
        reference = self.trajectory_points_by_view[self.reference_view_id]
        secondary = self.trajectory_points_by_view[self.secondary_view_id]
        points: list[TrajectoryPoint] = []
        for index in range(max(len(reference), len(secondary))):
            ref = reference[index] if index < len(reference) else None
            sec = secondary[index] if index < len(secondary) else None
            chosen = ref if ref is not None and ref.image_xy is not None else sec or ref
            if chosen is not None:
                points.append(chosen)
        return points

    def _append_single_view_observations(self, bundle: Any, samples_by_view: Mapping[str, Any]) -> None:
        for view_id, sample in samples_by_view.items():
            if not getattr(sample, "accepted", False) or getattr(sample, "image_xy", None) is None:
                continue
            projection = self.projections.get(view_id)
            frame_sample = bundle.views.get(view_id)
            if projection is None or frame_sample is None:
                continue
            self.observations.append(
                Observation(
                    _canonical_timestamp_ms(frame_sample) / 1000.0,
                    0 if view_id == self.reference_view_id else 1,
                    float(sample.image_xy[0]),
                    float(sample.image_xy[1]),
                    projection,
                    paired=False,
                    source_view_id=view_id,
                )
            )

    def _disable(self, reason: str) -> None:
        self._disabled = True
        self._failure_reason = reason

    def finish(self) -> CanonicalBallAnalysisOutput:
        observations = sorted(self.observations, key=lambda item: (item.t_sec, item.cam_index))
        canonical_points = self._canonical_points()
        events, event_diagnostics = self._resolve_events()
        flights = BallFlightSegmenter(
            ReconstructionConfig(long_loss_gap_frames=max(3, int(round(self.effective_fps * 0.4))))
        ).segment(canonical_points, events)
        segments: list[Reconstructed3DSegment] = []
        metrics_by_segment: dict[str, Any] = {}
        duration_by_segment: dict[str, float] = {}
        segment_windows: list[dict[str, Any]] = []
        hybrid_inputs: list[tuple[Any, Any, list[BallStereoMeasurement]]] = []
        previous_primary_view_id: str | None = None
        if not self._failure_reason:
            for flight in flights:
                flight_points = [canonical_points[index] for index in flight.point_indices]
                start_sec = flight_points[0].timestamp_sec
                end_sec = flight_points[-1].timestamp_sec
                segment_observations = [
                    observation
                    for observation in observations
                    if start_sec - 1e-6 <= observation.t_sec <= end_sec + 1e-6
                ]
                segment_measurements = [
                    measurement
                    for measurement in self.measurements
                    if start_sec - 1e-6 <= measurement.take_timestamp_ms / 1000.0 <= end_sec + 1e-6
                ]
                segment = reconstruct_segment(
                    segment_id=flight.segment_id,
                    observations=segment_observations,
                    max_control_points=8,
                    bounce_end=flight.end_event_type is not None and flight.end_event_type.value == "bounce",
                    stereo_measurements=segment_measurements,
                )
                metrics_by_view = {
                    view_id: compute_view_segment_metrics(
                        view_id,
                        [self.trajectory_points_by_view[view_id][index] for index in flight.point_indices],
                    )
                    for view_id in (self.reference_view_id, self.secondary_view_id)
                }
                main_view = select_main_view(
                    metrics_by_view,
                    previous_primary_view_id=previous_primary_view_id,
                )
                previous_primary_view_id = main_view.primary_view_id
                hybrid_inputs.append((flight, main_view, segment_measurements))
                duration = max(0.001, end_sec - start_sec)
                segments.append(segment)
                duration_by_segment[flight.segment_id] = duration
                if segment.samples:
                    metrics_by_segment[flight.segment_id] = compute_metrics(segment, duration_sec=duration)
                segment_windows.append(
                    {
                        "segment_id": flight.segment_id,
                        "start_sec": start_sec,
                        "end_sec": end_sec,
                        "start_event_id": flight.start_event_id,
                        "end_event_id": flight.end_event_id,
                        "boundary_reason": flight.boundary_reason,
                        "observation_count": len(segment_observations),
                        "primary_view_id": main_view.primary_view_id,
                        "secondary_view_id": main_view.secondary_view_id,
                        "primary_view_reason": main_view.reason,
                        "primary_view_score_margin": main_view.score_margin,
                        "view_metrics": {
                            view_id: metrics.to_dict() for view_id, metrics in metrics_by_view.items()
                        },
                    }
                )
        v3 = build_v3_trajectory(
            job_id=self.job_id,
            take_id=self.take_id,
            bounce_source="canonical_reference_view",
            segments=segments,
            landing=None,
            metrics_by_segment=metrics_by_segment,
            duration_by_segment=duration_by_segment,
        )
        v3["events"] = [event_to_payload(event) for event in events]
        base_segments = {segment["segment_id"]: segment for segment in v3.get("segments") or []}
        if self.hybrid_enabled:
            # build_v3_trajectory serializes optimizer samples on a segment-local
            # clock. Hybrid consumers use absolute source-video seconds.
            segment_start_by_id = {
                window["segment_id"]: float(window["start_sec"])
                for window in segment_windows
            }
            for segment_id, payload in base_segments.items():
                start_sec = segment_start_by_id.get(segment_id, 0.0)
                for sample in payload.get("samples") or []:
                    if isinstance(sample.get("timestamp_sec"), (int, float)):
                        sample["timestamp_sec"] = round(start_sec + float(sample["timestamp_sec"]), 6)
                    if isinstance(sample.get("t_sec"), (int, float)):
                        sample["t_sec"] = round(start_sec + float(sample["t_sec"]), 6)
            events_by_id = {event.event_id: event for event in events}
            hybrid_segments = [
                build_hybrid_segment(
                    flight=flight,
                    points_by_view=self.trajectory_points_by_view,
                    events_by_id=events_by_id,
                    main_view=main_view,
                    projections=self.projections,
                    reconstructed_3d=next(segment for segment in segments if segment.segment_id == flight.segment_id),
                    stereo_measurements=segment_measurements,
                    base_3d_payload=base_segments.get(flight.segment_id),
                )
                for flight, main_view, segment_measurements in hybrid_inputs
            ]
            v3["segments"] = hybrid_segments
            v3["schema_version"] = "reconstructed_ball_trajectory.v4"
            v3["reconstruction_mode"] = "hybrid_segmented"
            v3["coordinate_semantics"] = {
                "xy": "canonical_court_ft",
                "z": "estimated_multiview_or_visualization_only_height_ft",
                "validity": "per_segment_metric_validity",
                "image_paths": "per_view_image_px_at_real_timestamp",
            }
            displayable = [segment for segment in hybrid_segments if segment["display_level"] != "none"]
            v3["display_trajectory_status"] = (
                "available"
                if any(segment["display_level"] in {"high", "medium"} for segment in displayable)
                else "degraded" if displayable else "unavailable"
            )
        detail = self._failure_reason or {
            "FULL_ESTIMATED_3D": "双摄三维球路分析完成",
            "PARTIAL_3D": "双摄三维球路部分可用",
            "LANDING_ONLY": "三维球路不可用，当前没有可靠落点",
            "UNAVAILABLE": "没有足够双摄证据生成球路",
        }.get(v3.get("overall_status"), "双摄球路分析完成")
        overall = str(v3.get("overall_status", "UNAVAILABLE"))
        status = "succeeded" if overall == "FULL_ESTIMATED_3D" else (
            "degraded" if overall in {"PARTIAL_3D", "LANDING_ONLY"} else "unavailable"
        )
        if status == "unavailable" and v3.get("display_trajectory_status") in {"available", "degraded"}:
            status = "degraded"
            detail = "双摄三维不足，已生成估算分段球路（仅用于可视化）"
        if self._failure_reason:
            status = "unavailable"
        diagnostics = {
            "pipeline": "canonical_tick_ball_stereo.v1",
            "frame_stride": self.frame_stride,
            "time_unit_internal": "seconds",
            "evidence_timestamp_unit": "milliseconds",
            "max_time_gate_ms": self.max_time_gate_ms,
            "max_duration_seconds": self.max_duration_seconds,
            "overall_status": overall,
            "hybrid_enabled": self.hybrid_enabled,
            "stereo_coverage": max((segment.stereo_coverage for segment in segments), default=0.0),
            "reprojection_error_px": min((segment.reprojection_error_px for segment in segments), default=math.inf),
            "prediction_ratio": max((segment.prediction_ratio for segment in segments), default=0.0),
            "event_resolution": event_diagnostics,
            "segment_windows": segment_windows,
            "counters": dict(self.counters),
            "candidate_filtering": self.candidate_filtering,
            "failure_reason": self._failure_reason,
        }
        def segment_id_for_time(timestamp_sec: float) -> str | None:
            return next(
                (
                    window["segment_id"]
                    for window in segment_windows
                    if window["start_sec"] - 1e-6 <= timestamp_sec <= window["end_sec"] + 1e-6
                ),
                None,
            )

        segmented_measurements = [
            replace(
                measurement,
                segment_id=segment_id_for_time(float(measurement.take_timestamp_ms) / 1000.0),
            )
            for measurement in self.measurements
        ]
        segmented_observations = [
            replace(observation, segment_id=segment_id_for_time(observation.t_sec))
            for observation in observations
        ]
        segmented_pairings = [
            {
                **pairing,
                "segment_id": segment_id_for_time(float(pairing["take_timestamp_ms"]) / 1000.0),
            }
            for pairing in self.pairings
        ]
        evidence = build_stereo_evidence_v1(
            take_id=self.take_id,
            measurements=segmented_measurements,
            pairings=segmented_pairings,
            observations=segmented_observations,
            diagnostics=diagnostics,
            source_context={"job_id": self.job_id, "clock": "CanonicalAnalysisClock"},
        )
        v3["quality_summary"] = {
            "stereo_coverage": diagnostics["stereo_coverage"],
            "reprojection_error_px": diagnostics["reprojection_error_px"],
            "prediction_ratio": diagnostics["prediction_ratio"],
            "measurement_count": len(self.measurements),
            "average_speed_validity": (
                "estimated" if any(metric.average_speed_validity != "unavailable" for metric in metrics_by_segment.values())
                else "unavailable"
            ),
        }
        v3["diagnostics"] = diagnostics
        return CanonicalBallAnalysisOutput(
            v3_trajectory=v3,
            stereo_evidence=evidence,
            diagnostics=diagnostics,
            status=status,
            detail=detail,
        )
