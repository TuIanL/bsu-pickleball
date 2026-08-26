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


def interpolate_short_confirmed_identity_gaps(
    samples: list[FusedSample],
    *,
    max_missing_ticks: int = 2,
) -> list[FusedSample]:
    """Bridge tiny gaps bounded by the same confirmed global identity.

    The generated court samples are explicitly interpolated and contain no
    view/bbox provenance, so they cannot be mistaken for detector evidence.
    """
    if max_missing_ticks <= 0 or not samples:
        return sorted(samples, key=lambda item: (item.take_timestamp_ms, item.global_player_id))

    timeline = sorted({(item.reference_frame_index, item.take_timestamp_ms) for item in samples})
    timeline_index = {frame_index: index for index, (frame_index, _timestamp) in enumerate(timeline)}
    by_player: dict[str, list[FusedSample]] = {}
    for sample in samples:
        by_player.setdefault(sample.global_player_id, []).append(sample)

    accepted = {"confirmed_observed", "confirmed_recovered"}
    output: list[FusedSample] = list(samples)
    for player_samples in by_player.values():
        ordered = sorted(player_samples, key=lambda item: item.reference_frame_index)
        for left, right in zip(ordered, ordered[1:]):
            left_index = timeline_index.get(left.reference_frame_index)
            right_index = timeline_index.get(right.reference_frame_index)
            if left_index is None or right_index is None:
                continue
            missing = right_index - left_index - 1
            if missing <= 0 or missing > max_missing_ticks:
                continue
            if left.identity_status not in accepted or right.identity_status not in accepted:
                continue
            if left.identity_epoch != right.identity_epoch:
                continue
            # Canonical court length is 44 ft. Never bridge an apparent net crossing.
            if (left.y_ft < 22.0) != (right.y_ft < 22.0):
                continue
            for offset in range(1, missing + 1):
                frame_index, timestamp_ms = timeline[left_index + offset]
                ratio = offset / (missing + 1)
                output.append(
                    FusedSample(
                        global_player_id=left.global_player_id,
                        take_timestamp_ms=timestamp_ms,
                        reference_frame_index=frame_index,
                        x_ft=left.x_ft + (right.x_ft - left.x_ft) * ratio,
                        y_ft=left.y_ft + (right.y_ft - left.y_ft) * ratio,
                        fusion_status="interpolated",
                        metric_eligible=True,
                        observation_origin="interpolated",
                        view_observations={},
                        contributing_views=[],
                        authoritative_joint_eligible=(
                            left.authoritative_joint_eligible and right.authoritative_joint_eligible
                        ),
                        identity_status="interpolated",
                        identity_epoch=left.identity_epoch,
                        binding_provenance={
                            "interpolation": {
                                "left_reference_frame_index": left.reference_frame_index,
                                "right_reference_frame_index": right.reference_frame_index,
                            }
                        },
                    )
                )
    return sorted(output, key=lambda item: (item.take_timestamp_ms, item.global_player_id))


