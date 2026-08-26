"""比赛语义驱动的球搜索策略。

这一层只负责把时间线和视觉上下文转换为可审计的语义快照与球搜索决策，
不直接实现球 detector、BallTracker 或回合/比分裁决。默认 Shadow Mode
下，策略可以提出抑制建议，但不会改变现有正式球链路。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping, Sequence


SEMANTIC_TIMELINE_SCHEMA_VERSION = "ball_semantic_timeline.v1"
SEMANTIC_BOUNDARY_POLICY_VERSION = "semantic_boundary_policy.v1"


class SemanticPhase(StrEnum):
    UNKNOWN = "UNKNOWN"
    NON_PLAY_CONFIRMED = "NON_PLAY_CONFIRMED"
    PRE_SERVE = "PRE_SERVE"
    SERVE_ARMED = "SERVE_ARMED"
    RALLY_ACTIVE = "RALLY_ACTIVE"
    RALLY_END_CANDIDATE = "RALLY_END_CANDIDATE"
    POST_RALLY = "POST_RALLY"


class SemanticAuthority(StrEnum):
    NONE = "none"
    ALGORITHM = "algorithm"
    MANUAL = "manual"
    CORRECTED = "corrected"


class SemanticPolicyMode(StrEnum):
    SHADOW = "shadow"
    ENFORCED = "enforced"


class BallPolicyAction(StrEnum):
    FALLBACK = "fallback"
    ALLOW = "allow"
    SOFT_GATE = "soft_gate"
    SUPPRESS_FORMAL = "suppress_formal"
    SERVE_REACQUIRE = "serve_reacquire"


class BallBoundaryAction(StrEnum):
    """语义 phase 边沿对正式球链产生的一次性生命周期动作。"""

    NONE = "none"
    SEAL_FORMAL_SEGMENT = "seal_formal_segment"
    RESET_TRACKER_FOR_NEXT_RALLY = "reset_tracker_for_next_rally"
    WARM_REACQUIRE = "warm_reacquire"
    SERVE_REACQUIRE = "serve_reacquire"
    OPEN_FORMAL_SEGMENT = "open_formal_segment"


class FormalSegmentLifecycle(StrEnum):
    """正式球段与发球预热层的生命周期。"""

    NONE = "none"
    WARM = "warm"
    OPEN = "open"
    SEALED = "sealed"


def _jsonable(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


@dataclass(frozen=True)
class MatchSemanticSnapshot:
    """某个 canonical take 时间上的比赛语义快照。"""

    take_timestamp_ms: float
    phase: SemanticPhase = SemanticPhase.UNKNOWN
    phase_confidence: float = 0.0
    authority: SemanticAuthority = SemanticAuthority.NONE
    evidence: dict[str, Any] = field(default_factory=dict)
    policy_mode: SemanticPolicyMode = SemanticPolicyMode.SHADOW
    policy_decision: BallPolicyAction = BallPolicyAction.FALLBACK
    decision_reason: str = "semantic_context_unavailable"
    semantic_fallback: bool = True
    timeline_event_ids: tuple[str, ...] = ()
    previous_phase: SemanticPhase = SemanticPhase.UNKNOWN
    phase_changed: bool = False
    boundary_action: BallBoundaryAction = BallBoundaryAction.NONE
    boundary_action_id: str | None = None
    formal_segment_lifecycle: FormalSegmentLifecycle = FormalSegmentLifecycle.NONE
    evidence_ids: tuple[str, ...] = ()
    boundary_status: str = "none"
    pending_boundary: str | None = None
    adjudication_reason: str | None = None
    contradiction_evidence_ids: tuple[str, ...] = ()
    rescue_reason: str | None = None

    @classmethod
    def unknown(
        cls,
        timestamp_ms: float,
        *,
        mode: SemanticPolicyMode = SemanticPolicyMode.SHADOW,
        evidence: Mapping[str, Any] | None = None,
        reason: str = "semantic_context_unavailable",
    ) -> "MatchSemanticSnapshot":
        return cls(
            take_timestamp_ms=float(timestamp_ms),
            phase=SemanticPhase.UNKNOWN,
            phase_confidence=0.0,
            authority=SemanticAuthority.NONE,
            evidence=dict(evidence or {}),
            policy_mode=mode,
            policy_decision=BallPolicyAction.FALLBACK,
            decision_reason=reason,
            semantic_fallback=True,
        )

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(
            {
                "schema_version": SEMANTIC_TIMELINE_SCHEMA_VERSION,
                "take_timestamp_ms": self.take_timestamp_ms,
                "phase": self.phase,
                "phase_confidence": self.phase_confidence,
                "authority": self.authority,
                "evidence": self.evidence,
                "policy_mode": self.policy_mode,
                "policy_decision": self.policy_decision,
                "decision_reason": self.decision_reason,
                "semantic_fallback": self.semantic_fallback,
                "timeline_event_ids": list(self.timeline_event_ids),
                "previous_phase": self.previous_phase,
                "phase_changed": self.phase_changed,
                "boundary_action": self.boundary_action,
                "boundary_action_id": self.boundary_action_id,
                "formal_segment_lifecycle": self.formal_segment_lifecycle,
                "evidence_ids": list(self.evidence_ids),
                "boundary_status": self.boundary_status,
                "pending_boundary": self.pending_boundary,
                "adjudication_reason": self.adjudication_reason,
                "contradiction_evidence_ids": list(self.contradiction_evidence_ids),
                "rescue_reason": self.rescue_reason,
            }
        )


@dataclass(frozen=True)
class BallSearchDecision:
    """语义策略对球链各层级的决策。"""

    phase: SemanticPhase
    authority: SemanticAuthority
    policy_mode: SemanticPolicyMode
    action: BallPolicyAction
    search_scope: str
    recommended_tracker_update: bool
    recommended_formal_publish: bool
    tracker_update_allowed: bool
    formal_publish_allowed: bool
    accept_stationary_candidate: bool
    semantic_fallback: bool
    reason: str
    diagnostics: dict[str, Any] = field(default_factory=dict)
    rollout_enabled: bool = False
    hard_gate_active: bool = False
    boundary_action: BallBoundaryAction = BallBoundaryAction.NONE
    boundary_action_id: str | None = None
    formal_segment_lifecycle: FormalSegmentLifecycle = FormalSegmentLifecycle.NONE
    formal_candidate_count_before: int = 0
    formal_candidate_count_after: int = 0
    boundary_status: str = "none"
    pending_boundary: str | None = None
    rescued_active: bool = False
    grace_window_sec: float = 0.0
    evidence_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self.__dict__)


@dataclass(frozen=True)
class BallSemanticPolicyConfig:
    """策略配置；默认 Shadow + fail-open。"""

    mode: SemanticPolicyMode = SemanticPolicyMode.SHADOW
    enforce_authoritative_non_play: bool = False
    # take/job 可以显式打开该开关；旧的 enforce_authoritative_non_play 仍作为
    # 向后兼容的显式 rollout 入口，避免已有调用方行为改变。
    enforced_rollout_enabled: bool = False
    rollout_id: str = "default"
    allowed_hard_authorities: tuple[str, ...] = (
        SemanticAuthority.MANUAL.value,
        SemanticAuthority.CORRECTED.value,
    )
    serve_prepare_confidence: float = 0.55
    serve_armed_confidence: float = 0.70
    rally_end_min_evidence: int = 2
    semantic_timeline_enabled: bool = True
    policy_version: str = SEMANTIC_BOUNDARY_POLICY_VERSION
    min_confirm_ticks: int = 2
    grace_window_sec: float = 0.20
    rescue_min_consecutive_ticks: int = 2
    rescue_min_motion_pixels: float = 15.0
    evidence_freshness_sec: float = 0.50
    conflict_penalty: float = 0.25
    boundary_eval_enabled: bool = True

    def snapshot(self) -> dict[str, Any]:
        rollout_enabled = bool(self.enforced_rollout_enabled or self.enforce_authoritative_non_play)
        return {
            "schema_version": SEMANTIC_TIMELINE_SCHEMA_VERSION,
            "policy_version": self.policy_version,
            "mode": self.mode.value,
            "enforce_authoritative_non_play": self.enforce_authoritative_non_play,
            "enforced_rollout_enabled": self.enforced_rollout_enabled,
            "rollout_enabled": rollout_enabled,
            "rollout_id": self.rollout_id,
            "allowed_hard_authorities": list(self.allowed_hard_authorities),
            "serve_prepare_confidence": self.serve_prepare_confidence,
            "serve_armed_confidence": self.serve_armed_confidence,
            "rally_end_min_evidence": self.rally_end_min_evidence,
            "semantic_timeline_enabled": self.semantic_timeline_enabled,
            "min_confirm_ticks": max(1, int(self.min_confirm_ticks)),
            "grace_window_sec": max(0.0, float(self.grace_window_sec)),
            "rescue_min_consecutive_ticks": max(1, int(self.rescue_min_consecutive_ticks)),
            "rescue_min_motion_pixels": max(0.0, float(self.rescue_min_motion_pixels)),
            "evidence_freshness_sec": max(0.0, float(self.evidence_freshness_sec)),
            "conflict_penalty": max(0.0, min(1.0, float(self.conflict_penalty))),
            "boundary_eval_enabled": bool(self.boundary_eval_enabled),
            "time_unit": "milliseconds_for_take_and_timeline; seconds_for_evidence_windows",
            "fail_open": True,
        }


class BallSearchPolicy:
    """根据语义快照生成球链策略，不直接修改 tracker 状态。"""

    def __init__(self, config: BallSemanticPolicyConfig | None = None) -> None:
        self.config = config or BallSemanticPolicyConfig()

    def evaluate(
        self,
        snapshot: MatchSemanticSnapshot,
        *,
        raw_candidate_count: int = 0,
    ) -> BallSearchDecision:
        phase = snapshot.phase
        rollout_enabled = bool(self.config.enforced_rollout_enabled or self.config.enforce_authoritative_non_play)
        authority_allowed = snapshot.authority.value in set(self.config.allowed_hard_authorities)
        hard_non_play = (
            self.config.mode == SemanticPolicyMode.ENFORCED
            and rollout_enabled
            and authority_allowed
            and phase in {SemanticPhase.NON_PLAY_CONFIRMED, SemanticPhase.POST_RALLY}
        )

        if phase == SemanticPhase.UNKNOWN:
            return self._decision(
                snapshot,
                action=BallPolicyAction.FALLBACK,
                scope="legacy",
                recommended_tracker_update=True,
                recommended_formal_publish=True,
                tracker_update_allowed=True,
                formal_publish_allowed=True,
                accept_stationary_candidate=True,
                reason="semantic_unknown_fallback",
                raw_candidate_count=raw_candidate_count,
                hard_gate_active=False,
            )

        if hard_non_play:
            return self._decision(
                snapshot,
                action=BallPolicyAction.SUPPRESS_FORMAL,
                scope="sentinel_only",
                recommended_tracker_update=False,
                recommended_formal_publish=False,
                tracker_update_allowed=False,
                formal_publish_allowed=False,
                accept_stationary_candidate=False,
                reason="authoritative_non_play_hard_gate",
                raw_candidate_count=raw_candidate_count,
                hard_gate_active=True,
            )

        if phase == SemanticPhase.NON_PLAY_CONFIRMED or phase == SemanticPhase.POST_RALLY:
            return self._decision(
                snapshot,
                action=BallPolicyAction.SOFT_GATE,
                scope="sentinel_only",
                recommended_tracker_update=False,
                recommended_formal_publish=False,
                tracker_update_allowed=True,
                formal_publish_allowed=True,
                accept_stationary_candidate=False,
                reason="non_play_soft_gate_shadow_or_unenforced",
                raw_candidate_count=raw_candidate_count,
                hard_gate_active=False,
            )

        if phase == SemanticPhase.PRE_SERVE:
            warm_formal_gate = bool(
                self.config.mode == SemanticPolicyMode.ENFORCED
                and rollout_enabled
                and authority_allowed
            )
            return self._decision(
                snapshot,
                action=BallPolicyAction.SERVE_REACQUIRE,
                scope="serve_region",
                recommended_tracker_update=True,
                recommended_formal_publish=not warm_formal_gate,
                tracker_update_allowed=True,
                formal_publish_allowed=not warm_formal_gate,
                accept_stationary_candidate=False,
                reason="pre_serve_ignore_stationary_handheld_candidate",
                raw_candidate_count=raw_candidate_count,
                hard_gate_active=False,
            )

        if phase == SemanticPhase.SERVE_ARMED:
            warm_formal_gate = bool(
                self.config.mode == SemanticPolicyMode.ENFORCED
                and rollout_enabled
                and authority_allowed
            )
            return self._decision(
                snapshot,
                action=BallPolicyAction.SERVE_REACQUIRE,
                scope="serve_region_progressive",
                recommended_tracker_update=True,
                recommended_formal_publish=not warm_formal_gate,
                tracker_update_allowed=True,
                formal_publish_allowed=not warm_formal_gate,
                accept_stationary_candidate=False,
                reason="serve_armed_progressive_reacquisition",
                raw_candidate_count=raw_candidate_count,
                hard_gate_active=False,
            )

        return self._decision(
            snapshot,
            action=BallPolicyAction.ALLOW,
            scope="full_court",
            recommended_tracker_update=True,
            recommended_formal_publish=True,
            tracker_update_allowed=True,
            formal_publish_allowed=True,
            accept_stationary_candidate=True,
            reason="active_play_ball_search",
            raw_candidate_count=raw_candidate_count,
            hard_gate_active=False,
        )

    def _decision(
        self,
        snapshot: MatchSemanticSnapshot,
        *,
        action: BallPolicyAction,
        scope: str,
        recommended_tracker_update: bool,
        recommended_formal_publish: bool,
        tracker_update_allowed: bool,
        formal_publish_allowed: bool,
        accept_stationary_candidate: bool,
        reason: str,
        raw_candidate_count: int,
        hard_gate_active: bool = False,
    ) -> BallSearchDecision:
        # Shadow Mode deliberately leaves effective behavior unchanged.
        if self.config.mode == SemanticPolicyMode.SHADOW:
            tracker_update_allowed = True
            formal_publish_allowed = True
        return BallSearchDecision(
            phase=snapshot.phase,
            authority=snapshot.authority,
            policy_mode=self.config.mode,
            action=action,
            search_scope=scope,
            recommended_tracker_update=recommended_tracker_update,
            recommended_formal_publish=recommended_formal_publish,
            tracker_update_allowed=tracker_update_allowed,
            formal_publish_allowed=formal_publish_allowed,
            accept_stationary_candidate=accept_stationary_candidate,
            semantic_fallback=snapshot.semantic_fallback,
            reason=reason,
            diagnostics={
                "raw_candidate_count": int(raw_candidate_count),
                "shadow_effective_behavior": self.config.mode == SemanticPolicyMode.SHADOW,
                "rollout_id": self.config.rollout_id,
                "authority_allowed": snapshot.authority.value in set(self.config.allowed_hard_authorities),
                "policy_version": self.config.policy_version,
                "evidence_ids": list(snapshot.evidence_ids),
                "boundary_status": snapshot.boundary_status,
                "pending_boundary": snapshot.pending_boundary,
                "adjudication_reason": snapshot.adjudication_reason,
                "contradiction_evidence_ids": list(snapshot.contradiction_evidence_ids),
                "rescue_reason": snapshot.rescue_reason,
                "grace_window_sec": self.config.grace_window_sec,
            },
            rollout_enabled=bool(self.config.enforced_rollout_enabled or self.config.enforce_authoritative_non_play),
            hard_gate_active=hard_gate_active,
            boundary_action=snapshot.boundary_action,
            boundary_action_id=snapshot.boundary_action_id,
            formal_segment_lifecycle=snapshot.formal_segment_lifecycle,
            formal_candidate_count_before=max(0, int(raw_candidate_count)),
            formal_candidate_count_after=(0 if not formal_publish_allowed else max(0, int(raw_candidate_count))),
            boundary_status=snapshot.boundary_status,
            pending_boundary=snapshot.pending_boundary,
            rescued_active=snapshot.boundary_status == "rescued_active",
            grace_window_sec=max(0.0, float(self.config.grace_window_sec)),
            evidence_ids=snapshot.evidence_ids,
        )


class SemanticStateMachine:
    """保守的视觉状态转换器；权威时间线由 provider 优先覆盖。"""

    def __init__(self, config: BallSemanticPolicyConfig | None = None) -> None:
        self.config = config or BallSemanticPolicyConfig()
        self.phase = SemanticPhase.UNKNOWN
        self._last_timestamp_ms: float | None = None
        self._pending_boundary: str | None = None
        self._pending_since_ms: float | None = None
        self._pending_ticks: int = 0
        self._rescue_ticks: int = 0
        self._pending_evidence_ids: tuple[str, ...] = ()
        self._last_adjudication_status: str = "none"

    def reset(self) -> None:
        self.phase = SemanticPhase.UNKNOWN
        self._last_timestamp_ms = None
        self._pending_boundary = None
        self._pending_since_ms = None
        self._pending_ticks = 0
        self._rescue_ticks = 0
        self._pending_evidence_ids = ()
        self._last_adjudication_status = "none"

    def update(
        self,
        timestamp_ms: float,
        *,
        evidence: Mapping[str, Any] | None = None,
        authority: SemanticAuthority = SemanticAuthority.NONE,
        timeline_event_ids: Sequence[str] = (),
    ) -> MatchSemanticSnapshot:
        evidence_map = dict(evidence or {})
        previous_phase = self.phase
        phase = self.phase
        confidence = float(evidence_map.get("phase_confidence", 0.0) or 0.0)

        serve_confidence = float(evidence_map.get("serve_candidate_confidence", 0.0) or 0.0)
        serve_armed = bool(evidence_map.get("serve_armed", False))
        rally_active = bool(evidence_map.get("rally_active", False))
        end_evidence_count = int(evidence_map.get("rally_end_evidence_count", 0) or 0)
        explicit_non_play = bool(evidence_map.get("non_play_confirmed", False))

        timeline_event_type = str(evidence_map.get("timeline_event_type", ""))
        rally_end_confirmed = bool(evidence_map.get("rally_end_confirmed", False))
        evidence_ids = tuple(str(item) for item in evidence_map.get("evidence_ids", ()) if str(item))
        current_timestamp_ms = float(timestamp_ms)
        authoritative_boundary = authority in {SemanticAuthority.MANUAL, SemanticAuthority.CORRECTED} and (
            explicit_non_play
            or timeline_event_type in {"rally_end", "non_play"}
            or rally_end_confirmed
        )
        active_play_evidence = not bool(evidence_map.get("all_boundary_evidence_stale", False)) and self._has_active_play_evidence(
            evidence_map
        )
        end_signal = self._has_end_signal(evidence_map, end_evidence_count)
        boundary_status = "none"
        pending_boundary: str | None = None
        adjudication_reason: str | None = None
        contradiction_ids: tuple[str, ...] = ()
        rescue_reason: str | None = None

        if authority in {SemanticAuthority.MANUAL, SemanticAuthority.CORRECTED} and explicit_non_play:
            phase = SemanticPhase.NON_PLAY_CONFIRMED
            confidence = max(confidence, 1.0)
        elif timeline_event_type == "rally_end" or rally_end_confirmed:
            phase = SemanticPhase.POST_RALLY
            confidence = max(confidence, 1.0 if rally_end_confirmed else confidence)
        elif phase in {
            SemanticPhase.UNKNOWN,
            SemanticPhase.NON_PLAY_CONFIRMED,
            SemanticPhase.POST_RALLY,
        } and (serve_armed or serve_confidence >= self.config.serve_armed_confidence):
            phase = SemanticPhase.SERVE_ARMED
            confidence = max(confidence, serve_confidence, self.config.serve_armed_confidence if serve_armed else 0.0)
        elif phase in {
            SemanticPhase.UNKNOWN,
            SemanticPhase.NON_PLAY_CONFIRMED,
            SemanticPhase.POST_RALLY,
        } and serve_confidence >= self.config.serve_prepare_confidence:
            phase = SemanticPhase.PRE_SERVE
            confidence = max(confidence, serve_confidence)
        elif bool(evidence_map.get("post_rally", False)) and phase not in {
            SemanticPhase.RALLY_ACTIVE,
            SemanticPhase.PRE_SERVE,
            SemanticPhase.SERVE_ARMED,
        }:
            phase = SemanticPhase.POST_RALLY
            confidence = max(confidence, 0.75 if authority != SemanticAuthority.NONE else 0.0)
        elif serve_armed or serve_confidence >= self.config.serve_armed_confidence:
            phase = SemanticPhase.SERVE_ARMED
            confidence = max(confidence, serve_confidence)
        elif phase == SemanticPhase.SERVE_ARMED and rally_active:
            phase = SemanticPhase.RALLY_ACTIVE
            confidence = max(confidence, float(evidence_map.get("rally_confidence", 0.0) or 0.0))
        elif rally_active:
            phase = SemanticPhase.RALLY_ACTIVE
            confidence = max(confidence, float(evidence_map.get("rally_confidence", 0.0) or 0.0))
        elif phase == SemanticPhase.RALLY_ACTIVE and end_evidence_count >= self.config.rally_end_min_evidence:
            # 只有达到旧策略的候选阈值才改变公开 phase；单次弱信号仍可
            # 在内部进入 pending_end，但保留 RALLY_ACTIVE 兼容行为。
            if phase == SemanticPhase.RALLY_END_CANDIDATE:
                phase = SemanticPhase.RALLY_END_CANDIDATE
            else:
                phase = SemanticPhase.RALLY_ACTIVE
            confidence = max(confidence, min(1.0, end_evidence_count / 3.0))

        # 单一弱证据不能直接关闭或结束回合。
        if phase == SemanticPhase.UNKNOWN and not evidence_map:
            confidence = 0.0

        # 先处理边界仲裁，再写入状态。权威边界立即确认；算法证据进入 pending，
        # 在稳定窗口内出现有效比赛活动时可 rescue，不直接执行正式 hard gate。
        if authoritative_boundary:
            self._clear_pending_boundary()
            boundary_status = "confirmed_end"
            adjudication_reason = "authoritative_boundary"
        elif self._pending_boundary == "pending_end" and active_play_evidence:
            self._advance_pending_boundary("pending_end", current_timestamp_ms, evidence_ids)
            self._rescue_ticks += 1
            contradiction_ids = evidence_ids
            if self._rescue_ticks >= max(1, int(self.config.rescue_min_consecutive_ticks)):
                boundary_status = "rescued_active"
                rescue_reason = "active_ball_and_player_evidence_reappeared"
                adjudication_reason = "pending_end_rescued"
                self._clear_pending_boundary()
                phase = SemanticPhase.RALLY_ACTIVE
                confidence = max(confidence, float(evidence_map.get("rally_confidence", 0.0) or 0.0))
            else:
                boundary_status = "pending_end"
                pending_boundary = "pending_end"
                adjudication_reason = "awaiting_rescue_corroboration"
                phase = SemanticPhase.RALLY_ACTIVE
                confidence = max(
                    0.0,
                    max(confidence, float(evidence_map.get("rally_confidence", 0.0) or 0.0))
                    - max(0.0, float(self.config.conflict_penalty)),
                )
        elif phase == SemanticPhase.RALLY_END_CANDIDATE or (self.phase == SemanticPhase.RALLY_ACTIVE and end_signal):
            was_existing_end_candidate = self.phase == SemanticPhase.RALLY_END_CANDIDATE
            was_pending_end = self._pending_boundary == "pending_end"
            self._advance_pending_boundary(
                "pending_end",
                current_timestamp_ms,
                evidence_ids,
            )
            pending_boundary = "pending_end"
            boundary_status = "pending_end"
            adjudication_reason = "weak_or_partial_end_evidence"
            if was_existing_end_candidate or was_pending_end or end_evidence_count >= self.config.rally_end_min_evidence:
                phase = SemanticPhase.RALLY_END_CANDIDATE
            if self._pending_end_confirmed(current_timestamp_ms, evidence_map):
                phase = SemanticPhase.POST_RALLY
                boundary_status = "confirmed_end"
                pending_boundary = None
                adjudication_reason = "stable_end_evidence"
                self._clear_pending_boundary()
        elif phase == SemanticPhase.PRE_SERVE and previous_phase in {
            SemanticPhase.NON_PLAY_CONFIRMED,
            SemanticPhase.POST_RALLY,
        }:
            self._advance_pending_boundary("pending_start", current_timestamp_ms, evidence_ids)
            pending_boundary = "pending_start"
            boundary_status = "pending_start"
            adjudication_reason = "serve_prepare_evidence"
        elif phase == SemanticPhase.SERVE_ARMED and previous_phase == SemanticPhase.PRE_SERVE:
            self._advance_pending_boundary("pending_start", current_timestamp_ms, evidence_ids)
            pending_boundary = "pending_start"
            boundary_status = "pending_start"
            adjudication_reason = "serve_arm_evidence"
        elif phase == SemanticPhase.RALLY_ACTIVE and previous_phase != SemanticPhase.RALLY_ACTIVE:
            boundary_status = "confirmed_start"
            adjudication_reason = "rally_active_evidence"
            self._clear_pending_boundary()

        if boundary_status == "none" and self._pending_boundary is not None:
            pending_boundary = self._pending_boundary
            boundary_status = self._pending_boundary
        self.phase = phase
        self._last_timestamp_ms = current_timestamp_ms
        fallback = phase == SemanticPhase.UNKNOWN and authority == SemanticAuthority.NONE
        boundary_action = self._boundary_action(
            previous_phase=previous_phase,
            phase=phase,
            authority=authority,
            timeline_event_type=timeline_event_type,
        )
        phase_changed = phase != previous_phase
        boundary_action_id = None
        if boundary_action != BallBoundaryAction.NONE:
            event_id = next(
                (str(item) for item in reversed(tuple(timeline_event_ids)) if str(item)),
                None,
            )
            boundary_action_id = (
                f"semantic-boundary:{event_id}:{phase.value}"
                if event_id
                else f"semantic-boundary:{int(float(timestamp_ms))}:{phase.value}"
            )
        lifecycle = self._formal_segment_lifecycle(phase, boundary_action)
        return MatchSemanticSnapshot(
            take_timestamp_ms=float(timestamp_ms),
            phase=phase,
            phase_confidence=max(0.0, min(1.0, confidence)),
            authority=authority,
            evidence=evidence_map,
            policy_mode=self.config.mode,
            policy_decision=BallPolicyAction.FALLBACK if fallback else BallPolicyAction.ALLOW,
            decision_reason="semantic_unknown_fallback" if fallback else "state_machine_evidence",
            semantic_fallback=fallback,
            timeline_event_ids=tuple(str(item) for item in timeline_event_ids),
            previous_phase=previous_phase,
            phase_changed=phase_changed,
            boundary_action=boundary_action,
            boundary_action_id=boundary_action_id,
            formal_segment_lifecycle=lifecycle,
            evidence_ids=evidence_ids,
            boundary_status=boundary_status,
            pending_boundary=pending_boundary,
            adjudication_reason=adjudication_reason,
            contradiction_evidence_ids=contradiction_ids,
            rescue_reason=rescue_reason,
        )

    def _advance_pending_boundary(
        self,
        boundary: str,
        timestamp_ms: float,
        evidence_ids: tuple[str, ...],
    ) -> None:
        if self._pending_boundary != boundary:
            self._pending_boundary = boundary
            self._pending_since_ms = timestamp_ms
            self._pending_ticks = 0
            self._rescue_ticks = 0
        elif self._last_timestamp_ms is not None and timestamp_ms >= self._last_timestamp_ms:
            self._pending_ticks += 1
        self._pending_evidence_ids = evidence_ids

    def _clear_pending_boundary(self) -> None:
        self._pending_boundary = None
        self._pending_since_ms = None
        self._pending_ticks = 0
        self._rescue_ticks = 0
        self._pending_evidence_ids = ()

    def _pending_end_confirmed(self, timestamp_ms: float, evidence: Mapping[str, Any]) -> bool:
        if self._pending_boundary != "pending_end":
            return False
        if bool(evidence.get("all_boundary_evidence_stale", False)):
            return False
        if bool(evidence.get("algorithmic_rally_end_confirmed", False)):
            return True
        elapsed_sec = (
            max(0.0, timestamp_ms - self._pending_since_ms) / 1000.0
            if self._pending_since_ms is not None
            else 0.0
        )
        corroboration_count = self._end_corroboration_count(evidence)
        return (
            self._pending_ticks >= max(1, int(self.config.min_confirm_ticks))
            and elapsed_sec >= max(0.0, float(self.config.grace_window_sec))
            and corroboration_count >= max(2, int(self.config.rally_end_min_evidence))
            and not self._has_active_play_evidence(evidence)
        )

    @staticmethod
    def _has_active_play_evidence(evidence: Mapping[str, Any]) -> bool:
        motion = float(evidence.get("ball_motion_pixels", 0.0) or 0.0)
        motion_threshold = float(evidence.get("rescue_min_motion_pixels", 15.0) or 15.0)
        return bool(
            evidence.get("valid_ball_motion", False)
            or evidence.get("rally_active", False)
            or motion >= motion_threshold
            or float(evidence.get("player_motion_pixels", 0.0) or 0.0) >= motion_threshold
        )

    @staticmethod
    def _has_end_signal(evidence: Mapping[str, Any], end_evidence_count: int) -> bool:
        visibility = str(evidence.get("ball_visibility", "")).lower()
        return bool(
            end_evidence_count > 0
            or evidence.get("rally_end_candidate", False)
            or visibility in {"lost", "ended", "out", "net"}
        )

    @staticmethod
    def _end_corroboration_count(evidence: Mapping[str, Any]) -> int:
        count = int(evidence.get("rally_end_evidence_count", 0) or 0)
        count += int(bool(evidence.get("non_play_confirmed", False)))
        count += int(str(evidence.get("ball_visibility", "")).lower() in {"lost", "ended", "out", "net"})
        count += int(bool(evidence.get("player_activity_ended", False)))
        return count

    @staticmethod
    def _boundary_action(
        *,
        previous_phase: SemanticPhase,
        phase: SemanticPhase,
        authority: SemanticAuthority,
        timeline_event_type: str,
    ) -> BallBoundaryAction:
        hard_authority = authority in {SemanticAuthority.MANUAL, SemanticAuthority.CORRECTED}
        if hard_authority and timeline_event_type in {"rally_end", "non_play"} and phase != previous_phase:
            return BallBoundaryAction.SEAL_FORMAL_SEGMENT
        if hard_authority and phase in {SemanticPhase.NON_PLAY_CONFIRMED, SemanticPhase.POST_RALLY} and previous_phase not in {
            SemanticPhase.UNKNOWN,
            SemanticPhase.NON_PLAY_CONFIRMED,
            SemanticPhase.POST_RALLY,
        }:
            return BallBoundaryAction.SEAL_FORMAL_SEGMENT
        if phase == SemanticPhase.PRE_SERVE and phase != previous_phase and (
            previous_phase in {
                SemanticPhase.NON_PLAY_CONFIRMED,
                SemanticPhase.POST_RALLY,
            }
            or timeline_event_type in {"non_play_end", "outside_effective_window"}
        ):
            return BallBoundaryAction.WARM_REACQUIRE
        if phase == SemanticPhase.SERVE_ARMED and previous_phase != SemanticPhase.SERVE_ARMED:
            return BallBoundaryAction.SERVE_REACQUIRE
        if phase == SemanticPhase.RALLY_ACTIVE and phase != previous_phase and (
            timeline_event_type == "rally" or previous_phase in {SemanticPhase.SERVE_ARMED, SemanticPhase.PRE_SERVE}
        ):
            return BallBoundaryAction.OPEN_FORMAL_SEGMENT
        return BallBoundaryAction.NONE

    @staticmethod
    def _formal_segment_lifecycle(
        phase: SemanticPhase,
        boundary_action: BallBoundaryAction,
    ) -> FormalSegmentLifecycle:
        if boundary_action == BallBoundaryAction.WARM_REACQUIRE:
            return FormalSegmentLifecycle.WARM
        if boundary_action == BallBoundaryAction.SERVE_REACQUIRE:
            return FormalSegmentLifecycle.WARM
        if boundary_action == BallBoundaryAction.OPEN_FORMAL_SEGMENT or phase == SemanticPhase.RALLY_ACTIVE:
            return FormalSegmentLifecycle.OPEN
        if boundary_action == BallBoundaryAction.SEAL_FORMAL_SEGMENT or phase in {
            SemanticPhase.NON_PLAY_CONFIRMED,
            SemanticPhase.POST_RALLY,
        }:
            return FormalSegmentLifecycle.SEALED
        return FormalSegmentLifecycle.NONE


@dataclass(frozen=True)
class _TimelineEvent:
    event_id: str
    event_type: str
    timestamp_ms: int
    source: str

    @property
    def hard_authority(self) -> SemanticAuthority:
        if self.source == SemanticAuthority.CORRECTED.value:
            return SemanticAuthority.CORRECTED
        if self.source == SemanticAuthority.MANUAL.value:
            return SemanticAuthority.MANUAL
        return SemanticAuthority.ALGORITHM if self.source else SemanticAuthority.NONE


def _event_value(event: Any, key: str, default: Any = None) -> Any:
    if isinstance(event, Mapping):
        return event.get(key, default)
    return getattr(event, key, default)


class SemanticTimelineProvider:
    """将 timeline event 或有效时间窗口转换成 canonical 语义快照。"""

    _NON_PLAY_START = {
        "non_play_start",
        "timeout_start",
        "side_change",
        "drill_start",
    }
    _NON_PLAY_END = {
        "non_play_end",
        "timeout_end",
        "drill_end",
    }

    def __init__(
        self,
        events: Sequence[Any] | None = None,
        *,
        effective_windows: Sequence[tuple[float, float]] | None = None,
        config: BallSemanticPolicyConfig | None = None,
    ) -> None:
        self.config = config or BallSemanticPolicyConfig()
        self.events = tuple(self._normalize_events(events or ()))
        self.effective_windows = tuple((float(start), float(end)) for start, end in (effective_windows or ()))
        self.state_machine = SemanticStateMachine(self.config)
        from app.vision.pickleball_game_analysis.semantic_boundary_calibration import SemanticEvidenceLedger

        self.evidence_ledger = SemanticEvidenceLedger()

    @classmethod
    def from_events(
        cls,
        events: Sequence[Any] | None = None,
        *,
        effective_windows: Sequence[tuple[float, float]] | None = None,
        config: BallSemanticPolicyConfig | None = None,
    ) -> "SemanticTimelineProvider":
        return cls(events, effective_windows=effective_windows, config=config)

    @classmethod
    def from_capture_take(
        cls,
        capture_take_id: str | None,
        *,
        clip_start_ms: int | None = None,
        clip_end_ms: int | None = None,
        video_duration_ms: int | None = None,
        config: BallSemanticPolicyConfig | None = None,
    ) -> "SemanticTimelineProvider":
        """从现有 CaptureTake 时间线构造 provider；数据库不可用时 fail-open。"""

        if not capture_take_id:
            return cls(config=config)
        try:
            from app.database import get_session_factory
            from app.services.capture_take_service import get_capture_take
            from app.services.timeline_event_service import list_timeline_events
            from app.vision.pickleball_game_analysis.effective_time_windows import resolve_effective_windows

            db = get_session_factory()()
            try:
                take = get_capture_take(db, capture_take_id)
                if take is None:
                    return cls(config=config)
                events = list_timeline_events(
                    db,
                    take.field_session_id,
                    capture_take_id=capture_take_id,
                )
            finally:
                db.close()
            windows = resolve_effective_windows(
                clip_start_ms=clip_start_ms,
                clip_end_ms=clip_end_ms,
                capture_take_id=capture_take_id,
                video_duration_ms=video_duration_ms,
            )
            return cls(events, effective_windows=windows, config=config)
        except Exception:
            # 语义 provider 不能成为球员/球体主链的硬依赖。
            return cls(config=config)

    def reset(self) -> None:
        self.state_machine.reset()
        self.evidence_ledger.records.clear()

    def _with_evidence_ledger(
        self,
        timestamp_ms: float,
        evidence: dict[str, Any],
        authority: SemanticAuthority,
    ) -> dict[str, Any]:
        records = self.evidence_ledger.add_tick(
            timestamp_ms,
            evidence,
            authority=authority,
            freshness_seconds=self.config.evidence_freshness_sec,
        )
        evidence["evidence_ids"] = tuple(record.evidence_id for record in records)
        evidence["evidence_record_count"] = len(records)
        evidence["stale_evidence_ids"] = tuple(
            record.evidence_id for record in records if record.is_stale(float(timestamp_ms))
        )
        boundary_records = [
            record
            for record in records
            if record.kind in {"timeline", "rally_end_signal", "ball_motion", "ball_continuity"}
        ]
        evidence["all_boundary_evidence_stale"] = bool(boundary_records) and all(
            record.is_stale(float(timestamp_ms)) for record in boundary_records
        )
        return evidence

    def snapshot(
        self,
        timestamp_ms: float,
        *,
        evidence: Mapping[str, Any] | None = None,
    ) -> MatchSemanticSnapshot:
        ts = float(timestamp_ms)
        relevant = [event for event in self.events if event.timestamp_ms <= ts]
        active_non_play = self._active_non_play(relevant)
        active_rally = self._active_rally(relevant)
        event_ids = tuple(event.event_id for event in relevant[-6:])
        authority = self._highest_authority(active_non_play or active_rally)
        evidence_map = dict(evidence or {})
        if active_non_play:
            evidence_map.update(
                {
                    "non_play_confirmed": authority in {SemanticAuthority.MANUAL, SemanticAuthority.CORRECTED},
                    "timeline_event_type": "non_play",
                    "timeline_event_ids": list(event_ids),
                }
            )
            return self.state_machine.update(
                ts,
                evidence=self._with_evidence_ledger(ts, evidence_map, authority),
                authority=authority,
                timeline_event_ids=event_ids,
            )

        if active_rally:
            evidence_map.update({"rally_active": True, "timeline_event_type": "rally"})
            return self.state_machine.update(
                ts,
                evidence=self._with_evidence_ledger(ts, evidence_map, authority),
                authority=authority,
                timeline_event_ids=event_ids,
            )

        last_rally_end = next(
            (
                event
                for event in reversed(relevant)
                if event.event_type == "rally_end"
            ),
            None,
        )
        if last_rally_end is not None:
            evidence_map.update(
                {
                    "post_rally": True,
                    "rally_end_confirmed": last_rally_end.hard_authority
                    in {SemanticAuthority.MANUAL, SemanticAuthority.CORRECTED},
                    "timeline_event_type": "rally_end",
                }
            )
            return self.state_machine.update(
                ts,
                evidence=self._with_evidence_ledger(ts, evidence_map, last_rally_end.hard_authority),
                authority=last_rally_end.hard_authority,
                timeline_event_ids=event_ids,
            )

        last_non_play_end = next(
            (
                event
                for event in reversed(relevant)
                if event.event_type in self._NON_PLAY_END
            ),
            None,
        )
        if last_non_play_end is not None:
            evidence_map.update({"post_rally": True, "timeline_event_type": "non_play_end"})
            return self.state_machine.update(
                ts,
                evidence=self._with_evidence_ledger(ts, evidence_map, last_non_play_end.hard_authority),
                authority=last_non_play_end.hard_authority,
                timeline_event_ids=event_ids,
            )

        # 时间线存在但当前在所有有效窗口之外，优先表达 post-rally；
        # 没有任何时间线时则交给视觉 state machine，缺证据自然回到 UNKNOWN。
        if self.effective_windows and not any(start <= ts / 1000.0 < end for start, end in self.effective_windows):
            evidence_map.update({"post_rally": True, "timeline_event_type": "outside_effective_window"})
            snapshot = self.state_machine.update(
                ts,
                evidence=self._with_evidence_ledger(ts, evidence_map, authority),
                authority=authority,
                timeline_event_ids=event_ids,
            )
            if snapshot.phase == SemanticPhase.UNKNOWN:
                return MatchSemanticSnapshot(
                    **{
                        **snapshot.__dict__,
                        "phase": SemanticPhase.POST_RALLY,
                        "phase_confidence": 0.75 if authority != SemanticAuthority.NONE else 0.0,
                        "authority": authority,
                        "semantic_fallback": authority == SemanticAuthority.NONE,
                        "decision_reason": "outside_effective_play_window",
                    }
                )
            return snapshot

        return self.state_machine.update(
            ts,
            evidence=self._with_evidence_ledger(ts, evidence_map, authority),
            authority=authority,
            timeline_event_ids=event_ids,
        )

    def diagnostics_snapshot(self) -> dict[str, Any]:
        return {
            "schema_version": SEMANTIC_TIMELINE_SCHEMA_VERSION,
            "policy_version": self.config.policy_version,
            "event_count": len(self.events),
            "effective_window_count": len(self.effective_windows),
            "evidence_ledger": self.evidence_ledger.to_list(),
            "config": self.config.snapshot(),
        }

    @classmethod
    def _normalize_events(cls, events: Sequence[Any]) -> list[_TimelineEvent]:
        normalized: list[_TimelineEvent] = []
        for index, raw in enumerate(events):
            event_type = _event_value(raw, "event_type", _event_value(raw, "type", ""))
            event_type = getattr(event_type, "value", event_type)
            timestamp_ms = _event_value(raw, "timestamp_ms", _event_value(raw, "timestampMs", 0))
            try:
                timestamp = int(timestamp_ms or 0)
            except (TypeError, ValueError):
                continue
            if bool(_event_value(raw, "is_undone", False)):
                continue
            source = _event_value(raw, "source", "")
            source = getattr(source, "value", source) or ""
            normalized.append(
                _TimelineEvent(
                    event_id=str(_event_value(raw, "id", f"timeline-{index + 1}")),
                    event_type=str(event_type or ""),
                    timestamp_ms=timestamp,
                    source=str(source),
                )
            )
        return sorted(normalized, key=lambda event: (event.timestamp_ms, event.event_id))

    def _active_non_play(self, relevant: Sequence[_TimelineEvent]) -> list[_TimelineEvent]:
        active: list[_TimelineEvent] = []
        for event in relevant:
            if event.event_type in self._NON_PLAY_START:
                active.append(event)
            elif event.event_type in self._NON_PLAY_END and active:
                active.pop()
        return active

    @staticmethod
    def _active_rally(relevant: Sequence[_TimelineEvent]) -> list[_TimelineEvent]:
        active: list[_TimelineEvent] = []
        for event in relevant:
            if event.event_type == "rally_start":
                active.append(event)
            elif event.event_type == "rally_end" and active:
                active.pop()
        return active

    @staticmethod
    def _highest_authority(events: Sequence[_TimelineEvent]) -> SemanticAuthority:
        if not events:
            return SemanticAuthority.NONE
        ranked = {
            SemanticAuthority.CORRECTED: 4,
            SemanticAuthority.MANUAL: 3,
            SemanticAuthority.ALGORITHM: 2,
            SemanticAuthority.NONE: 0,
        }
        return max((event.hard_authority for event in events), key=lambda value: ranked[value])


def build_semantic_timeline_payload(
    *,
    job_id: str,
    take_id: str | None,
    snapshots: Sequence[MatchSemanticSnapshot],
    decisions: Sequence[BallSearchDecision],
    diagnostics: Mapping[str, Any] | None = None,
    frame_stride: int | None = None,
    timestamp_provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """生成可回放的语义诊断 artifact。"""

    provenance = {
        "clock": "unknown",
        "time_unit": "milliseconds",
        "coordinate": "canonical_take_time",
        **dict(timestamp_provenance or {}),
    }
    payload_diagnostics = dict(diagnostics or {})
    payload_diagnostics.setdefault(
        "semantic_shadow_metrics",
        compute_semantic_shadow_metrics(snapshots, decisions),
    )

    return {
        "schema_version": SEMANTIC_TIMELINE_SCHEMA_VERSION,
        "artifact_kind": "ball_semantic_timeline",
        "job_id": job_id,
        "capture_take_id": take_id,
        "frame_stride": frame_stride,
        "timestamp_provenance": provenance,
        "evidence_ledger": list(payload_diagnostics.get("evidence_ledger", ())),
        "snapshots": [snapshot.to_dict() for snapshot in snapshots],
        "decisions": [decision.to_dict() for decision in decisions],
        "diagnostics": payload_diagnostics,
    }


def compute_semantic_shadow_metrics(
    snapshots: Sequence[MatchSemanticSnapshot],
    decisions: Sequence[BallSearchDecision],
    *,
    duration_seconds: float | None = None,
    accepted_timestamps_ms: Sequence[float] = (),
) -> dict[str, Any]:
    """计算 Shadow/Enforced 都可复用的稳定对照指标。

    指标刻意基于 raw candidate 和策略决策计算，使 Shadow Mode 可以在不改变
    正式球路的情况下，回答“如果启用策略会抑制什么”。正式接受延迟只有在调用方
    提供 accepted timestamps 时才计算，缺数据时保持 ``None`` 而不是猜测。
    """

    snapshot_list = list(snapshots)
    decision_list = list(decisions)
    phase_counts = {phase.value: 0 for phase in SemanticPhase}
    authority_counts = {authority.value: 0 for authority in SemanticAuthority}
    for snapshot in snapshot_list:
        phase_counts[snapshot.phase.value] = phase_counts.get(snapshot.phase.value, 0) + 1
        authority_counts[snapshot.authority.value] = authority_counts.get(snapshot.authority.value, 0) + 1

    raw_candidate_count = sum(
        max(0, int(decision.diagnostics.get("raw_candidate_count", 0) or 0))
        for decision in decision_list
    )
    recommended_suppressed_count = sum(
        max(0, int(decision.diagnostics.get("raw_candidate_count", 0) or 0))
        for decision in decision_list
        if not decision.recommended_formal_publish
    )
    effective_suppressed_count = sum(
        max(0, int(decision.diagnostics.get("raw_candidate_count", 0) or 0))
        for decision in decision_list
        if not decision.formal_publish_allowed
    )
    boundary_action_counts = {action.value: 0 for action in BallBoundaryAction}
    hard_gate_tick_count = 0
    warm_capture_tick_count = 0
    formal_publish_count = 0
    for decision in decision_list:
        boundary_action_counts[decision.boundary_action.value] = (
            boundary_action_counts.get(decision.boundary_action.value, 0) + 1
        )
        if decision.hard_gate_active:
            hard_gate_tick_count += 1
        if not decision.formal_publish_allowed and decision.tracker_update_allowed:
            warm_capture_tick_count += 1
        formal_publish_count += max(0, int(decision.formal_candidate_count_after or 0))
    serve_timestamps = [
        snapshot.take_timestamp_ms
        for snapshot in snapshot_list
        if snapshot.phase in {SemanticPhase.PRE_SERVE, SemanticPhase.SERVE_ARMED}
    ]
    accepted = sorted(float(timestamp) for timestamp in accepted_timestamps_ms)
    first_serve_timestamp = min(serve_timestamps) if serve_timestamps else None
    first_reliable_after_serve = next(
        (timestamp for timestamp in accepted if first_serve_timestamp is not None and timestamp >= first_serve_timestamp),
        None,
    )
    serve_latency = (
        first_reliable_after_serve - first_serve_timestamp
        if first_serve_timestamp is not None and first_reliable_after_serve is not None
        else None
    )
    duration = float(duration_seconds) if duration_seconds is not None and duration_seconds > 0 else None

    return {
        "snapshot_count": len(snapshot_list),
        "decision_count": len(decision_list),
        "raw_candidate_count": raw_candidate_count,
        "recommended_suppressed_candidate_count": recommended_suppressed_count,
        "effective_suppressed_candidate_count": effective_suppressed_count,
        "recommended_suppression_ratio": (
            recommended_suppressed_count / raw_candidate_count if raw_candidate_count else 0.0
        ),
        "effective_suppression_ratio": (
            effective_suppressed_count / raw_candidate_count if raw_candidate_count else 0.0
        ),
        "hard_gate_tick_count": hard_gate_tick_count,
        "warm_capture_tick_count": warm_capture_tick_count,
        "formal_publish_candidate_count": formal_publish_count,
        "boundary_action_counts": boundary_action_counts,
        "non_play_candidate_count_per_minute": (
            recommended_suppressed_count / (duration / 60.0) if duration else None
        ),
        "unknown_ratio": (
            phase_counts[SemanticPhase.UNKNOWN.value] / len(snapshot_list) if snapshot_list else 0.0
        ),
        "serve_to_first_reliable_observation_latency_ms": serve_latency,
        "phase_counts": phase_counts,
        "authority_counts": authority_counts,
    }


def serve_candidate_semantic_snapshot(
    candidate: Any,
    *,
    mode: SemanticPolicyMode = SemanticPolicyMode.SHADOW,
) -> MatchSemanticSnapshot:
    """把 ServeStartDetector 候选转成语义 evidence，不把它升级为击球/比分事件。"""

    timestamp_seconds = float(
        _event_value(candidate, "timestamp_seconds", _event_value(candidate, "timestamp_sec", 0.0)) or 0.0
    )
    confidence = float(_event_value(candidate, "confidence", 0.0) or 0.0)
    candidate_id = str(_event_value(candidate, "id", "serve-candidate"))
    evidence = {
        "serve_candidate": True,
        "serve_candidate_id": candidate_id,
        "serve_candidate_confidence": confidence,
        "serve_reason": str(_event_value(candidate, "reason", "")),
        "serve_source_signals": list(_event_value(candidate, "source_signals", ()) or ()),
        "serve_detection_mode": _event_value(candidate, "detection_mode", None),
    }
    return MatchSemanticSnapshot(
        take_timestamp_ms=timestamp_seconds * 1000.0,
        phase=SemanticPhase.SERVE_ARMED,
        phase_confidence=max(0.0, min(1.0, confidence)),
        authority=SemanticAuthority.ALGORITHM,
        evidence=_jsonable(evidence),
        policy_mode=mode,
        policy_decision=BallPolicyAction.SERVE_REACQUIRE,
        decision_reason="serve_detector_candidate_evidence",
        semantic_fallback=False,
        timeline_event_ids=(candidate_id,),
    )


def semantic_config_snapshot(config: BallSemanticPolicyConfig) -> dict[str, Any]:
    """返回稳定 JSON 字符串前的配置快照，便于 artifact diagnostics 使用。"""

    return config.snapshot()


def semantic_config_snapshot_json(config: BallSemanticPolicyConfig) -> str:
    return json.dumps(semantic_config_snapshot(config), ensure_ascii=False, sort_keys=True)


__all__ = [
    "SEMANTIC_TIMELINE_SCHEMA_VERSION",
    "BallPolicyAction",
    "BallSearchDecision",
    "BallSearchPolicy",
    "BallSemanticPolicyConfig",
    "MatchSemanticSnapshot",
    "SemanticAuthority",
    "SemanticPhase",
    "SemanticPolicyMode",
    "SemanticStateMachine",
    "SemanticTimelineProvider",
    "build_semantic_timeline_payload",
    "compute_semantic_shadow_metrics",
    "serve_candidate_semantic_snapshot",
    "semantic_config_snapshot",
    "semantic_config_snapshot_json",
]
