"""MultiViewJointRun —— joint_tracking_v2 的运行实体(design D7/D8/D10)。

    GlobalState(t-1) → predict(t) → guidance snapshot → View A/B(base+pre-gated guided,
    tracker.update ONCE) → tick barrier → GlobalPlayerAssociator → fusion → GlobalState(t)

- 两路同用 pre-tick snapshot(V1 串行执行、共享模型实例)。
- CanonicalAnalysisClock 保证 source-frame 单调不重复(invariant 8)。
- 长任务语义:每 tick cancellation;进度 = processed/total;原子 finalize 写 v2 artifact。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.services.frame_timing_provider import FrameTimingProvider
from app.vision.multiview.analysis_clock import CanonicalAnalysisClock
from app.vision.multiview.association_global import GlobalPlayerAssociator, JointObservation
from app.vision.multiview.court_frame import CanonicalCourtFrameDefinition
from app.vision.multiview.global_state import GlobalPlayerRegistry
from app.vision.multiview.guidance import CrossViewGuidance, GuidanceGenerator
from app.vision.multiview.joint_artifact import FusedSample, NormalizedFusedTrajectory, write_fused_v2
from app.vision.multiview.joint_view_runtime import JointViewRuntime
from app.vision.multiview.offline_refinement import (
    F0RefinementSnapshot,
    F0TickSnapshot,
    F0TickViewState,
)
from app.vision.multiview.quality import IntrinsicFeatures, view_intrinsic_quality
from app.vision.multiview.recovery_config import P1OnlineRecoveryConfig
from app.vision.multiview.debug_trace import build_joint_debug_trace


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
    f0_snapshot: F0RefinementSnapshot | None = None
    debug_trace: dict[str, object] | None = None
    # Compact recovery evidence retained in memory even when raw debug trace is disabled.
    recovery_evidence: list[dict[str, object]] = field(default_factory=list)


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
        view_geometry: dict[str, dict[str, Any]] | None = None,
        recovery_config: P1OnlineRecoveryConfig | None = None,
        canonical_frame_ref: CanonicalCourtFrameDefinition | None = None,
        reference_timing_provider: FrameTimingProvider | None = None,
        timing_authority_by_view: dict[str, str] | None = None,
        sync_quality: str = "unknown",
        execution_mode: str = "single_view_fallback",
        authoritative_joint_eligible: bool = False,
        debug_trace_enabled: bool = False,
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
        self.view_geometry = dict(view_geometry or {})
        recovery_config_provided = recovery_config is not None
        self.recovery_config = recovery_config or P1OnlineRecoveryConfig()
        if recovery_config_provided:
            # Keep the injected config authoritative for online recovery while
            # leaving legacy callers that omit it on their existing policy.
            policy = self.guidance_generator.policy
            policy.min_donor_quality = self.recovery_config.min_donor_quality
            policy.donor_max_age_ms = self.recovery_config.donor_max_age_ms
            policy.donor_origins = tuple(self.recovery_config.donor_origins)
            policy.max_uncertainty_ft = self.recovery_config.max_prediction_uncertainty_ft
            policy.guidance_cooldown_ticks = self.recovery_config.guidance_cooldown_ticks
            policy.max_regions_per_view_per_tick = self.recovery_config.max_regions_per_view_per_tick
        self.canonical_frame_ref = canonical_frame_ref
        self.reference_timing_provider = reference_timing_provider
        self.timing_authority_by_view = dict(timing_authority_by_view or {})
        self.sync_quality = sync_quality
        self.execution_mode = execution_mode
        self.authoritative_joint_eligible = authoritative_joint_eligible
        self.debug_trace_enabled = bool(debug_trace_enabled)
        self._debug_ticks: list[dict[str, object]] = []
        self._recovery_evidence: list[dict[str, object]] = []
        self.counter: dict[str, int] = {}
        # 失败语义:非 reference 视角连续缺帧(解码失败)→ 该时刻起 degraded,不再 step(继续 reference)
        self._consecutive_missing: dict[str, int] = {}
        self.view_degraded: set[str] = set()
        self._tick_authoritative_by_index: dict[int, bool] = {}
        self.recovery_funnel: dict[str, int] = {}
        self._recovery_episode_by_target: dict[tuple[str, str], str] = {}
        self._next_recovery_episode = 1

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
        f0_predictions: dict[int, dict[str, tuple[float, float]]] = {}
        f0_tick_metadata: dict[int, dict[str, Any]] = {}

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
            funnel_before = dict(self.recovery_funnel)
            bundle = self.clock.tick(
                reference_frame_index=ref_idx,
                reference_timestamp_seconds=timestamp_s,
            )
            tick_authoritative = self._tick_is_authoritative(bundle)
            take_ms = bundle.take_timestamp_ms
            f0_tick_metadata[tick_number] = {
                "canonical_timestamp_ms": take_ms,
                "reference_frame_index": ref_idx,
                "metric_scope": metric_eligible_tick,
                "views": {
                    view_id: {
                        "view_status": bundle.frame_status.get(view_id, "unavailable"),
                        "source_frame_index": (
                            bundle.views[view_id].source_frame_index
                            if bundle.views.get(view_id) is not None
                            else None
                        ),
                        "source_timestamp_ms": (
                            bundle.views[view_id].source_timestamp_ms
                            if bundle.views.get(view_id) is not None
                            else None
                        ),
                        "mapped_take_timestamp_ms": (
                            bundle.views[view_id].mapped_take_timestamp_ms
                            if bundle.views.get(view_id) is not None
                            else None
                        ),
                        "selection_error_ms": (
                            bundle.views[view_id].selection_error_ms
                            if bundle.views.get(view_id) is not None
                            else None
                        ),
                        "timing_authority": (
                            bundle.views[view_id].timing_authority
                            if bundle.views.get(view_id) is not None
                            else "missing"
                        ),
                        "sync_quality": (
                            bundle.views[view_id].sync_quality
                            if bundle.views.get(view_id) is not None
                            else "unknown"
                        ),
                    }
                    for view_id in self.runtimes
                },
            }
            self.registry.age_bindings(
                take_ms,
                weak_after_ms=self.recovery_config.binding_weak_after_ms,
                lost_after_ms=self.recovery_config.binding_lost_after_ms,
            )
            self.registry.update_stale_eligibility(timestamp_s)
            predictions = self.registry.predict_all(timestamp_s)
            f0_predictions[tick_number] = {
                gid: (value[0], value[1]) for gid, value in predictions.items()
            }

            # Freeze recovery denominator from the pre-tick state. A missing
            # target frame is an availability skip, not a visual opportunity.
            for gid, state in self.registry.players.items():
                pred = predictions.get(gid)
                for target_view in self.runtimes:
                    binding = state.view_bindings.get(target_view)
                    if binding is None or binding.visibility not in {"weak", "missing", "lost"}:
                        continue
                    episode_key = (gid, target_view)
                    if episode_key not in self._recovery_episode_by_target:
                        self._recovery_episode_by_target[episode_key] = f"re_{self._next_recovery_episode:06d}"
                        self._next_recovery_episode += 1
                    if bundle.frame_status.get(target_view) != "available":
                        self.counter[f"{target_view}:recovery_skip_target_unavailable"] = (
                            self.counter.get(f"{target_view}:recovery_skip_target_unavailable", 0) + 1
                        )
                        continue
                    if state.lifecycle != "confirmed" or not state.cross_view_anchored:
                        continue
                    if pred is None or pred[2] > self.recovery_config.max_prediction_uncertainty_ft:
                        self.counter[f"{target_view}:recovery_skip_uncertainty"] = (
                            self.counter.get(f"{target_view}:recovery_skip_uncertainty", 0) + 1
                        )
                        continue
                    self.recovery_funnel["recovery_opportunity_count"] = (
                        self.recovery_funnel.get("recovery_opportunity_count", 0) + 1
                    )

            # ---- guidance snapshot(每 view 一个,pre-tick)----
            guidance_by_view: dict[str, list[CrossViewGuidance]] = {}
            for view_id in self.runtimes:
                if not self.recovery_config.enabled:
                    guidance_by_view[view_id] = []
                    continue
                geometry = self.view_geometry.get(view_id, {})
                # A populated per-view geometry map is the P1 source of truth.  Do
                # not silently fall back to reference geometry when the target's
                # own transform or dimensions are incomplete.  Older lightweight
                # adapters that provide no map at all retain their compatibility
                # path and normally do not exercise online recovery.
                if self.view_geometry:
                    orientation = geometry.get("orientation")
                    inverse_homography = geometry.get("inverse_homography")
                    frame_width = int(geometry.get("frame_width") or 0)
                    frame_height = int(geometry.get("frame_height") or 0)
                    geometry_available = bool(
                        geometry.get("available", False)
                        and orientation is not None
                        and inverse_homography is not None
                        and frame_width > 0
                        and frame_height > 0
                    )
                else:
                    orientation = self.orientations.get(view_id)
                    inverse_homography = self.inverse_homography
                    frame_width = int(self.frame_width)
                    frame_height = int(self.frame_height)
                    geometry_available = True
                if not geometry_available:
                    self.counter[f"{view_id}:recovery_skip_missing_target_geometry"] = (
                        self.counter.get(f"{view_id}:recovery_skip_missing_target_geometry", 0) + 1
                    )
                    guidance_by_view[view_id] = []
                    continue
                target_available = bundle.frame_status.get(view_id) == "available"
                guidance_by_view[view_id] = self.guidance_generator.generate_for_view(
                    registry=self.registry,
                    target_view=view_id,
                    orientation=orientation,
                    inverse_homography=inverse_homography,
                    now_take_ms=take_ms,
                    tick=ref_idx,
                    frame_width=frame_width,
                    frame_height=frame_height,
                    predictions=predictions,
                    candidate_donor_views=tuple(other for other in self.runtimes if other != view_id),
                    target_frame_available=target_available,
                    strict_donor=self.recovery_config.enabled,
                )
                for guidance in guidance_by_view[view_id]:
                    guidance.recovery_episode_id = self._recovery_episode_by_target.get(
                        (guidance.global_player_id, view_id)
                    )
                self.recovery_funnel["guidance_generated_count"] = self.recovery_funnel.get(
                    "guidance_generated_count", 0
                ) + len(guidance_by_view[view_id])

            # ---- View A/B perception(每 source frame 至多一次 tracker.update)----
            all_obs: list[JointObservation] = []
            view_results: dict[str, Any] = {}
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
                try:
                    result = runtime.step(
                        sample.source_frame_index,
                        timestamp_s,
                        guidance=tuple(guidance_by_view.get(view_id, ())),
                        timing_context=sample,
                    )
                except TypeError as exc:
                    # Keep lightweight legacy test/runtime adapters usable while
                    # the production JointViewRuntime carries timing context.
                    if "timing_context" not in str(exc):
                        raise
                    result = runtime.step(
                        sample.source_frame_index,
                        timestamp_s,
                        guidance=tuple(guidance_by_view.get(view_id, ())),
                    )
                if result is None:
                    # 解码缺帧:累计;非 reference 视角连续缺失 → 降级(design D10 失败语义)
                    self._consecutive_missing[view_id] = self._consecutive_missing.get(view_id, 0) + 1
                    if guidance_by_view.get(view_id):
                        self.counter[f"{view_id}:recovery_decode_error"] = (
                            self.counter.get(f"{view_id}:recovery_decode_error", 0) + 1
                        )
                    if view_id != self.reference_view_id and self._consecutive_missing[view_id] >= 5:
                        self.view_degraded.add(view_id)
                        self.counter[f"{view_id}:degraded"] = self.counter.get(f"{view_id}:degraded", 0) + 1
                    continue
                self._consecutive_missing[view_id] = 0
                view_results[view_id] = result
                if getattr(result, "guided_detection_invoked", False):
                    self.recovery_funnel["guided_candidate_count"] = self.recovery_funnel.get(
                        "guided_candidate_count", 0
                    ) + int(getattr(result, "guided_candidate_count", 0))
                    self.recovery_funnel["guided_pre_gate_accepted_count"] = (
                        self.recovery_funnel.get("guided_pre_gate_accepted_count", 0)
                        + int(getattr(result, "guided_pre_gate_accepted_count", 0))
                    )
                    self.recovery_funnel["guided_roi_invocation_count"] = self.recovery_funnel.get(
                        "guided_roi_invocation_count", 0
                    ) + len(guidance_by_view.get(view_id, ()))
                    for guidance in guidance_by_view.get(view_id, ()):
                        self.guidance_generator.commit(guidance, ref_idx)
                for reason, count in getattr(result, "guided_reject_reason_counts", {}).items():
                    self.counter[f"{view_id}:recovery_reject_{reason}"] = (
                        self.counter.get(f"{view_id}:recovery_reject_{reason}", 0) + int(count)
                    )
                all_obs.extend(self._result_to_observations(view_id, result, take_ms))
                guided_obs_count = sum(
                    1 for obs in all_obs if obs.view_id == view_id and obs.detection_origin == "guided_roi"
                )
                self.recovery_funnel["guided_candidate_admitted_count"] = (
                    self.recovery_funnel.get("guided_candidate_admitted_count", 0) + guided_obs_count
                )
                self.recovery_funnel["guided_local_identity_admitted_count"] = (
                    self.recovery_funnel.get("guided_local_identity_admitted_count", 0) + guided_obs_count
                )

            # ---- tick barrier:两路完成后才更新 global ----
            updates = self.associator.process_tick(all_obs, timestamp_s, self.orientations, tick=tick_number)
            fused = self.associator.fuse_assignments(updates, include_tentative=True)
            for gid, (x, y, views) in fused.items():
                self.registry.absorb_measurement(gid, x, y, timestamp_s)
                gid_updates = [u for u in updates if u.global_id == gid and u.view_id in views]
                if len(views) >= 2 and all(u.observation.detection_origin == "base" for u in gid_updates):
                    self.registry.record_dual_consistent(gid)
                # Close the target episode exactly once after a formal target-view
                # observation is assigned.  Base wins when both origins survive
                # in the same tick, so it cannot be counted as guided success.
                for target_view in views:
                    episode_key = (gid, target_view)
                    episode_id = self._recovery_episode_by_target.get(episode_key)
                    if episode_id is None:
                        continue
                    target_updates = [u for u in gid_updates if u.view_id == target_view]
                    if not target_updates:
                        continue
                    has_base = any(u.observation.detection_origin == "base" for u in target_updates)
                    has_guided = any(
                        u.observation.detection_origin == "guided_roi"
                        and u.observation.expected_global_player_id == gid
                        for u in target_updates
                    )
                    if has_base:
                        self.recovery_funnel["base_recovered_count"] = (
                            self.recovery_funnel.get("base_recovered_count", 0) + 1
                        )
                        self._recovery_episode_by_target.pop(episode_key, None)
                    elif has_guided:
                        self.recovery_funnel["guided_recovery_success_count"] = (
                            self.recovery_funnel.get("guided_recovery_success_count", 0) + 1
                        )
                        self._recovery_episode_by_target.pop(episode_key, None)
                for update in gid_updates:
                    if (
                        update.observation.detection_origin == "guided_roi"
                        and update.observation.expected_global_player_id == gid
                    ):
                        self.recovery_funnel["guided_expected_global_preserved_count"] = (
                            self.recovery_funnel.get("guided_expected_global_preserved_count", 0) + 1
                        )
                # 逐 tick 轨迹样本(每个 canonical tick 一个真实观测样本)
                if metric_eligible_tick:
                    view_observations = {
                        view_id: self._view_detail(
                            view_id=view_id,
                            sample=bundle.views.get(view_id),
                            status=bundle.frame_status.get(view_id, "unavailable_no_sync"),
                            observation=next(
                                (
                                    update.observation
                                    for update in updates
                                    if update.global_id == gid and update.view_id == view_id
                                ),
                                None,
                            ),
                        )
                        for view_id in self.runtimes
                    }
                    samples.append(
                        FusedSample(
                            global_player_id=gid,
                            take_timestamp_ms=take_ms,
                            reference_frame_index=ref_idx,
                            x_ft=x,
                            y_ft=y,
                            fusion_status="dual_observed" if len(views) >= 2 else "single_view_fallback",
                            metric_eligible=True,  # 真实观测(非 predicted),可进指标
                            observation_origin=(
                                "guided_roi"
                                if any(
                                    update.global_id == gid and update.observation.detection_origin == "guided_roi"
                                    for update in updates
                                )
                                else "base"
                            ),
                            view_observations=view_observations,
                            contributing_views=list(views),
                            authoritative_joint_eligible=tick_authoritative,
                        )
                    )

            if self.debug_trace_enabled:
                self._debug_ticks.append(
                    self._build_debug_tick(
                        tick_number=tick_number,
                        reference_frame_index=ref_idx,
                        take_timestamp_ms=take_ms,
                        tick_authoritative=tick_authoritative,
                        bundle=bundle,
                        view_results=view_results,
                        guidance_by_view=guidance_by_view,
                        predictions=predictions,
                        updates=updates,
                        fused=fused,
                        funnel_before=funnel_before,
                    )
                )
            recovery = {
                key: self.recovery_funnel.get(key, 0) - funnel_before.get(key, 0)
                for key in set(self.recovery_funnel) | set(funnel_before)
                if self.recovery_funnel.get(key, 0) - funnel_before.get(key, 0)
            }
            pre_gate_rejections = sum(
                int(count)
                for view_result in view_results.values()
                for reason, count in getattr(view_result, "guided_reject_reason_counts", {}).items()
                if reason in {"invalid_bbox", "bbox_out_of_frame", "projection_failed", "missing_prediction", "residual_too_large"}
            )
            if pre_gate_rejections:
                recovery["guided_pre_gate_rejected_count"] = pre_gate_rejections
            recovery_keys = set(recovery)
            if any(guidance_by_view.values()) or recovery_keys or any(
                update.observation.detection_origin == "guided_roi" for update in updates
            ):
                self._recovery_evidence.append(
                    {
                        "canonical_tick": tick_number,
                        "canonical_timestamp_ms": take_ms,
                        "recovery": recovery,
                        "views": {
                            view_id: {
                                "guidance": [self._guidance_debug_row(item) for item in guidance_by_view.get(view_id, ())],
                            }
                            for view_id in self.runtimes
                            if guidance_by_view.get(view_id)
                        },
                        "canonical_observations": [
                            self._observation_debug_row(update.global_id, update.observation)
                            for update in updates
                            if update.observation.detection_origin in {"guided_roi", "base"}
                        ],
                    }
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
                            source_frame_index=obs.source_frame_index,
                            source_timestamp_ms=obs.source_timestamp_ms,
                            mapped_take_timestamp_ms=obs.mapped_take_timestamp_ms,
                            selection_error_ms=obs.selection_error_ms,
                            timing_authority=obs.timing_authority,
                            sync_quality=obs.sync_quality,
                            view_status=obs.view_status,
                            observation_status="observed",
                            view_player_id=obs.view_player_id,
                            detector_confidence=obs.confidence,
                            projection_confidence=obs.projection_confidence,
                            tracking_status=obs.tracking_status,
                            bbox=tuple(obs.bbox) if obs.bbox is not None else None,
                        )
                    else:
                        sample = bundle.views.get(view_id)
                        view_trace.setdefault(view_id, {})[tick_number] = F0TickViewState(
                            observed=False, quality=0.0, canonical_position=None, origin="missing",
                            source_frame_index=(sample.source_frame_index if sample is not None else None),
                            source_timestamp_ms=(sample.source_timestamp_ms if sample is not None else None),
                            mapped_take_timestamp_ms=(sample.mapped_take_timestamp_ms if sample is not None else None),
                            selection_error_ms=(sample.selection_error_ms if sample is not None else None),
                            timing_authority=(sample.timing_authority if sample is not None else "missing"),
                            sync_quality=(sample.sync_quality if sample is not None else "unknown"),
                            view_status=bundle.frame_status.get(view_id, "unavailable"),
                            observation_status=(
                                "unavailable" if bundle.frame_status.get(view_id) != "available" else "missing"
                            ),
                        )
            for view_id, _rt in self.runtimes.items():
                bundle_sample = bundle.views.get(view_id)
                f0_source_frames.setdefault(view_id, {})[tick_number] = (
                    bundle_sample.source_frame_index if bundle_sample is not None else None
                )
            if fused:
                for gid, (x, y, _views) in fused.items():
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
            authoritative_run=self.execution_mode == "joint_authoritative",
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
            "timing_authority_by_view": dict(self.timing_authority_by_view),
            "sync_quality": self.sync_quality,
            "execution_mode": self.execution_mode,
            "authoritative_joint_eligible": self.authoritative_joint_eligible,
            "authoritative_eligible_tick_count": sum(
                1 for tick_index in tick_indices if self._tick_authoritative_by_index.get(tick_index, False)
            ),
            "frame_status_counts": dict(self.clock.status_counts),
            "p1_online_recovery_config": self.recovery_config.snapshot(),
            "recovery_funnel": dict(self.recovery_funnel),
            "association_counters": dict(getattr(self.associator, "diagnostics", {})),
            # global-player-roster.v1 快照（stabilize-joint-global-player-roster）：
            # reference view binding 决定 canonical Player_N（display anchor）
            "roster": [
                {
                    "global_player_id": gid,
                    "player_id": _roster_canonical_player_id(state, self.reference_view_id),
                    "label": _roster_display_label(state, self.reference_view_id),
                    "status": state.roster_status,
                    "lifecycle": state.lifecycle,
                    "cross_view_anchored": state.cross_view_anchored,
                    "bindings": {
                        view_id: {
                            "view_player_id": binding.view_player_id,
                            "track_id": binding.track_id,
                            "visibility": binding.visibility,
                        }
                        for view_id, binding in state.view_bindings.items()
                        if binding.view_player_id is not None
                    },
                }
                for gid, state in sorted(self.registry.players.items())
                if state.roster_status is not None
            ],
            "roster_state": self.registry.roster_state,
            "expected_player_count": self.registry.expected_player_count,
            "roster_occupied_count": sum(
                1 for s in self.registry.players.values() if s.roster_status is not None
            ),
            "confirmed_player_count": sum(
                1 for s in self.registry.players.values() if s.roster_status == "confirmed"
            ),
        }
        if analysis_window is not None:
            diagnostics["analysis_window"] = analysis_window
        debug_trace = (
            build_joint_debug_trace(
                run_id=self.run_id,
                capture_take_id=self.capture_take_id,
                reference_view_id=self.reference_view_id,
                timing_authority_by_view=self.timing_authority_by_view,
                sync_quality=self.sync_quality,
                execution_mode=self.execution_mode,
                authoritative_joint_eligible=self.authoritative_joint_eligible,
                ticks=self._debug_ticks,
            )
            if self.debug_trace_enabled
            else None
        )
        snapshot_ticks: list[F0TickSnapshot] = []
        for tick_number in sorted(f0_tick_metadata):
            metadata = f0_tick_metadata[tick_number]
            observations: list[tuple[str, str, F0TickViewState]] = []
            for gid in sorted(f0_trace):
                for view_id in self.runtimes:
                    state = f0_trace.get(gid, {}).get(view_id, {}).get(tick_number)
                    if state is not None:
                        observations.append((gid, view_id, state))
            predictions_for_tick = tuple(
                sorted(f0_predictions.get(tick_number, {}).items(), key=lambda item: item[0])
            )
            snapshot_ticks.append(
                F0TickSnapshot(
                    canonical_tick=tick_number,
                    canonical_timestamp_ms=float(metadata["canonical_timestamp_ms"]),
                    reference_frame_index=int(metadata["reference_frame_index"]),
                    observations=tuple(observations),
                    global_positions=tuple(
                        (gid, positions[tick_number])
                        for gid, positions in sorted(f0_global_positions.items())
                        if tick_number in positions
                    ),
                    predictions=predictions_for_tick,
                    metric_scope=bool(metadata["metric_scope"]),
                )
            )
        f0_snapshot = F0RefinementSnapshot(
            run_id=self.run_id,
            capture_take_id=self.capture_take_id,
            reference_view_id=self.reference_view_id,
            view_ids=tuple(self.runtimes),
            global_player_ids=tuple(sorted(f0_trace)),
            ticks=tuple(snapshot_ticks),
            config_snapshot={"p1_online_recovery": self.recovery_config.snapshot()},
        )
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
            f0_snapshot=f0_snapshot,
            debug_trace=debug_trace,
            recovery_evidence=list(self._recovery_evidence),
        )

    # ---- 内部 ---------------------------------------------------------------

    @staticmethod
    def _view_detail(*, view_id: str, sample: Any, status: str, observation: JointObservation | None) -> dict[str, Any]:
        """Serialize timing context even when a view has no player observation."""
        if observation is not None:
            return {
                "view_id": view_id,
                "view_status": status,
                "source_frame_index": observation.source_frame_index,
                "source_timestamp_ms": observation.source_timestamp_ms,
                "mapped_take_timestamp_ms": observation.mapped_take_timestamp_ms,
                "selection_error_ms": observation.selection_error_ms,
                "timing_authority": observation.timing_authority,
                "sync_quality": observation.sync_quality,
                "x_ft": observation.local_x_ft,
                "y_ft": observation.local_y_ft,
                "quality": observation.confidence,
                "view_player_id": observation.view_player_id,
                "local_identity_epoch": observation.local_identity_epoch,
                "source_track_id": observation.track_id,
                "detection_origin": observation.detection_origin,
                "guidance_id": observation.guidance_id,
                "donor_view": observation.donor_view,
                "expected_global_player_id": observation.expected_global_player_id,
                "pre_gate_residual_ft": observation.pre_gate_residual_ft,
                "intrinsic_quality": observation.intrinsic_quality,
                "recovery_episode_id": observation.recovery_episode_id,
            }
        return {
            "view_id": view_id,
            "view_status": status,
            "view_player_id": None,
            "local_identity_epoch": None,
            "source_track_id": None,
            "detection_origin": "missing",
            "guidance_id": None,
            "donor_view": None,
            "expected_global_player_id": None,
            "pre_gate_residual_ft": None,
            "intrinsic_quality": None,
            "recovery_episode_id": None,
            "source_frame_index": sample.source_frame_index if sample is not None else None,
            "source_timestamp_ms": sample.source_timestamp_ms if sample is not None else None,
            "mapped_take_timestamp_ms": sample.mapped_take_timestamp_ms if sample is not None else None,
            "selection_error_ms": sample.selection_error_ms if sample is not None else None,
            "timing_authority": sample.timing_authority if sample is not None else "missing",
            "sync_quality": sample.sync_quality if sample is not None else "unknown",
        }

    def _tick_is_authoritative(self, bundle: Any) -> bool:
        reference_sample = bundle.views.get(self.reference_view_id)
        if not self.authoritative_joint_eligible:
            if reference_sample is not None:
                self._tick_authoritative_by_index[reference_sample.source_frame_index] = False
            return False
        max_error_ms = getattr(self.clock, "max_pairing_error_ms", 1000.0 / 30.0)
        eligible = all(
            bundle.frame_status.get(view_id) == "available"
            and (sample := bundle.views.get(view_id)) is not None
            and getattr(sample, "timing_authority", "missing") == "source_pts"
            and abs(getattr(sample, "selection_error_ms", 0.0) or 0.0) <= max_error_ms
            for view_id in self.runtimes
        )
        if reference_sample is not None:
            self._tick_authoritative_by_index[reference_sample.source_frame_index] = eligible
        return eligible

    def _build_debug_tick(
        self,
        *,
        tick_number: int,
        reference_frame_index: int,
        take_timestamp_ms: float,
        tick_authoritative: bool,
        bundle: Any,
        view_results: dict[str, Any],
        guidance_by_view: dict[str, list[CrossViewGuidance]],
        predictions: dict[str, tuple[float, float, float]],
        updates: list[Any],
        fused: dict[str, tuple[float, float, list[str]]],
        funnel_before: dict[str, int],
    ) -> dict[str, object]:
        views: dict[str, object] = {}
        for view_id in self.runtimes:
            sample = bundle.views.get(view_id)
            result = view_results.get(view_id)
            status = bundle.frame_status.get(view_id, "unavailable")
            observations = [
                self._observation_debug_row(update.global_id, update.observation)
                for update in updates
                if update.view_id == view_id
            ]
            position_by_track = {
                int(position.track_id): position
                for position in getattr(result, "frame_positions", [])
            }
            detections = []
            for detection in getattr(result, "frame_detections", []) if result is not None else []:
                track_id = int(detection.track_id) if detection.track_id is not None else None
                position = position_by_track.get(track_id) if track_id is not None else None
                detections.append(
                    {
                        "bbox": list(detection.bbox),
                        "image_footpoint": list(position.image_footpoint) if position is not None else None,
                        "track_id": track_id,
                        "player_id": detection.player_id,
                        "confidence": detection.confidence,
                        "tracking_status": "detected" if track_id is not None else "unmatched",
                        "court_position": (
                            list(position.court_position)
                            if position is not None and position.court_position
                            else None
                        ),
                    }
                )
            bindings: dict[str, object] = {}
            for global_id, state in self.registry.players.items():
                binding = state.view_bindings.get(view_id)
                bindings[global_id] = (
                    {
                        "visibility": binding.visibility,
                        "view_player_id": binding.view_player_id,
                        "identity_epoch": binding.local_identity_epoch,
                        "track_id": binding.track_id,
                        "quality": binding.quality,
                        "lock_state": binding.lock_state,
                        "tracking_status": binding.tracking_status,
                        "observation_origin": binding.observation_origin,
                        "guidance_id": binding.guidance_id,
                        "donor_view": binding.donor_view,
                    }
                    if binding is not None
                    else {
                        "visibility": "missing",
                        "view_player_id": None,
                        "identity_epoch": None,
                        "track_id": None,
                    }
                )
            views[view_id] = {
                "status": status,
                "source_frame_index": sample.source_frame_index if sample is not None else None,
                "source_timestamp_ms": sample.source_timestamp_ms if sample is not None else None,
                "mapped_take_timestamp_ms": sample.mapped_take_timestamp_ms if sample is not None else None,
                "selection_error_ms": sample.selection_error_ms if sample is not None else None,
                "timing_authority": sample.timing_authority if sample is not None else "missing",
                "sync_quality": sample.sync_quality if sample is not None else "unknown",
                "observations": observations,
                "observation_status": (
                    "unavailable" if status != "available" else ("observed" if observations else "missing")
                ),
                "detections": detections,
                "guidance": [self._guidance_debug_row(item) for item in guidance_by_view.get(view_id, ())],
                "bindings": bindings,
            }
        recovery = {
            key: self.recovery_funnel.get(key, 0) - funnel_before.get(key, 0)
            for key in set(self.recovery_funnel) | set(funnel_before)
            if self.recovery_funnel.get(key, 0) - funnel_before.get(key, 0)
        }
        return {
            "canonical_tick": tick_number,
            "reference_frame_index": reference_frame_index,
            "canonical_timestamp_ms": take_timestamp_ms,
            "authoritative_tick": tick_authoritative,
            "frame_status": dict(bundle.frame_status),
            "views": views,
            "global_predictions": {
                gid: {"x_ft": value[0], "y_ft": value[1], "uncertainty_ft": value[2]}
                for gid, value in predictions.items()
            },
            "canonical_observations": [
                self._observation_debug_row(update.global_id, update.observation)
                for update in updates
            ],
            "fused": {
                global_id: {"x_ft": x, "y_ft": y, "views": list(views_for_player)}
                for global_id, (x, y, views_for_player) in fused.items()
            },
            "recovery": recovery,
        }

    @staticmethod
    def _guidance_debug_row(guidance: CrossViewGuidance) -> dict[str, object]:
        return {
            "guidance_id": guidance.guidance_id,
            "global_player_id": guidance.global_player_id,
            "target_view": guidance.target_view,
            "roi": list(guidance.roi),
            "predicted_canonical_position": list(guidance.predicted_canonical_position),
            "predicted_local_position": list(guidance.predicted_local_position),
            "expected_image_position": list(guidance.expected_image_position),
            "uncertainty_ft": guidance.uncertainty_ft,
            "confidence": guidance.confidence,
            "donor_view": guidance.donor_view,
            "donor_view_player_id": guidance.donor_view_player_id,
            "donor_source_frame_index": guidance.donor_source_frame_index,
            "donor_take_timestamp_ms": guidance.donor_take_timestamp_ms,
            "donor_quality": guidance.donor_quality,
            "donor_origin": guidance.donor_origin,
            "expected_global_player_id": guidance.expected_global_player_id,
            "recovery_episode_id": guidance.recovery_episode_id,
        }

    @staticmethod
    def _observation_debug_row(global_id: str, observation: JointObservation) -> dict[str, object]:
        return {
            "global_player_id": global_id,
            "view_id": observation.view_id,
            "source_frame_index": observation.source_frame_index,
            "take_timestamp_ms": observation.take_timestamp_ms,
            "source_timestamp_ms": observation.source_timestamp_ms,
            "mapped_take_timestamp_ms": observation.mapped_take_timestamp_ms,
            "selection_error_ms": observation.selection_error_ms,
            "bbox": None,
            "image_footpoint": None,
            "local_x_ft": observation.local_x_ft,
            "local_y_ft": observation.local_y_ft,
            "canonical_x_ft": observation.canonical_x_ft,
            "canonical_y_ft": observation.canonical_y_ft,
            "view_player_id": observation.view_player_id,
            "local_identity_epoch": observation.local_identity_epoch,
            "track_id": observation.track_id,
            "confidence": observation.confidence,
            "detection_origin": observation.detection_origin,
            "guidance_id": observation.guidance_id,
            "donor_view": observation.donor_view,
            "expected_global_player_id": observation.expected_global_player_id,
            "pre_gate_residual_ft": observation.pre_gate_residual_ft,
            "timing_authority": observation.timing_authority,
            "sync_quality": observation.sync_quality,
            "tracking_status": observation.tracking_status,
            "lock_state": observation.lock_state,
            "bbox": list(observation.bbox) if observation.bbox is not None else None,
            "image_footpoint": list(observation.image_footpoint)
            if observation.image_footpoint is not None
            else None,
        }

    @staticmethod
    def _result_to_observations(
        view_id: str,
        result: Any,
        take_ms: float,
    ) -> list[JointObservation]:
        """把 ViewFrameResult 的球场位置转成 JointObservation(canonical 由 associator 归一化)。"""
        obs: list[JointObservation] = []
        positions_by_track = {int(pos.track_id): pos for pos in result.frame_positions}
        formal_detections = [
            detection for detection in getattr(result, "frame_detections", [])
            if getattr(detection, "player_id", None)
        ]
        # Lightweight legacy adapters may not expose formal detections. Production
        # ViewTrackingSession uses this branch only for stable local identities.
        candidates = formal_detections or (
            [] if hasattr(result, "frame_detections") else list(result.frame_positions)
        )
        for item in candidates:
            pos = (
                positions_by_track.get(int(getattr(item, "track_id", 0)))
                if formal_detections
                else item
            )
            if pos is None:
                continue
            if pos.court_position is None:
                continue
            track_id = int(pos.track_id)
            player_id = getattr(item, "player_id", None) or getattr(
                result, "local_identity_by_track", {}
            ).get(track_id, "")
            if not player_id:
                continue
            obs.append(
                JointObservation(
                    view_id=view_id,
                    source_frame_index=result.frame_index,
                    take_timestamp_ms=(
                        result.mapped_take_timestamp_ms
                        if result.mapped_take_timestamp_ms is not None
                        else take_ms
                    ),
                    local_x_ft=pos.court_position[0],
                    local_y_ft=pos.court_position[1],
                    canonical_x_ft=None,
                    canonical_y_ft=None,
                    view_player_id=player_id,
                    local_identity_epoch=int(getattr(result, "local_identity_epoch_by_track", {}).get(track_id, 0)),
                    track_id=track_id,
                    confidence=pos.confidence or 0.0,
                    projection_confidence=pos.projection_confidence,
                    detection_origin=getattr(result, "observation_origin_by_track", {}).get(track_id, "base"),
                    guidance_id=getattr(result, "guidance_id_by_track", {}).get(track_id),
                    donor_view=getattr(result, "donor_view_by_track", {}).get(track_id),
                    expected_global_player_id=getattr(result, "expected_global_by_track", {}).get(track_id),
                    pre_gate_residual_ft=getattr(result, "pre_gate_residual_by_track", {}).get(track_id),
                    recovery_episode_id=getattr(result, "recovery_episode_by_track", {}).get(track_id),
                    bbox=list(pos.bbox),
                    image_footpoint=tuple(pos.image_footpoint),
                    intrinsic_quality=view_intrinsic_quality(
                        IntrinsicFeatures(
                            detector_confidence=pos.confidence or 0.0,
                            bbox_height_px=float(pos.bbox[3] - pos.bbox[1]),
                            frame_height_px=float(getattr(item, "source_height", 0) or 0) or None,
                            projection_confidence=pos.projection_confidence,
                            footpoint_method=pos.footpoint_method,
                            tracking_status="detected",
                        )
                    ),
                    source_timestamp_ms=getattr(result, "source_timestamp_ms", None),
                    mapped_take_timestamp_ms=(
                        result.mapped_take_timestamp_ms
                        if getattr(result, "mapped_take_timestamp_ms", None) is not None
                        else take_ms
                    ),
                    selection_error_ms=getattr(result, "selection_error_ms", None),
                    timing_authority=getattr(result, "timing_authority", "missing"),
                    sync_quality=getattr(result, "sync_quality", "unknown"),
                    tracking_status=str(getattr(pos, "tracking_status", "detected")),
                )
            )
        return obs


# ---- Global Roster 公开映射辅助（stabilize-joint-global-player-roster）----


def _roster_canonical_player_id(state, reference_view_id: str) -> str | None:
    """reference view binding 决定 canonical `Player_N`（display anchor）。

    - 稳定绑定 reference view 的 local identity → 公开身份即该 `Player_N`；
    - 仅有 non-reference evidence → 暂缓分配（返回 None）；
    - 整场 reference 缺失 → 由 composer 用 deterministic fallback（slot 顺序）兜底。
    """
    binding = state.view_bindings.get(reference_view_id)
    if binding is not None and binding.view_player_id:
        pid = binding.view_player_id
        if pid.startswith("Player_"):
            return pid
    return None


def _roster_display_label(state, reference_view_id: str) -> str | None:
    """`Player_N` → `Pn` 展示标签（与结构化热力图 P1..P4 对齐）。"""
    pid = _roster_canonical_player_id(state, reference_view_id)
    if not pid:
        return None
    return f"P{pid.rsplit('_', 1)[-1]}"
