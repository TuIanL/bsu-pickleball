"""Canonical-tick 双摄球处理器。

该模块只负责把 joint 的同步帧捆绑转换成球侧 evidence/v3。它不拥有视频时间轴，
也不重新打开视频；每个 tick 使用调用方已经确定的 ``SynchronizedFrameBundle``。
球 detector 每个视角每个 tick 只调用一次，tracker 通过 ``update_from_candidates``
消费同一份候选集合。
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Mapping

import numpy as np

from app.vision.multiview.ball_stereo.artifact_builders import (
    build_stereo_evidence_v1,
    build_v3_trajectory,
)
from app.vision.multiview.ball_stereo.association import associate_views
from app.vision.multiview.ball_stereo.metrics import compute_metrics
from app.vision.multiview.ball_stereo.segment_reconstruction import (
    Observation,
    Reconstructed3DSegment,
    reconstruct_segment,
)
from app.vision.multiview.ball_stereo.stereo_measurement import BallStereoMeasurement, measure_stereo


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
        max_time_gate_ms: float = 40.0,
        max_duration_seconds: float | None = None,
        disabled_reason: str | None = None,
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
        self.max_time_gate_ms = float(max_time_gate_ms)
        self.max_duration_seconds = (
            float(max_duration_seconds)
            if max_duration_seconds is not None and float(max_duration_seconds) > 0
            else None
        )
        self._started_monotonic = time.monotonic()
        self.disabled_reason = disabled_reason
        self.measurements: list[BallStereoMeasurement] = []
        self.observations: list[Observation] = []
        self.pairings: list[dict[str, Any]] = []
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
                sample = tracker.update_from_candidates(
                    frame_index=int(frame_sample.source_frame_index),
                    timestamp_sec=_canonical_timestamp_ms(frame_sample) / 1000.0,
                    view_candidates=raw_candidates,
                    frame_shape=frame.shape,
                    homography=None,
                )
            except Exception as exc:  # noqa: BLE001 - 球侧不可用不得破坏球员主链
                self._disable(f"球检测运行失败：{exc}")
                return
            self.counters["available_view_frames"] += 1
            candidates_by_view[view_id] = [_candidate_tuple(item) for item in raw_candidates]
            samples_by_view[view_id] = sample
            if getattr(sample, "accepted", False) and getattr(sample, "image_xy", None) is not None:
                self.counters["accepted_view_observations"] += 1

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
            }
        )
        self.measurements.append(measurement)
        self.observations.extend(
            [
                Observation(
                    ref_ts / 1000.0,
                    0,
                    float(pair.cam1_candidate[0]),
                    float(pair.cam1_candidate[1]),
                    self.projections[self.reference_view_id],
                    paired=True,
                ),
                Observation(
                    sec_ts / 1000.0,
                    1,
                    float(pair.cam2_candidate[0]),
                    float(pair.cam2_candidate[1]),
                    self.projections[self.secondary_view_id],
                    paired=True,
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
                "time_gate_ms": self.max_time_gate_ms,
            }
        )

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
                )
            )

    def _disable(self, reason: str) -> None:
        self._disabled = True
        self._failure_reason = reason

    def finish(self) -> CanonicalBallAnalysisOutput:
        observations = sorted(self.observations, key=lambda item: (item.t_sec, item.cam_index))
        duration = max((item.t_sec for item in observations), default=0.0) - min(
            (item.t_sec for item in observations), default=0.0
        )
        duration = max(duration, 0.3)
        if observations and not self._failure_reason:
            segment = reconstruct_segment(
                segment_id="seg_canonical_1",
                observations=observations,
                max_control_points=8,
            )
        else:
            segment = Reconstructed3DSegment(segment_id="seg_canonical_1", status="UNAVAILABLE")
        metrics = compute_metrics(segment, duration_sec=duration) if segment.samples else None
        v3 = build_v3_trajectory(
            job_id=self.job_id,
            take_id=self.take_id,
            bounce_source="canonical_reference_view",
            segments=[segment],
            landing=None,
            metrics_by_segment={segment.segment_id: metrics} if metrics else {},
            duration_by_segment={segment.segment_id: duration},
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
            "stereo_coverage": segment.stereo_coverage,
            "reprojection_error_px": segment.reprojection_error_px,
            "prediction_ratio": segment.prediction_ratio,
            "counters": dict(self.counters),
            "failure_reason": self._failure_reason,
        }
        evidence = build_stereo_evidence_v1(
            take_id=self.take_id,
            measurements=self.measurements,
            pairings=self.pairings,
            diagnostics=diagnostics,
            source_context={"job_id": self.job_id, "clock": "CanonicalAnalysisClock"},
        )
        v3["quality_summary"] = {
            "stereo_coverage": segment.stereo_coverage,
            "reprojection_error_px": segment.reprojection_error_px,
            "prediction_ratio": segment.prediction_ratio,
            "measurement_count": len(self.measurements),
            "average_speed_validity": metrics.average_speed_validity if metrics else "unavailable",
        }
        v3["diagnostics"] = diagnostics
        return CanonicalBallAnalysisOutput(
            v3_trajectory=v3,
            stereo_evidence=evidence,
            diagnostics=diagnostics,
            status=status,
            detail=detail,
        )
