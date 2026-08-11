"""MultiViewJointRun —— joint_tracking_v2 的运行实体(design D7/D8/D10)。

    GlobalState(t-1) → predict(t) → guidance snapshot → View A/B(base+pre-gated guided,
    tracker.update ONCE) → tick barrier → GlobalPlayerAssociator → fusion → GlobalState(t)

- 两路同用 pre-tick snapshot(V1 串行执行、共享模型实例)。
- CanonicalAnalysisClock 保证 source-frame 单调不重复(invariant 8)。
- 长任务语义:每 tick cancellation;进度 = processed/total;原子 finalize 写 v2 artifact。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from app.vision.multiview.analysis_clock import CanonicalAnalysisClock
from app.vision.multiview.association_global import GlobalPlayerAssociator, JointObservation
from app.vision.multiview.guidance import CrossViewGuidance, GuidanceGenerator
from app.vision.multiview.global_state import GlobalPlayerRegistry
from app.vision.multiview.joint_artifact import FusedSample, NormalizedFusedTrajectory, write_fused_v2
from app.vision.multiview.joint_view_runtime import JointViewRuntime
from app.vision.multiview.offline_refinement import F0TickViewState
from app.vision.multiview.court_frame import CanonicalCourtFrameDefinition
from app.services.frame_timing_provider import FrameTimingProvider


class CancellationToken(Protocol):
    def raise_if_cancelled(self) -> None: ...


ProgressCallback = Callable[[int, int], None]


@dataclass
class MultiViewJointRunOutput:
    trajectory: dict[str, object]
    normalized: NormalizedFusedTrajectory
    diagnostics: dict[str, Any]
    counters: dict[str, int] = field(default_factory=dict)
    # F0 trace(供 offline refinement 挖掘 RecoveryWindow)
    f0_trace: dict[str, dict[str, dict[int, F0TickViewState]]] = field(default_factory=dict)
    f0_source_frames: dict[str, dict[int, int | None]] = field(default_factory=dict)
    f0_global_positions: dict[str, dict[int, tuple[float, float]]] = field(default_factory=dict)


class MultiViewJointRun:
    """一次 joint_tracking_v2 分析运行。"""

    def __init__(
        self,
        *,
        run_id: str,
        capture_take_id: str,
        reference_view_id: str,
        clock: CanonicalAnalysisClock,
        runtimes: dict[str, JointViewRuntime],
        registry: GlobalPlayerRegistry,
        associator: GlobalPlayerAssociator,
        guidance_generator: GuidanceGenerator,
        orientations: dict[str, Any],
        inverse_homography: Any,
        frame_width: int,
        frame_height: int,
        canonical_frame_ref: CanonicalCourtFrameDefinition | None = None,
        reference_timing_provider: FrameTimingProvider | None = None,
    ) -> None:
        self.run_id = run_id
        self.capture_take_id = capture_take_id
        self.reference_view_id = reference_view_id
        self.clock = clock
        self.runtimes = runtimes
        self.registry = registry
        self.associator = associator
        self.guidance_generator = guidance_generator
        self.orientations = orientations
        self.inverse_homography = inverse_homography
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.canonical_frame_ref = canonical_frame_ref
        self.reference_timing_provider = reference_timing_provider
        self.counter: dict[str, int] = {}
        # 失败语义:非 reference 视角连续缺帧(解码失败)→ 该时刻起 degraded,不再 step(继续 reference)
        self._consecutive_missing: dict[str, int] = {}
        self.view_degraded: set[str] = set()

    # ---- 主循环 ---------------------------------------------------------------

    def run(
        self,
        *,
        reference_frame_count: int | None = None,
        reference_fps: float,
        frame_stride: int = 1,
        reference_frame_start: int = 0,
        reference_frame_end: int | None = None,
        metric_frame_start: int | None = None,
        metric_frame_end: int | None = None,
        analysis_window: dict[str, Any] | None = None,
        cancellation_token: CancellationToken | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> MultiViewJointRunOutput:
        """按 reference 分析帧逐 tick 推进;返回 v2 产物 + 诊断。"""
        if reference_fps <= 0:
            reference_fps = 30.0
        stride = max(1, int(frame_stride))
        if reference_frame_start < 0:
            raise ValueError("reference_frame_start must be non-negative")
        if reference_frame_end is None:
            if reference_frame_count is None:
                raise ValueError("reference_frame_count or reference_frame_end is required")
            reference_frame_end = reference_frame_start + max(0, reference_frame_count) * stride
        if reference_frame_end <= reference_frame_start:
            raise ValueError("reference frame range must be positive")
        tick_indices = list(range(reference_frame_start, reference_frame_end, stride))
        total_ticks = len(tick_indices)
        metric_start = metric_frame_start if metric_frame_start is not None else reference_frame_start
        metric_end = metric_frame_end if metric_frame_end is not None else reference_frame_end
        if metric_start < reference_frame_start or metric_end > reference_frame_end or metric_end <= metric_start:
            raise ValueError("metric frame range must be inside the reference frame range")
        samples: list[FusedSample] = []
        f0_trace: dict[str, dict[str, dict[int, F0TickViewState]]] = {}
        f0_source_frames: dict[str, dict[int, int | None]] = {}
        f0_global_positions: dict[str, dict[int, tuple[float, float]]] = {}

        for tick_number, ref_idx in enumerate(tick_indices):
            if cancellation_token is not None:
                cancellation_token.raise_if_cancelled()
            timestamp_s = (
                self.reference_timing_provider.take_timestamp_for_frame(ref_idx)
                if self.reference_timing_provider is not None
                else None
            )
            if timestamp_s is None:
                timestamp_s = ref_idx / reference_fps
            metric_eligible_tick = metric_start <= ref_idx < metric_end
            bundle = self.clock.tick(
                reference_frame_index=ref_idx,
                reference_timestamp_seconds=timestamp_s,
            )
            take_ms = bundle.take_timestamp_ms
            predictions = self.registry.predict_all(timestamp_s)

            # ---- guidance snapshot(每 view 一个,pre-tick)----
            guidance_by_view: dict[str, list[CrossViewGuidance]] = {}
            for view_id in self.runtimes:
                if view_id == self.reference_view_id:
                    continue
                guidance_by_view[view_id] = self.guidance_generator.generate_for_view(
                    registry=self.registry,
                    target_view=view_id,
                    orientation=self.orientations.get(view_id),
                    inverse_homography=self.inverse_homography,
                    now_take_ms=take_ms,
                    tick=ref_idx,
                    frame_width=self.frame_width,
                    frame_height=self.frame_height,
                    predictions=predictions,
                )

            # ---- View A/B perception(每 source frame 至多一次 tracker.update)----
            all_obs: list[JointObservation] = []
            for view_id, runtime in self.runtimes.items():
                # 已 degraded 的视角不再 step
                if view_id in self.view_degraded:
                    continue
                status = bundle.frame_status.get(view_id, "unavailable")
                if status != "available":
                    self.counter[f"{view_id}:{status}"] = self.counter.get(f"{view_id}:{status}", 0) + 1
                    continue
                sample = bundle.views[view_id]
                if sample is None:
                    continue
                result = runtime.step(
                    sample.source_frame_index,
                    timestamp_s,
                    guidance=tuple(guidance_by_view.get(view_id, ())),
                )
                if result is None:
                    # 解码缺帧:累计;非 reference 视角连续缺失 → 降级(design D10 失败语义)
                    self._consecutive_missing[view_id] = self._consecutive_missing.get(view_id, 0) + 1
                    if view_id != self.reference_view_id and self._consecutive_missing[view_id] >= 5:
                        self.view_degraded.add(view_id)
                        self.counter[f"{view_id}:degraded"] = self.counter.get(f"{view_id}:degraded", 0) + 1
                    continue
                self._consecutive_missing[view_id] = 0
                all_obs.extend(self._result_to_observations(view_id, result, take_ms))

            # ---- tick barrier:两路完成后才更新 global ----
            updates = self.associator.process_tick(all_obs, timestamp_s, self.orientations)
            fused = self.associator.fuse_assignments(updates, include_tentative=True)
            for gid, (x, y, views) in fused.items():
                self.registry.absorb_measurement(gid, x, y, timestamp_s)
                if len(views) >= 2:
                    self.registry.record_dual_consistent(gid)
                # 逐 tick 轨迹样本(每个 canonical tick 一个真实观测样本)
                if metric_eligible_tick:
                    samples.append(
                        FusedSample(
                            global_player_id=gid,
                            take_timestamp_ms=take_ms,
                            reference_frame_index=ref_idx,
                            x_ft=x,
                            y_ft=y,
                            fusion_status="dual_observed" if len(views) >= 2 else "single_view_fallback",
                            metric_eligible=True,  # 真实观测(非 predicted),可进指标
                            observation_origin="base",
                            contributing_views=list(views),
                        )
                    )

            # ---- F0 trace(供 offline refinement 挖掘)----
            for gid in list(self.registry.players):
                view_trace = f0_trace.setdefault(gid, {})
                for view_id in self.runtimes:
                    matched = [u for u in updates if u.global_id == gid and u.view_id == view_id]
                    if matched:
                        obs = matched[0].observation
                        view_trace.setdefault(view_id, {})[tick_number] = F0TickViewState(
                            observed=True, quality=obs.confidence,
                            canonical_position=(obs.canonical_x_ft, obs.canonical_y_ft),
                            origin=obs.detection_origin,
                        )
                    else:
                        view_trace.setdefault(view_id, {})[tick_number] = F0TickViewState(
                            observed=False, quality=0.0, canonical_position=None, origin="missing",
                        )
            for view_id, _rt in self.runtimes.items():
                bundle_sample = bundle.views.get(view_id)
                if metric_eligible_tick:
                    f0_source_frames.setdefault(view_id, {})[tick_number] = (
                        bundle_sample.source_frame_index if bundle_sample is not None else None
                    )
            if metric_eligible_tick:
                for gid, (x, y, views) in fused.items():
                    f0_global_positions.setdefault(gid, {})[tick_number] = (x, y)

            if progress_callback is not None:
                progress_callback(tick_number + 1, total_ticks)

        # ---- 结束:逐 tick 样本已累积,排序后写 v2 ----
        samples.sort(key=lambda s: (s.take_timestamp_ms, s.global_player_id))
        trajectory = write_fused_v2(
            run_id=self.run_id,
            capture_take_id=self.capture_take_id,
            reference_view_id=self.reference_view_id,
            samples=samples,
        )
        diagnostics = {
            "run_id": self.run_id,
            "schema_version": trajectory["schema_version"],
            "global_player_count": len(self.registry.players),
            "anchored_count": sum(1 for s in self.registry.players.values() if s.cross_view_anchored),
            "confirmed_count": sum(1 for s in self.registry.players.values() if s.lifecycle == "confirmed"),
            "view_degraded": sorted(self.view_degraded),
            "degraded": "joint_degraded" if self.view_degraded else "healthy",
            "counters": dict(self.counter),
            "reference_frame_range": {"start": reference_frame_start, "end": reference_frame_end},
            "metric_frame_range": {"start": metric_start, "end": metric_end},
            "processed_tick_count": total_ticks,
            "canonical_frame_id": (
                self.canonical_frame_ref.frame_id if self.canonical_frame_ref is not None else None
            ),
        }
        if analysis_window is not None:
            diagnostics["analysis_window"] = analysis_window
        return MultiViewJointRunOutput(
            trajectory=trajectory,
            normalized=NormalizedFusedTrajectory(
                schema_version=str(trajectory["schema_version"]),
                run_id=self.run_id,
                capture_take_id=self.capture_take_id,
                reference_view_id=self.reference_view_id,
                samples=samples,
            ),
            diagnostics=diagnostics,
            counters=dict(self.counter),
            f0_trace=f0_trace,
            f0_source_frames=f0_source_frames,
            f0_global_positions=f0_global_positions,
        )

    # ---- 内部 ---------------------------------------------------------------

    @staticmethod
    def _result_to_observations(
        view_id: str,
        result: Any,
        take_ms: float,
    ) -> list[JointObservation]:
        """把 ViewFrameResult 的球场位置转成 JointObservation(canonical 由 associator 归一化)。"""
        obs: list[JointObservation] = []
        for pos in result.frame_positions:
            if pos.court_position is None:
                continue
            obs.append(
                JointObservation(
                    view_id=view_id,
                    source_frame_index=result.frame_index,
                    take_timestamp_ms=take_ms,
                    local_x_ft=pos.court_position[0],
                    local_y_ft=pos.court_position[1],
                    canonical_x_ft=None,
                    canonical_y_ft=None,
                    view_player_id="",
                    track_id=pos.track_id,
                    confidence=pos.confidence or 0.0,
                    projection_confidence=pos.projection_confidence,
                    detection_origin="base",
                )
            )
        return obs
