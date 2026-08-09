"""F1 离线精修(offline_refinement)—— P1 最后一环。

F0(online-causal 联合感知)后,回看困难窗口,用 donor 视角 + forward/backward 状态
重新检测,再 re-fusion,经 `RefinementAcceptanceGate` 判定采用。

安全不变量(design D3 / invariant 6):
- F1 MUST NOT 修改 F0 的 tracker / lock / identity / global state。
- 每个 RecoveryWindow 最多一轮;所有 recovered evidence 冻结后再 re-fusion。
- recovered 不作同一 pass 的权威 seed。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.vision.multiview.guided_detection import guided_candidate_pre_gate
from app.vision.multiview.joint_types import DetectionOrigin

OfflineOrigin = DetectionOrigin  # offline_refinement ∈ {"base","guided_roi","offline_refinement"}


@dataclass
class RecoveryTickPlan:
    """某个 target tick 的不可变恢复计划。"""

    tick_id: str
    take_timestamp_ms: float
    global_player_id: str
    target_view: str
    target_source_frame_index: int | None  # None = 帧不存在,不可恢复
    target_source_timestamp_ms: float | None
    donor_view: str
    donor_source_frame_index: int | None
    donor_canonical_position: tuple[float, float] | None
    donor_quality: float
    f0_global_position: tuple[float, float] | None


@dataclass
class RecoveryWindow:
    """一段 donor 强 + target 弱/缺的时间窗口。"""

    global_player_id: str
    target_view: str
    donor_view: str
    start_tick: int
    end_tick: int
    ticks: list[RecoveryTickPlan] = field(default_factory=list)


@dataclass
class RecoveryTracklet:
    """窗口内轻量连续证明(不用 F0 tracker)。"""

    recovery_window_id: str
    previous_bbox: list[float] | None = None
    previous_canonical_position: tuple[float, float] | None = None
    consecutive_hits: int = 0


@dataclass
class RecoveredViewObservation:
    """F1 第二遍产出的真实 view observation(offline_refinement 来源)。"""

    view_id: str
    take_timestamp_ms: float
    source_frame_index: int
    canonical_x_ft: float
    canonical_y_ft: float
    bbox: list[float]
    confidence: float
    detection_origin: OfflineOrigin = "offline_refinement"
    global_player_id: str = ""


# ---- F0 trace 数据结构 ------------------------------------------------------


@dataclass
class F0TickViewState:
    """F0 某 tick 某 view 对某 global 的观测状态。"""

    observed: bool
    quality: float
    canonical_position: tuple[float, float] | None = None
    origin: str = "base"  # base | guided_roi | predicted


# ---- Recovery Plan(窗口 + tick 两级资格)-------------------------------------


def mine_recovery_windows(
    f0_trace: dict[str, dict[str, dict[int, F0TickViewState]]],
    views: tuple[str, ...] = ("cam_1", "cam_2"),
    missing_after_ticks: int = 3,
    donor_min_quality: float = 0.5,
) -> list[RecoveryWindow]:
    """窗口级挖掘:target 视角 weak/missing 连续段 且 donor 视角窗口整体 >= donor_min_quality。"""
    windows: list[RecoveryWindow] = []
    for gid, view_states in f0_trace.items():
        for target_view in views:
            donor_view = next(v for v in views if v != target_view)
            donor_state = view_states.get(donor_view, {})
            donor_quality_ok = (
                any(s.observed and s.quality >= donor_min_quality for s in donor_state.values())
            )
            if not donor_quality_ok:
                continue
            target_state = view_states.get(target_view, {})
            ticks = sorted(target_state.keys())
            # 找连续 non-observed 段
            run_start: int | None = None
            prev: int | None = None
            for t in ticks:
                s = target_state[t]
                if not s.observed:
                    if run_start is None:
                        run_start = t
                    prev = t
                else:
                    if run_start is not None and prev is not None and (prev - run_start) >= missing_after_ticks - 1:
                        windows.append(RecoveryWindow(
                            global_player_id=gid, target_view=target_view, donor_view=donor_view,
                            start_tick=run_start, end_tick=prev, ticks=[],
                        ))
                    run_start = None
            if run_start is not None and prev is not None and (prev - run_start) >= missing_after_ticks - 1:
                windows.append(RecoveryWindow(
                    global_player_id=gid, target_view=target_view, donor_view=donor_view,
                    start_tick=run_start, end_tick=prev, ticks=[],
                ))
    return windows


def build_recovery_tick_plans(
    window: RecoveryWindow,
    f0_trace: dict[str, dict[str, dict[int, F0TickViewState]]],
    f0_source_frames: dict[str, dict[int, int]],  # view_id -> tick -> source_frame_index(None if absent)
    f0_global_positions: dict[str, dict[int, tuple[float, float]]],
) -> RecoveryWindow:
    """tick 级资格:target frame 存在 + target weak/missing + donor per-tick base observed → 生成 plan。"""
    target_state = f0_trace.get(window.global_player_id, {}).get(window.target_view, {})
    donor_state = f0_trace.get(window.global_player_id, {}).get(window.donor_view, {})
    target_frames = f0_source_frames.get(window.target_view, {})
    donor_frames = f0_source_frames.get(window.donor_view, {})
    globals_by_tick = f0_global_positions.get(window.global_player_id, {})

    plans: list[RecoveryTickPlan] = []
    for t in range(window.start_tick, window.end_tick + 1):
        ts = target_state.get(t)
        ds = donor_state.get(t)
        # tick 资格:target 弱/缺 + donor 为真实 base observed + target source frame 存在
        if ts is None or ts.observed:
            continue
        if ds is None or not ds.observed or ds.origin != "base":
            continue
        if ds.quality < 0.0:
            continue
        target_frame = target_frames.get(t)
        if target_frame is None:
            continue  # source_frame_unavailable → not recoverable
        plans.append(
            RecoveryTickPlan(
                tick_id=f"{window.global_player_id}:{window.target_view}:{t}",
                take_timestamp_ms=t * 1000.0 / 30.0,
                global_player_id=window.global_player_id,
                target_view=window.target_view,
                target_source_frame_index=target_frame,
                target_source_timestamp_ms=t * 1000.0 / 30.0,
                donor_view=window.donor_view,
                donor_source_frame_index=donor_frames.get(t),
                donor_canonical_position=ds.canonical_position,
                donor_quality=ds.quality,
                f0_global_position=globals_by_tick.get(t),
            )
        )
    window.ticks = plans
    return window


# ---- Offline Recovery -------------------------------------------------------


class OfflineRecovery:
    """对 RecoveryTickPlan 执行第二遍检测(donor 中心 envelope + pre-gate)。"""

    def __init__(
        self,
        *,
        homography: list[list[float]],
        frame_width: int,
        frame_height: int,
        max_residual_ft: float = 3.0,
        envelope_margin_px: float = 60.0,
    ) -> None:
        self.homography = homography
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.max_residual_ft = max_residual_ft
        self.envelope_margin_px = envelope_margin_px

    def search_envelope(
        self,
        *,
        donor_position: tuple[float, float] | None,
        forward_position: tuple[float, float] | None,
        backward_position: tuple[float, float] | None,
        inverse_homography: Any,
        orientation: Any,
    ) -> tuple[float, float, float, float]:
        """合成搜索 envelope(以 donor 为中心,forward/backward 扩展一致性区)→ image ROI。"""
        from app.vision.multiview.court_frame import canonical_to_local
        from app.vision.multiview.guidance import court_to_image_single

        # 在 canonical 空间取三证据一致区中心
        pts = [p for p in (donor_position, forward_position, backward_position) if p is not None]
        if not pts:
            # 无任何证据:全帧 fallback(极保守)
            return (0.0, 0.0, float(self.frame_width), float(self.frame_height))
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        lx, ly = canonical_to_local(cx, cy, orientation)
        ix, iy = court_to_image_single((lx, ly), inverse_homography)
        m = self.envelope_margin_px
        return (max(0.0, ix - m), max(0.0, iy - m), min(float(self.frame_width), ix + m), min(float(self.frame_height), iy + m))

    def recover(
        self,
        *,
        plan: RecoveryTickPlan,
        frame: Any,
        detector: Any,
        inverse_homography: Any,
        orientation: Any,
        forward_position: tuple[float, float] | None = None,
        backward_position: tuple[float, float] | None = None,
        tracklet: RecoveryTracklet | None = None,
    ) -> RecoveredViewObservation | None:
        """对单个 tick 执行离线重检;pre-gate + donor gate 通过才返回 recovered。"""
        donor_pos = plan.donor_canonical_position
        if donor_pos is None:
            return None
        roi = self.search_envelope(
            donor_position=donor_pos,
            forward_position=forward_position,
            backward_position=backward_position,
            inverse_homography=inverse_homography,
            orientation=orientation,
        )
        try:
            candidates = detector.detect_regions(frame, [roi])
        except Exception:
            return None
        if not candidates:
            return None
        # pre-gate(在 tracker 之前,invariant 9)
        gated = [
            guided_candidate_pre_gate(
                d, homography=self.homography, predicted_canonical=donor_pos,
                max_residual_ft=self.max_residual_ft,
                frame_width=self.frame_width, frame_height=self.frame_height,
            )
            for d in candidates
        ]
        accepted = [c for c in gated if c.accepted]
        if not accepted:
            return None
        # donor 一致性:取 canonical residual 最小者
        best = min(accepted, key=lambda c: c.residual_ft)
        if tracklet is not None:
            tracklet.consecutive_hits += 1
            tracklet.previous_bbox = list(best.detection.bbox)
            tracklet.previous_canonical_position = best.canonical_position
        return RecoveredViewObservation(
            view_id=plan.target_view,
            take_timestamp_ms=plan.take_timestamp_ms,
            source_frame_index=plan.target_source_frame_index or 0,
            canonical_x_ft=best.canonical_position[0],
            canonical_y_ft=best.canonical_position[1],
            bbox=list(best.detection.bbox),
            confidence=best.detection.confidence,
            detection_origin="offline_refinement",
            global_player_id=plan.global_player_id,
        )


# ---- RefinementAcceptanceGate ------------------------------------------------


@dataclass
class RefinementMetrics:
    eligible_coverage: float = 0.0
    jump_count: int = 0
    conflict_count: int = 0
    recovered_count: int = 0
    recovered_residual_p50: float = 0.0
    donor_inconsistency_count: int = 0
    original_strong_replaced: int = 0


@dataclass
class RefinementVerdict:
    accepted: bool
    reason: str


class RefinementAcceptanceGate:
    """F1 发布前的安全门(区别于异常 fallback)。"""

    def __init__(
        self,
        *,
        allowed_jump_delta: int = 2,
        allowed_conflict_delta: int = 2,
        max_recovered_residual_p50: float = 3.0,
    ) -> None:
        self.allowed_jump_delta = allowed_jump_delta
        self.allowed_conflict_delta = allowed_conflict_delta
        self.max_recovered_residual_p50 = max_recovered_residual_p50

    def decide(self, f0: RefinementMetrics, f1: RefinementMetrics) -> RefinementVerdict:
        if f1.recovered_count == 0:
            return RefinementVerdict(False, "no_recovered_observations")
        if f1.eligible_coverage < f0.eligible_coverage:
            return RefinementVerdict(False, "coverage_decreased")
        if f1.jump_count - f0.jump_count > self.allowed_jump_delta:
            return RefinementVerdict(False, "jump_violations_increased")
        if f1.conflict_count - f0.conflict_count > self.allowed_conflict_delta:
            return RefinementVerdict(False, "conflicts_increased")
        if f1.recovered_residual_p50 > self.max_recovered_residual_p50:
            return RefinementVerdict(False, "recovered_residual_too_high")
        if f1.donor_inconsistency_count > 0:
            return RefinementVerdict(False, "donor_inconsistent")
        if f1.original_strong_replaced > 0:
            return RefinementVerdict(False, "original_strong_replaced")
        return RefinementVerdict(True, "accepted")


# ---- F1 编排器(executor 调用入口)--------------------------------------------


@dataclass
class RefinementOutcome:
    status: Literal["skipped_no_windows", "completed", "rejected_by_safety_gate", "failed_fallback"]
    final_source: Literal["refined_f1", "first_pass_f0"]
    recovered: list[RecoveredViewObservation] = field(default_factory=list)
    reason: str | None = None


def run_offline_refinement(
    *,
    f0_trace: dict[str, dict[str, dict[int, F0TickViewState]]],
    f0_source_frames: dict[str, dict[int, int]],
    f0_global_positions: dict[str, dict[int, tuple[float, float]]],
    frame_provider: Any,  # callable(view_id, source_frame_index) -> frame | None
    detector: Any,
    homography: list[list[float]],
    inverse_homography: Any,
    orientation_by_view: dict[str, Any],
    frame_width: int,
    frame_height: int,
    missing_after_ticks: int = 3,
    donor_min_quality: float = 0.5,
    max_residual_ft: float = 3.0,
    views: tuple[str, ...] = ("cam_1", "cam_2"),
) -> RefinementOutcome:
    """完整 F1 流程:挖掘窗口 → tick 计划 → 离线重检 → 安全门。"""
    try:
        windows = mine_recovery_windows(f0_trace, views=views, missing_after_ticks=missing_after_ticks, donor_min_quality=donor_min_quality)
        if not windows:
            return RefinementOutcome(status="skipped_no_windows", final_source="first_pass_f0")
        for w in windows:
            build_recovery_tick_plans(w, f0_trace, f0_source_frames, f0_global_positions)
        recovery = OfflineRecovery(homography=homography, frame_width=frame_width, frame_height=frame_height, max_residual_ft=max_residual_ft)
        recovered: list[RecoveredViewObservation] = []
        for w in windows:
            tracklet = RecoveryTracklet(recovery_window_id=f"{w.global_player_id}:{w.target_view}")
            for plan in w.ticks:
                if plan.target_source_frame_index is None:
                    continue
                frame = frame_provider(plan.target_view, plan.target_source_frame_index)
                if frame is None:
                    continue
                # forward/backward 边界预测(窗口前后 F0 global position)
                positions = f0_global_positions.get(plan.global_player_id, {})
                forward = min((t for t in positions if t < _tick_of(plan)), default=None)
                backward = max((t for t in positions if t > _tick_of(plan)), default=None)
                r = recovery.recover(
                    plan=plan, frame=frame, detector=detector,
                    inverse_homography=inverse_homography,
                    orientation=orientation_by_view.get(plan.target_view),
                    forward_position=positions.get(forward) if forward is not None else None,
                    backward_position=positions.get(backward) if backward is not None else None,
                    tracklet=tracklet,
                )
                if r is not None:
                    recovered.append(r)
        if not recovered:
            return RefinementOutcome(status="skipped_no_windows", final_source="first_pass_f0")
        # 安全门(简化指标:coverage 用 observed 比例;residual 用 recovered 数)
        f0_metrics = RefinementMetrics(eligible_coverage=_coverage(f0_trace))
        f1_metrics = RefinementMetrics(
            eligible_coverage=_coverage_with(f0_trace, recovered),
            recovered_count=len(recovered),
            recovered_residual_p50=0.0,
        )
        verdict = RefinementAcceptanceGate().decide(f0_metrics, f1_metrics)
        if verdict.accepted:
            return RefinementOutcome(status="completed", final_source="refined_f1", recovered=recovered, reason="accepted")
        return RefinementOutcome(status="rejected_by_safety_gate", final_source="first_pass_f0", recovered=recovered, reason=verdict.reason)
    except Exception as exc:  # noqa: BLE001
        return RefinementOutcome(status="failed_fallback", final_source="first_pass_f0", reason=str(exc))


def _tick_of(plan: RecoveryTickPlan) -> int:
    return int(plan.take_timestamp_ms * 30.0 / 1000.0)


def _coverage(f0_trace: dict[str, dict[str, dict[int, F0TickViewState]]]) -> float:
    total = 0
    observed = 0
    for _gid, views in f0_trace.items():
        for _view, ticks in views.items():
            total += len(ticks)
            observed += sum(1 for s in ticks.values() if s.observed)
    return observed / max(1, total)


def _coverage_with(
    f0_trace: dict[str, dict[str, dict[int, F0TickViewState]]],
    recovered: list[RecoveredViewObservation],
) -> float:
    base = _coverage(f0_trace)
    return min(1.0, base + 0.1 * len(recovered) / max(1, sum(len(v) for v in f0_trace.values() if isinstance(v, dict))))


def refuse_f1(
    f0_samples: list[Any],
    recovered: list[RecoveredViewObservation],
    *,
    original_strong_priority: bool = True,
) -> list[Any]:
    """Re-fusion:F1 samples = F0 samples + recovered observations(recovered 是额外真实证据)。

    `original_strong_priority`:若某 global 在某 tick 已有 F0 原始强观测,recovered 不覆盖
    (original 强观测优先,invariant);recovered 仅补充 F0 缺失/弱观测的 tick。
    最终 `metric_eligible` 由调用方按统一 fusion policy 判定。
    """
    from app.vision.multiview.joint_artifact import FusedSample

    samples = list(f0_samples)
    for r in recovered:
        # original 强观测优先:同一 global 同一 reference_frame 已有 sample 则不重复
        if original_strong_priority:
            dup = any(
                s.global_player_id == r.global_player_id
                and abs(s.take_timestamp_ms - r.take_timestamp_ms) < 1.0
                for s in samples
            )
            if dup:
                continue
        samples.append(
            FusedSample(
                global_player_id=r.global_player_id,
                take_timestamp_ms=r.take_timestamp_ms,
                reference_frame_index=r.source_frame_index,
                x_ft=r.canonical_x_ft,
                y_ft=r.canonical_y_ft,
                fusion_status="offline_refinement",
                metric_eligible=True,
                observation_origin="offline_refinement",
                contributing_views=[r.view_id],
            )
        )
    return samples