class _LegacyCommittedResult:
    """轻量 legacy runtime 的已 commit 结果包装（无两阶段能力时回退旧 step）。"""

    def __init__(self, result: Any) -> None:
        self.result = result


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
    # player display diagnostics（只读 observability；构建失败不影响核心结果）
    display_diagnostics_payload: dict[str, object] | None = None
    display_diagnostics_error: str | None = None
    # canonical-tick 球路阶段输出；由 executor 在最终 compose 前发布。
    ball_analysis: Any | None = None


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
        ball_processor: Any | None = None,
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
            policy.fast_recovery_enabled = self.recovery_config.fast_recovery_enabled
            policy.same_tick_recovery_enabled = self.recovery_config.same_tick_recovery_enabled
            policy.pre_association_gate_ft = self.recovery_config.pre_association_gate_ft
            policy.ambiguity_margin = self.recovery_config.ambiguity_margin
        self.canonical_frame_ref = canonical_frame_ref
        self.reference_timing_provider = reference_timing_provider
        self.timing_authority_by_view = dict(timing_authority_by_view or {})
        self.sync_quality = sync_quality
        self.execution_mode = execution_mode
        self.authoritative_joint_eligible = authoritative_joint_eligible
        self.debug_trace_enabled = bool(debug_trace_enabled)
        self.ball_processor = ball_processor
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
        # player display diagnostics（只读；失败不影响核心结果）
        self._display_diag_rows: list[Any] = []
        self._display_diag_error: str | None = None
        # same-tick RecoveryAttemptLedger（B-Phase-2）：同 pair 去重 + 每 view ROI 预算
        self._same_tick_attempted: set[tuple[str, str]] = set()
        self._same_tick_ledger: dict[str, list[Any]] = {view_id: [] for view_id in self.runtimes}

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
            # same-tick RecoveryAttemptLedger：预算按 canonical tick 重置
            self._same_tick_attempted = set()
            self._same_tick_ledger = {view_id: [] for view_id in self.runtimes}
            bundle = self.clock.tick(
                reference_frame_index=ref_idx,
                reference_timestamp_seconds=timestamp_s,
            )
            if self.ball_processor is not None:
                # 先只准备球候选；tracker commit 延迟到当 tick 球员 barrier 之后。
                # 球侧异常由 processor 自身降级，不得打断 player joint 的主链。
                prepare = getattr(self.ball_processor, "prepare_tick", None)
                if prepare is not None:
                    prepare(tick_id=tick_number, bundle=bundle)
                else:
                    # 历史注入的球处理器仍走旧 process_tick 兼容路径。
                    self.ball_processor.process_tick(tick_id=tick_number, bundle=bundle)
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
                        "mapping_mode": (
                            bundle.views[view_id].mapping_mode
                            if bundle.views.get(view_id) is not None
                            else None
                        ),
                        "extrapolation_distance_ms": (
                            bundle.views[view_id].extrapolation_distance_ms
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
            # 触发资格用共享 predicate（与 guidance 同一语义，消灭幽灵 guidance）：
            # visibility weak/missing/lost OR fast path（available miss >= 1）。
            from app.vision.multiview.recovery_config import is_target_recovery_eligible

            for gid, state in self.registry.players.items():
                pred = predictions.get(gid)
                for target_view in self.runtimes:
                    binding = state.view_bindings.get(target_view)
                    if binding is None or not is_target_recovery_eligible(
                        binding, self.recovery_config.fast_recovery_enabled
                    ):
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

            # ---- View A/B perception：两阶段（B-Phase-2 same-tick usable-candidate recovery）----
            # 阶段 1：每 view prepare（decode 一次 + base/ROI/pre-tick guided/merge，不 update tracker）
            # 阶段 2（barrier 后）：pre-association → same-tick guidance → complete（tracker.update ONCE）
            all_obs: list[JointObservation] = []
            view_results: dict[str, Any] = {}
            prepared_by_view: dict[str, Any] = {}
            same_tick_guidance_by_view: dict[str, list[Any]] = {}
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
                prepared = self._runtime_prepare(
                    runtime, sample, timestamp_s, tuple(guidance_by_view.get(view_id, ()))
                )
                if prepared is None:
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
                prepared_by_view[view_id] = prepared

            # ---- current-tick barrier：两路 prepare 完成后做 same-tick 决策 ----
            if self.recovery_config.same_tick_recovery_enabled and prepared_by_view:
                same_tick_guidance_by_view = self._select_same_tick_guidance(
                    prepared_by_view=prepared_by_view,
                    predictions=predictions,
                    take_ms=take_ms,
                    tick_number=tick_number,
                )

            # ---- 阶段 2：complete（tracker.update ONCE/view）----
            for view_id, runtime in self.runtimes.items():
                prepared = prepared_by_view.get(view_id)
                if prepared is None:
                    continue
                sample = bundle.views[view_id]
                result = self._runtime_complete(
                    runtime, prepared, tuple(same_tick_guidance_by_view.get(view_id, ())), sample
                )
                if result is None:
                    continue
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
                # same-tick 单独计数（B-Phase-2）：本 view 有 same-tick guidance 且形成 formal obs
                if same_tick_guidance_by_view.get(view_id):
                    self.recovery_funnel["same_tick_roi_invocation_count"] = (
                        self.recovery_funnel.get("same_tick_roi_invocation_count", 0)
                        + len(same_tick_guidance_by_view.get(view_id, ()))
                    )
                    same_tick_obs = [
                        obs for obs in all_obs
                        if obs.view_id == view_id and obs.detection_origin == "guided_roi"
                        and obs.guidance_id and str(obs.guidance_id).startswith("st_")
                    ]
                    if same_tick_obs:
                        self.recovery_funnel["same_tick_formal_observation_count"] = (
                            self.recovery_funnel.get("same_tick_formal_observation_count", 0)
                            + len(same_tick_obs)
                        )

            # ---- tick barrier:两路完成后才更新 global ----
            updates = self.associator.process_tick(all_obs, timestamp_s, self.orientations, tick=tick_number)
            # D1:conflict 仲裁使用 pre-tick prediction（tick barrier 前冻结,含 uncertainty）
            fused = self.associator.fuse_assignments(
                updates, include_tentative=True, predictions=predictions,
            )
            if self.ball_processor is not None and hasattr(self.ball_processor, "commit_tick"):
                # 当前 tick 的球员观察和 global identity 已完成；语义策略在此之后
                # 评估，随后每视角 tracker 最多 commit 一次。
                self.ball_processor.commit_tick(
                    tick_id=tick_number,
                    bundle=bundle,
                    semantic_evidence={
                        "player_observation_count": len(all_obs),
                        "global_player_count": len(fused),
                        "player_context_ready": True,
                    },
                )

            # ---- available-miss ledger（顺序冻结：association → ledger →
            #      display diagnostics → fusion/debug）----
            # attempt authority = view_results（view 本 tick 真实被 perception 成功尝试）；
            # frame_status 仅表示 source availability；view_degraded / decode 失败
            # （view_results 无该 view）不计 miss。
            assigned_views: dict[tuple[str, str], bool] = {}
            for update in updates:
                assigned_views[(update.global_id, update.view_id)] = True
            for gid, state in self.registry.players.items():
                if state.lifecycle != "confirmed":
                    continue
                for view_id in self.runtimes:
                    if view_id not in view_results:
                        continue  # view 未被成功尝试（degraded / decode 失败等）→ skip
                    if bundle.frame_status.get(view_id) != "available":
                        continue  # source 不可用 → availability skip
                    binding = state.view_bindings.get(view_id)
                    if binding is None:
                        continue
                    binding.record_attempt(
                        observed=assigned_views.get((gid, view_id), False),
                        take_ms=take_ms,
                        tick=tick_number,
                    )

            # ---- player display diagnostics（只读 observability；失败不影响核心结果）----
            try:
                from app.vision.multiview.player_display_diagnostics import build_display_diagnostics_rows

                roster_snapshot = [
                    {
                        "global_player_id": gid,
                        "player_id": _roster_canonical_player_id(state, self.reference_view_id),
                        "lifecycle": state.lifecycle,
                        "bindings": {
                            view_id: {
                                "view_player_id": binding.view_player_id,
                                "visibility": binding.visibility,
                                "available_miss_streak": binding.consecutive_available_misses,
                            }
                            for view_id, binding in state.view_bindings.items()
                            if binding.view_player_id is not None
                        },
                    }
                    for gid, state in self.registry.players.items()
                    if state.roster_status is not None
                ]
                self._display_diag_rows.extend(
                    build_display_diagnostics_rows(
                        canonical_tick=tick_number,
                        timestamp_ms=take_ms,
                        reference_view_id=self.reference_view_id,
                        view_results=view_results,
                        frame_status=bundle.frame_status,
                        predictions=predictions,
                        view_geometry=self.view_geometry or {},
                        policy=self.guidance_generator.policy,
                        roster=roster_snapshot,
                        association_decisions=self.associator.last_tick_decisions,
                        guidance_decisions=self.guidance_generator.last_decisions,
                        same_tick_guidance_by_view=same_tick_guidance_by_view,
                        # fix-multiview-cam1-bootstrap-4player D4：reference 槽位冲突
                        # 计数（association 只读观测）→ roster_conflict 字段
                        roster_conflicts=(
                            getattr(self.registry, "reference_slot_conflicts", None) or {}
                        ),
                    )
                )
            except Exception as exc:  # noqa: BLE001 诊断构建失败不阻断核心 joint 分析
                self._display_diag_error = f"{type(exc).__name__}: {exc}"
                self.counter["player_display_diagnostics_failed"] = (
                    self.counter.get("player_display_diagnostics_failed", 0) + 1
                )

            for gid, (x, y, views) in fused.items():
                # D3:reanchor update 由 JointRun 唯一执行 reseed（决策与执行分离）
                reanchor_updates = [u for u in updates if u.global_id == gid and getattr(u, "reanchor", False)]
                if reanchor_updates:
                    self.registry.reseed(gid, x, y, timestamp_s, tick=tick_number)
                    self.counter["reanchor_succeeded"] = self.counter.get("reanchor_succeeded", 0) + 1
                else:
                    update_result = self.registry.absorb_measurement(gid, x, y, timestamp_s, tick=tick_number)
                    if not update_result.accepted:
                        # D2:innovation guard 拒绝 → 计数（associator.diagnostics 之外的 estimator 侧事件）
                        self.counter["measurement_innovation_rejected"] = (
                            self.counter.get("measurement_innovation_rejected", 0) + 1
                        )
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
                    identity_updates = [update for update in updates if update.global_id == gid]
                    recovered = any(
                        update.observation.detection_origin == "guided_roi"
                        for update in identity_updates
                    )
                    ambiguous = any(update.tentative for update in identity_updates)
                    identity_status = (
                        "ambiguous"
                        if ambiguous
                        else "confirmed_recovered" if recovered else "confirmed_observed"
                    )
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
                            metric_eligible=not ambiguous,
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
                            identity_status=identity_status,
                            identity_epoch=max(
                                (update.observation.local_identity_epoch for update in identity_updates),
                                default=0,
                            ),
                            binding_provenance={
                                update.view_id: {
                                    "view_player_id": update.observation.view_player_id,
                                    "source_track_id": update.observation.track_id,
                                    "local_identity_epoch": update.observation.local_identity_epoch,
                                    "detection_origin": update.observation.detection_origin,
                                    "tentative": update.tentative,
                                }
                                for update in identity_updates
                            },
                            quarantine_reason="tentative_association" if ambiguous else None,
                        )
                    )

            # D2:conflict_no_measurement → 标记 estimator 风险（供 D3 reanchor 决策查询）
            for fusion_decision in getattr(self.associator, "last_tick_fusion_decisions", []):
                if fusion_decision.get("reason") == "conflict_no_measurement":
                    gid = fusion_decision.get("global_player_id")
                    if gid is not None:
                        self.registry.mark_state_risk(gid, "conflict_no_measurement", tick=tick_number)

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
        samples = interpolate_short_confirmed_identity_gaps(samples)
        trajectory = write_fused_v2(
            run_id=self.run_id,
            capture_take_id=self.capture_take_id,
            reference_view_id=self.reference_view_id,
            samples=samples,
            authoritative_run=self.execution_mode == "joint_authoritative",
        )
        per_view_appearance: dict[str, dict[str, Any]] = {}
        per_view_roi_recovery: dict[str, dict[str, Any]] = {}
        for view_id, runtime in self.runtimes.items():
            session = getattr(runtime, "tracking_session", None)
            snapshot = getattr(session, "snapshot", None)
            if callable(snapshot):
                session_outputs = snapshot()
                per_view_appearance[view_id] = dict(
                    getattr(session_outputs, "appearance_summary", {}) or {}
                )
                per_view_roi_recovery[view_id] = dict(
                    getattr(session_outputs, "roi_recovery_summary", {}) or {}
                )
            else:
                per_view_appearance[view_id] = {}
                per_view_roi_recovery[view_id] = {}
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
            "roi_recovery": {"per_view": per_view_roi_recovery},
            "association_counters": dict(getattr(self.associator, "diagnostics", {})),
            "appearance": {
                "association": self.associator.appearance_diagnostics(),
                "per_view": per_view_appearance,
            },
            # fix-multiview-reacquire-after-fusion-pollution：joint 侧 estimator/reanchor 计数
            # （D2 innovation guard 拒绝、D3 reanchor 执行），与 association_counters 分层。
            "joint_counters": dict(self.counter),
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
        # ---- player display diagnostics 产物（构建失败不影响核心结果）----
        display_diagnostics_payload: dict[str, object] | None = None
        display_diagnostics_error = self._display_diag_error
        if not self._display_diag_error and not self._display_diag_rows:
            # 无确认球员/可用视角时仍产出空产物（status=unavailable），供前端区分
            pass
        try:
            from app.vision.multiview.player_display_diagnostics import (
                build_player_display_diagnostics_payload,
            )

            diag_status = "failed" if self._display_diag_error else ("available" if self._display_diag_rows else "unavailable")
            display_diagnostics_payload = build_player_display_diagnostics_payload(
                job_id=self.run_id,
                video_id=self.capture_take_id,
                reference_view_id=self.reference_view_id,
                rows=self._display_diag_rows,
                status=diag_status,
                detail=display_diagnostics_error or "",
            )
        except Exception as exc:  # noqa: BLE001 产物构建失败不阻断核心结果
            display_diagnostics_error = f"{type(exc).__name__}: {exc}"
            # fix-multiview-player-identity D1：构建/校验失败也回退最小占位产物，
            # 保证查询 API 永不因"产物文件不存在"而 404（status=failed + detail）
            display_diagnostics_payload = _fallback_display_diagnostics_payload(
                run_id=self.run_id,
                capture_take_id=self.capture_take_id,
                reference_view_id=self.reference_view_id,
                status="failed",
                detail=display_diagnostics_error,
            )
            self.counter["player_display_diagnostics_failed"] = (
                self.counter.get("player_display_diagnostics_failed", 0) + 1
            )
        ball_analysis = None
        if self.ball_processor is not None:
            ball_analysis = self.ball_processor.finish()
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
            display_diagnostics_payload=display_diagnostics_payload,
            display_diagnostics_error=display_diagnostics_error,
            ball_analysis=ball_analysis,
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
            "mapping_mode": sample.mapping_mode if sample is not None else None,
            "extrapolation_distance_ms": sample.extrapolation_distance_ms if sample is not None else None,
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
            # debug-only 候选层：live 但未满足 lock_only formal eligibility 的 track。
            # 仅 perception 实际执行（result 存在）的 view 写入；不含 player_id（无 formal 身份）。
            candidate_detections = []
            for detection in getattr(result, "candidate_detections", []) if result is not None else []:
                candidate_detections.append(
                    {
                        "bbox": list(detection.bbox),
                        "track_id": int(detection.track_id) if detection.track_id is not None else None,
                        "confidence": detection.confidence,
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
                "mapping_mode": sample.mapping_mode if sample is not None else None,
                "extrapolation_distance_ms": sample.extrapolation_distance_ms if sample is not None else None,
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
            # display-only tick（perception 未执行、result 缺失）不写 candidate_detections 字段
            if result is not None:
                views[view_id]["candidate_detections"] = candidate_detections
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
    def _runtime_prepare(runtime: Any, sample: Any, timestamp_s: float, pre_tick_guidance: tuple) -> Any | None:
        """阶段 1：解帧一次 + tracking_session.prepare_frame（不 update tracker）。

        兼容轻量 legacy runtime（无 prepare 方法）→ 回退旧 step 语义（内部一步完成）。
        返回 None 表示 decode 失败。
        """
        prepare = getattr(runtime, "prepare", None)
        if callable(prepare):
            try:
                return prepare(
                    sample.source_frame_index, timestamp_s,
                    pre_tick_guidance=pre_tick_guidance, timing_context=sample,
                )
            except TypeError:
                return prepare(sample.source_frame_index, timestamp_s, pre_tick_guidance=pre_tick_guidance)
        # legacy runtime：无 prepare → 直接用 step 并视为已 commit（无法两阶段）
        try:
            result = runtime.step(
                sample.source_frame_index, timestamp_s,
                guidance=pre_tick_guidance, timing_context=sample,
            )
        except TypeError:
            result = runtime.step(
                sample.source_frame_index, timestamp_s, guidance=pre_tick_guidance
            )
        if result is None:
            return None
        return _LegacyCommittedResult(result)

    @staticmethod
    def _runtime_complete(runtime: Any, prepared: Any, same_tick_guidance: tuple, sample: Any) -> Any | None:
        """阶段 2（commit）：tracker.update ONCE + 后续链路；转发 complete_frame。

        legacy 已 commit 结果直接返回。
        """
        if isinstance(prepared, _LegacyCommittedResult):
            return prepared.result
        complete = getattr(runtime, "complete", None)
        if callable(complete):
            try:
                return complete(
                    prepared, same_tick_guidance=same_tick_guidance, timing_context=sample
                )
            except TypeError:
                return complete(prepared, same_tick_guidance=same_tick_guidance)
        raise RuntimeError(f"runtime {runtime} has no complete() and prepared is not legacy")

    def _select_same_tick_guidance(
        self,
        *,
        prepared_by_view: dict[str, Any],
        predictions: dict[str, tuple[float, float, float]],
        take_ms: float,
        tick_number: int,
    ) -> dict[str, list[Any]]:
        """same-tick opportunity selection：donor 有 strong base candidate、target 无 usable candidate。

        产出 `view_id -> [CrossViewGuidance]`（same-tick ROI），复用 RecoveryAttemptLedger
        预算（pre-tick + same-tick ≤ max_regions_per_view_per_tick；同 pair 去重）。
        """
        from app.vision.multiview.pre_association import pre_associate

        out: dict[str, list[Any]] = {view_id: [] for view_id in prepared_by_view}
        if len(prepared_by_view) < 2:
            return out
        # 1) 构建 view_evidence（只消费 ROI-filtered base + 成功 pre-tick guided）
        view_evidence: dict[str, list[tuple[Any, str]]] = {}
        homography_by_view: dict[str, Any] = {}
        orientation_by_view: dict[str, Any] = {}
        source_frame_index_by_view: dict[str, int] = {}
        for view_id, prepared in prepared_by_view.items():
            if isinstance(prepared, _LegacyCommittedResult):
                continue
            evidence: list[tuple[Any, str]] = []
            for det in getattr(prepared, "roi_filtered_base", []) or []:
                evidence.append((det, "base"))
            for det in getattr(prepared, "pre_tick_guided", []) or []:
                evidence.append((det, "guided_roi"))
            view_evidence[view_id] = evidence
            geometry = self.view_geometry.get(view_id, {})
            homography_by_view[view_id] = geometry.get("inverse_homography")
            orientation_by_view[view_id] = geometry.get("orientation")
            source_frame_index_by_view[view_id] = getattr(prepared, "frame_index", 0)
        pa = pre_associate(
            view_evidence=view_evidence,
            homography_by_view=homography_by_view,
            orientation_by_view=orientation_by_view,
            source_frame_index_by_view=source_frame_index_by_view,
            global_predictions=predictions,
            pre_association_gate_ft=self.recovery_config.pre_association_gate_ft,
            ambiguity_margin=self.recovery_config.ambiguity_margin,
        )
        # 2) same-tick opportunity：donor 有 strong base candidate、target 无 usable candidate
        #    donor 严格 base origin（防 guided→guided 自我强化）
        donor_by_global: dict[str, tuple[str, Any]] = {}  # gid -> (view_id, candidate)
        for cand in pa.candidates:
            if cand.match_status == "strong" and cand.origin == "base" and cand.canonical_position_ft is not None:
                donor_by_global.setdefault(cand.matched_global_id, (cand.view_id, cand))
        if not donor_by_global:
            return out
        # target 已有 usable candidate 的 global（不补检）
        covered: dict[str, set[str]] = {view_id: set() for view_id in prepared_by_view}
        for cand in pa.candidates:
            if cand.match_status == "strong" and cand.canonical_position_ft is not None:
                covered.setdefault(cand.view_id, set()).add(cand.matched_global_id)
        # 3) 每 target view 生成 same-tick guidance（donor 当前 canonical evidence 投影）
        for target_view in prepared_by_view:
            if isinstance(prepared_by_view[target_view], _LegacyCommittedResult):
                continue
            geometry = self.view_geometry.get(target_view, {})
            orientation = geometry.get("orientation")
            inverse_homography = geometry.get("inverse_homography")
            if orientation is None or inverse_homography is None:
                continue
            for gid, (donor_view, donor_cand) in donor_by_global.items():
                if donor_view == target_view:
                    continue  # donor 必须是另一路
                if gid in covered.get(target_view, set()):
                    continue  # target 已有 usable candidate
                # 预算：同 pair 去重 + pre-tick+same-tick ≤ max_regions
                if (gid, target_view) in self._same_tick_attempted:
                    continue
                pre_count = len(self._same_tick_ledger[target_view])
                if pre_count >= self.recovery_config.max_regions_per_view_per_tick:
                    continue
                # donor 当前 canonical position → target image（绝不复制 pixel bbox）
                from app.vision.multiview.fused_overlay_projection import canonical_to_target_image
                from app.vision.multiview.guidance import CrossViewGuidance

                projection = canonical_to_target_image(
                    canonical_position=donor_cand.canonical_position_ft,
                    orientation=orientation,
                    inverse_homography=inverse_homography,
                    frame_width=int(geometry.get("frame_width") or 0),
                    frame_height=int(geometry.get("frame_height") or 0),
                )
                if not projection.projection_valid:
                    continue
                # ROI 尺寸复用共享 build_expected_player_region
                from app.vision.multiview.player_display_diagnostics import build_expected_player_region

                policy = self.guidance_generator.policy
                region = build_expected_player_region(
                    predicted_canonical_position=donor_cand.canonical_position_ft,
                    uncertainty_ft=None,
                    orientation=orientation,
                    inverse_homography=inverse_homography,
                    frame_width=int(geometry.get("frame_width") or 0),
                    frame_height=int(geometry.get("frame_height") or 0),
                    policy=policy,
                )
                if region.status != "available" or region.roi is None:
                    continue
                guidance = CrossViewGuidance(
                    global_player_id=gid,
                    target_view=target_view,
                    predicted_canonical_position=donor_cand.canonical_position_ft,
                    uncertainty_ft=0.0,
                    predicted_local_position=donor_cand.court_position_ft or donor_cand.canonical_position_ft,
                    expected_image_position=projection.image_footpoint,
                    roi=region.roi,
                    confidence=1.0,
                    expires_at=take_ms + 50.0,
                    guidance_id=f"st_{gid}_{target_view}_{tick_number}",
                    donor_view=donor_view,
                    donor_quality=donor_cand.intrinsic_quality,
                    donor_origin="base",
                    expected_global_player_id=gid,
                )
                out[target_view].append(guidance)
                self._same_tick_attempted.add((gid, target_view))
                self._same_tick_ledger[target_view].append(guidance)
                self.counter["same_tick_guidance_generated_count"] = (
                    self.counter.get("same_tick_guidance_generated_count", 0) + 1
                )
        return out

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
                    appearance_descriptor=getattr(result, "appearance_by_track", {}).get(track_id),
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


def _fallback_display_diagnostics_payload(
    *,
    run_id: str,
    capture_take_id: str | None,
    reference_view_id: str,
    status: str,
    detail: str,
) -> dict[str, object]:
    """fix-multiview-player-identity D1：最小占位 display diagnostics 产物。

    构建/校验失败时保证 `display_diagnostics_payload` 仍为 dict，composer 因此
    一定会写盘 artifact，查询 API 不会因"产物文件不存在"返回 404。
    """
    from app.vision.multiview.player_display_diagnostics import (
        PLAYER_DISPLAY_DIAGNOSTICS_SCHEMA,
    )

    return {
        "schema_version": PLAYER_DISPLAY_DIAGNOSTICS_SCHEMA,
        "job_id": run_id,
        "video_id": capture_take_id,
        "reference_view_id": reference_view_id,
        "status": status,
        "detail": detail,
        "rows": [],
    }
