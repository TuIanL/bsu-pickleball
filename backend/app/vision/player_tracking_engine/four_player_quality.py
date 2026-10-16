"""Four-player identity quality contract and deterministic comparison helpers."""

from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


QUALITY_SCHEMA_VERSION = "four-player-identification-quality.v1"
CANONICAL_PLAYERS = tuple(f"Player_{index}" for index in range(1, 5))


class IdentificationThresholds(BaseModel):
    min_player_coverage: float = Field(default=0.70, ge=0.0, le=1.0)
    max_gap_seconds: float = Field(default=2.0, gt=0.0)
    required_confirmed_roster: int = Field(default=4, ge=4, le=4)
    max_identity_switches: int = Field(default=0, ge=0)
    max_duplicate_bindings: int = Field(default=0, ge=0)
    max_cross_side_samples: int = Field(default=0, ge=0)
    max_local_slot_reassociation_violations: int = Field(default=0, ge=0)
    max_display_topology_transitions: int = Field(default=12, ge=0)


class AppearanceQualitySummary(BaseModel):
    descriptor_attempts: int = Field(default=0, ge=0)
    descriptor_available: int = Field(default=0, ge=0)
    mean_quality: float | None = Field(default=None, ge=0.0, le=1.0)
    template_updates: int = Field(default=0, ge=0)
    template_freezes: int = Field(default=0, ge=0)
    template_age_ticks: int | None = Field(default=None, ge=0)
    decision_contributions: int = Field(default=0, ge=0)
    decision_supports: int = Field(default=0, ge=0)
    decision_conflicts: int = Field(default=0, ge=0)
    effective_weight: float = Field(default=0.0, ge=0.0)
    fallback_reason: str | None = None


class PlayerIdentificationSummary(BaseModel):
    player_id: str
    detection_ticks: int = Field(default=0, ge=0)
    canonical_ticks: int = Field(default=0, ge=0)
    detection_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    canonical_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    longest_gap_seconds: float = Field(default=0.0, ge=0.0)
    source_track_history: dict[str, list[int]] = Field(default_factory=dict)
    source_track_count: int = Field(default=0, ge=0)
    reconnect_count: int = Field(default=0, ge=0)
    identity_switch_count: int = Field(default=0, ge=0)
    duplicate_binding_count: int = Field(default=0, ge=0)
    cross_side_count: int = Field(default=0, ge=0)
    ambiguous_count: int = Field(default=0, ge=0)
    quarantined_count: int = Field(default=0, ge=0)
    accepted_count: int = Field(default=0, ge=0)
    local_slot_reassociation_violation_count: int = Field(default=0, ge=0)
    display_topology_transition_count: int = Field(default=0, ge=0)
    appearance: AppearanceQualitySummary = Field(default_factory=AppearanceQualitySummary)


class PipelineFunnelCounters(BaseModel):
    attempted_ticks: int = Field(default=0, ge=0)
    base_detection_ticks: int = Field(default=0, ge=0)
    roi_attempts: int = Field(default=0, ge=0)
    roi_hits: int = Field(default=0, ge=0)
    tracker_fragments: int = Field(default=0, ge=0)
    duplicate_binding_count: int = Field(default=0, ge=0)
    cross_side_count: int = Field(default=0, ge=0)
    quarantined_count: int = Field(default=0, ge=0)
    identity_switch_count: int = Field(default=0, ge=0)
    local_slot_reassociation_violation_count: int = Field(default=0, ge=0)
    display_topology_transition_count: int = Field(default=0, ge=0)
    bbox_footpoint_inconsistency_count: int = Field(default=0, ge=0)


class CandidateRecoveryQuality(BaseModel):
    available: bool = False
    enabled: bool = False
    detail: str | None = None
    minimum_consecutive_ticks: int | None = Field(default=None, ge=1)
    maximum_step_ft: float | None = Field(default=None, ge=0.0)
    unique_match_margin_ft: float | None = Field(default=None, ge=0.0)
    evidence_ttl_ticks: int | None = Field(default=None, ge=1)
    pending_evidence_count: int | None = Field(default=None, ge=0)
    counters: dict[str, int] = Field(default_factory=dict)


class FourPlayerIdentificationQuality(BaseModel):
    schema_version: Literal["four-player-identification-quality.v1"] = QUALITY_SCHEMA_VERSION
    job_id: str
    baseline_job_id: str | None = None
    status: Literal["available", "unavailable", "failed"] = "available"
    detail: str = ""
    algorithm_version: str
    config_signature: str | None = None
    thresholds: IdentificationThresholds = Field(default_factory=IdentificationThresholds)
    attempted_ticks: int = Field(default=0, ge=0)
    duration_seconds: float = Field(default=0.0, ge=0.0)
    confirmed_roster_count: int = Field(default=0, ge=0, le=4)
    players: dict[str, PlayerIdentificationSummary] = Field(default_factory=dict)
    funnel: PipelineFunnelCounters = Field(default_factory=PipelineFunnelCounters)
    candidate_recovery: CandidateRecoveryQuality = Field(default_factory=CandidateRecoveryQuality)
    per_view_funnel: dict[str, dict[str, Any]] = Field(default_factory=dict)
    per_canonical_end_funnel: dict[str, dict[str, Any]] = Field(default_factory=dict)
    identity_slots: dict[str, dict[str, Any]] = Field(default_factory=dict)
    mapping_confirmation_available: bool = False
    mapping_confirmed_by_player: dict[str, bool | None] = Field(default_factory=dict)
    # 7.3：roster.json 与 anchor_binding_audit 对同一槽位给出互斥结论时的证据。
    # 非空即表示身份审计存在双源真相冲突，质量 verdict 必须 fail-closed。
    mapping_conflict_with_audit: dict[str, dict[str, Any]] = Field(default_factory=dict)
    camera_profiles: dict[str, dict[str, Any]] = Field(default_factory=dict)
    hard_invariants: dict[str, bool] = Field(default_factory=dict)
    absolute_gates: dict[str, bool] = Field(default_factory=dict)
    verdict: Literal["pass", "fail", "unavailable"] = "unavailable"
    failure_reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_complete_roster(self) -> "FourPlayerIdentificationQuality":
        if self.status == "available" and set(self.players) != set(CANONICAL_PLAYERS):
            raise ValueError("available quality artifact must contain exactly Player_1..Player_4")
        return self


class QualityComparison(BaseModel):
    schema_version: Literal["four-player-identification-comparison.v1"] = (
        "four-player-identification-comparison.v1"
    )
    baseline_job_id: str
    candidate_job_id: str
    hard_invariants_pass: bool
    absolute_gates_pass: bool
    relative_gates_pass: bool
    threshold_compatible: bool
    verdict: Literal["pass", "fail", "unavailable"]
    reasons: list[str] = Field(default_factory=list)
    player_deltas: dict[str, dict[str, float]] = Field(default_factory=dict)


def evaluate_quality(artifact: FourPlayerIdentificationQuality) -> FourPlayerIdentificationQuality:
    """Compute fail-closed hard/absolute gates without mutating thresholds."""
    if artifact.status != "available":
        return artifact.model_copy(update={"verdict": "unavailable"})
    thresholds = artifact.thresholds
    duplicate_count = artifact.funnel.duplicate_binding_count + sum(
        player.duplicate_binding_count for player in artifact.players.values()
    )
    cross_side_count = artifact.funnel.cross_side_count + sum(
        player.cross_side_count for player in artifact.players.values()
    )
    switch_count = artifact.funnel.identity_switch_count + sum(
        player.identity_switch_count for player in artifact.players.values()
    )
    local_reassociation_violations = max(
        artifact.funnel.local_slot_reassociation_violation_count,
        sum(player.local_slot_reassociation_violation_count for player in artifact.players.values()),
    )
    hard = {
        "confirmed_roster": artifact.confirmed_roster_count == thresholds.required_confirmed_roster,
        "duplicate_binding_zero": duplicate_count <= thresholds.max_duplicate_bindings,
        "cross_side_zero": cross_side_count <= thresholds.max_cross_side_samples,
        "identity_switch_zero": switch_count <= thresholds.max_identity_switches,
        "local_slot_reassociation_zero": (
            local_reassociation_violations <= thresholds.max_local_slot_reassociation_violations
        ),
    }
    if artifact.mapping_confirmation_available:
        hard["canonical_identity_anchors_confirmed"] = (
            set(artifact.mapping_confirmed_by_player) == set(CANONICAL_PLAYERS)
            and all(artifact.mapping_confirmed_by_player.get(player_id) is True for player_id in CANONICAL_PLAYERS)
        )
    # 7.3：审计与 roster.json 结论冲突时无法判定哪个为真，fail-closed。
    if artifact.mapping_conflict_with_audit:
        hard["identity_audit_single_source"] = False
    elif artifact.identity_slots or artifact.mapping_confirmation_available:
        hard["identity_audit_single_source"] = True
    if artifact.identity_slots:
        confirmed_by_end = {
            end: sum(
                1 for slot in artifact.identity_slots.values()
                if slot.get("status") == "confirmed" and slot.get("canonical_end") == end
            )
            for end in ("end_a", "end_b")
        }
        hard["two_confirmed_players_per_canonical_end"] = confirmed_by_end == {"end_a": 2, "end_b": 2}
    absolute: dict[str, bool] = {}
    for player_id in CANONICAL_PLAYERS:
        player = artifact.players[player_id]
        absolute[f"{player_id}.coverage"] = player.canonical_coverage >= thresholds.min_player_coverage
        absolute[f"{player_id}.longest_gap"] = player.longest_gap_seconds <= thresholds.max_gap_seconds
        absolute[f"{player_id}.display_topology_stable"] = (
            player.display_topology_transition_count <= thresholds.max_display_topology_transitions
        )
    failures = [name for name, passed in {**hard, **absolute}.items() if not passed]
    return artifact.model_copy(
        update={
            "hard_invariants": hard,
            "absolute_gates": absolute,
            "verdict": "pass" if not failures else "fail",
            "failure_reasons": failures,
        }
    )


def compare_quality(
    baseline: FourPlayerIdentificationQuality,
    candidate: FourPlayerIdentificationQuality,
) -> QualityComparison:
    """Compare two immutable artifacts and reject silently weakened thresholds."""
    if baseline.status != "available" or candidate.status != "available":
        return QualityComparison(
            baseline_job_id=baseline.job_id,
            candidate_job_id=candidate.job_id,
            hard_invariants_pass=False,
            absolute_gates_pass=False,
            relative_gates_pass=False,
            threshold_compatible=False,
            verdict="unavailable",
            reasons=["baseline_or_candidate_unavailable"],
        )
    baseline = evaluate_quality(baseline)
    candidate = evaluate_quality(candidate)
    threshold_compatible = (
        candidate.thresholds.min_player_coverage >= baseline.thresholds.min_player_coverage
        and candidate.thresholds.max_gap_seconds <= baseline.thresholds.max_gap_seconds
        and candidate.thresholds.required_confirmed_roster >= baseline.thresholds.required_confirmed_roster
        and candidate.thresholds.max_identity_switches <= baseline.thresholds.max_identity_switches
        and candidate.thresholds.max_duplicate_bindings <= baseline.thresholds.max_duplicate_bindings
        and candidate.thresholds.max_cross_side_samples <= baseline.thresholds.max_cross_side_samples
        and candidate.thresholds.max_local_slot_reassociation_violations
        <= baseline.thresholds.max_local_slot_reassociation_violations
        and candidate.thresholds.max_display_topology_transitions
        <= baseline.thresholds.max_display_topology_transitions
    )
    deltas: dict[str, dict[str, float]] = {}
    relative_pass = True
    for player_id in CANONICAL_PLAYERS:
        old = baseline.players[player_id]
        new = candidate.players[player_id]
        coverage_delta = new.canonical_coverage - old.canonical_coverage
        gap_delta = new.longest_gap_seconds - old.longest_gap_seconds
        deltas[player_id] = {
            "canonical_coverage": coverage_delta,
            "longest_gap_seconds": gap_delta,
        }
    # The OpenSpec regression contract deliberately compares the weakest
    # player, plus the targeted P2 failure, instead of requiring every already
    # near-perfect player to remain bit-for-bit identical across detector runs.
    # Absolute per-player gates and every hard invariant still apply.
    baseline_min_coverage = min(
        player.canonical_coverage for player in baseline.players.values()
    )
    candidate_min_coverage = min(
        player.canonical_coverage for player in candidate.players.values()
    )
    baseline_p2 = baseline.players["Player_2"]
    candidate_p2 = candidate.players["Player_2"]
    if candidate_min_coverage < baseline_min_coverage - 1e-9:
        relative_pass = False
    if candidate_p2.canonical_coverage < baseline_p2.canonical_coverage - 1e-9:
        relative_pass = False
    if candidate_p2.longest_gap_seconds > baseline_p2.longest_gap_seconds + 1e-9:
        relative_pass = False
    hard_pass = all(candidate.hard_invariants.values())
    absolute_pass = all(candidate.absolute_gates.values())
    reasons: list[str] = []
    if not threshold_compatible:
        reasons.append("candidate_thresholds_weakened")
    if not hard_pass:
        reasons.append("hard_invariant_failed")
    if not absolute_pass:
        reasons.append("absolute_gate_failed")
    if not relative_pass:
        reasons.append("relative_regression")
    return QualityComparison(
        baseline_job_id=baseline.job_id,
        candidate_job_id=candidate.job_id,
        hard_invariants_pass=hard_pass,
        absolute_gates_pass=absolute_pass,
        relative_gates_pass=relative_pass,
        threshold_compatible=threshold_compatible,
        verdict="pass" if not reasons else "fail",
        reasons=reasons,
        player_deltas=deltas,
    )


def build_quality_from_joint_artifacts(
    *,
    job_id: str,
    trajectory: dict[str, Any],
    roster: dict[str, Any],
    display_diagnostics: dict[str, Any] | None = None,
    runtime_diagnostics: dict[str, Any] | None = None,
    algorithm_version: str = "legacy-joint-tracking-v2",
    thresholds: IdentificationThresholds | None = None,
) -> FourPlayerIdentificationQuality:
    """Build a conservative baseline summary from published joint artifacts."""
    samples = list(trajectory.get("samples") or [])
    roster_players = list(roster.get("players") or [])
    global_to_player = {
        str(item.get("global_player_id")): str(item.get("player_id"))
        for item in roster_players
        if item.get("global_player_id") and item.get("player_id") in CANONICAL_PLAYERS
    }
    mapping_confirmation_available = any(
        isinstance(item, dict) and "mapping_confirmed" in item
        for item in roster_players
    )
    # 7.3：`roster.json` 的 `mapping_confirmed` 与 `frozen_roster.anchor_binding_audit`
    # 曾各自独立求值，导致同一 Job 内 P4 同时被报成 confirmed 与 unconfirmed。
    # 现在 audit 是唯一权威来源：roster.json 的结论只在 audit 无该槽位记录时作为
    # 兼容回退；两者冲突时记入 `mapping_conflict_with_audit` 并使门槛判定为 fail。
    roster_mapping_confirmed = {
        str(item.get("player_id")): bool(item.get("mapping_confirmed"))
        for item in roster_players
        if isinstance(item, dict)
        and str(item.get("player_id") or "") in CANONICAL_PLAYERS
    }
    frozen_roster = dict((runtime_diagnostics or {}).get("frozen_roster") or {})
    anchor_audit = dict(frozen_roster.get("anchor_binding_audit") or {})
    audit_entries = {
        str(entry.get("canonical_player_id")): entry
        for entry in (anchor_audit.get("entries") or [])
        if isinstance(entry, dict) and entry.get("canonical_player_id") in CANONICAL_PLAYERS
    }
    # 审计条目的 confirmed 必须同时满足 `confirmed is True` 且 formal 槽位回指本身，
    # 否则一个 global 身份可同时声称多个 P 槽位（实测 P4 被 global_player_3/4 同时占用）。
    audit_confirmed_by_player = {
        player_id: (
            entry.get("confirmed") is True
            and entry.get("formal_canonical_player_id") == player_id
        )
        for player_id, entry in audit_entries.items()
    }
    mapping_conflict_with_audit: dict[str, dict[str, Any]] = {}
    mapping_confirmed_by_player: dict[str, bool | None] = {}
    for player_id in CANONICAL_PLAYERS:
        audit_value = audit_confirmed_by_player.get(player_id)
        roster_value = roster_mapping_confirmed.get(player_id)
        if audit_value is None:
            # 审计未覆盖该槽位：兼容回退到 roster.json，并标明来源不是权威审计。
            mapping_confirmed_by_player[player_id] = roster_value
            continue
        mapping_confirmed_by_player[player_id] = audit_value
        if roster_value is not None and roster_value != audit_value:
            mapping_conflict_with_audit[player_id] = {
                "audit_confirmed": audit_value,
                "roster_json_confirmed": roster_value,
                "audit_reason": audit_entries[player_id].get("reason"),
                "audit_global_player_id": audit_entries[player_id].get("global_player_id"),
            }
    expected_end_by_player = {
        player_id: str(entry.get("canonical_end"))
        for player_id, entry in audit_entries.items()
        if entry.get("canonical_end") in {"end_a", "end_b"}
        and audit_confirmed_by_player.get(player_id) is True
        and entry.get("formal_canonical_player_id") == player_id
    }
    processed_timestamps_ms = (runtime_diagnostics or {}).get("processed_tick_timestamps_ms")
    has_processed_timeline = isinstance(processed_timestamps_ms, list) and bool(processed_timestamps_ms)
    if has_processed_timeline:
        ticks = sorted({float(value) / 1000.0 for value in processed_timestamps_ms})
    else:
        ticks = sorted({float(sample.get("timestamp_seconds") or 0.0) for sample in samples})
    duration = max(ticks) - min(ticks) if len(ticks) > 1 else 0.0
    timestamps: dict[str, list[float]] = defaultdict(list)
    source_tracks: dict[str, dict[str, set[int]]] = defaultdict(lambda: defaultdict(set))
    detection_ticks: dict[str, set[float]] = defaultdict(set)
    perception_track_ids: dict[str, set[int]] = defaultdict(set)
    perception_sample_ticks: dict[str, set[float]] = defaultdict(set)
    eligible_samples_by_end: dict[str, int] = defaultdict(int)
    trajectory_ambiguous: dict[str, int] = defaultdict(int)
    trajectory_quarantined: dict[str, int] = defaultdict(int)
    cross_side_samples: dict[str, int] = defaultdict(int)
    accepted_identity_statuses = {"confirmed_observed", "confirmed_recovered", "interpolated"}
    for sample in samples:
        timestamp = float(sample.get("timestamp_seconds") or 0.0)
        sample_end = _canonical_end_for_y(sample.get("y_ft"))
        if bool(sample.get("metric_eligible")) and sample_end:
            eligible_samples_by_end[sample_end] += 1
        for view_id, observation in (sample.get("view_observations") or {}).items():
            if not isinstance(observation, dict):
                continue
            track_id = observation.get("source_track_id")
            if isinstance(track_id, int):
                perception_track_ids[str(view_id)].add(track_id)
                if bool(sample.get("metric_eligible")):
                    perception_sample_ticks[str(view_id)].add(timestamp)
        player_id = global_to_player.get(str(sample.get("global_player_id")))
        if player_id is None:
            continue
        expected_end = expected_end_by_player.get(player_id)
        if bool(sample.get("metric_eligible")) and expected_end and sample_end in {"end_a", "end_b"} and sample_end != expected_end:
            cross_side_samples[player_id] += 1
        identity_status = str(sample.get("identity_status", "confirmed_observed"))
        mapping_confirmed = (
            mapping_confirmed_by_player.get(player_id) is True
            if mapping_confirmation_available
            else True
        )
        accepted = (
            bool(sample.get("metric_eligible"))
            and identity_status in accepted_identity_statuses
            and mapping_confirmed
        )
        if accepted:
            timestamps[player_id].append(timestamp)
        else:
            trajectory_quarantined[player_id] += 1
            if identity_status == "ambiguous":
                trajectory_ambiguous[player_id] += 1
        for view_id, observation in (sample.get("view_observations") or {}).items():
            if not isinstance(observation, dict):
                continue
            track_id = observation.get("source_track_id")
            if isinstance(track_id, int):
                source_tracks[player_id][str(view_id)].add(track_id)
            if accepted and observation.get("view_status") == "available" and track_id is not None:
                detection_ticks[player_id].add(timestamp)
    display_diagnostics = display_diagnostics or {}
    diagnostics = list(display_diagnostics.get("rows") or [])
    reconnects: dict[str, int] = defaultdict(int)
    ambiguous: dict[str, int] = defaultdict(int)
    local_reassociation_violations: dict[str, int] = defaultdict(int)
    topology_transitions: dict[str, int] = defaultdict(int)
    topology_window_counts: dict[str, dict[tuple[Any, ...], int]] = defaultdict(dict)
    reassociation_events = [
        event for event in display_diagnostics.get("events", []) or []
        if isinstance(event, dict) and event.get("reason") == "reassociated"
    ]
    recovery_config = dict((runtime_diagnostics or {}).get("p1_online_recovery_config") or {})
    candidate_recovery_runtime = dict((runtime_diagnostics or {}).get("candidate_recovery") or {})
    association_counters = dict((runtime_diagnostics or {}).get("association_counters") or {})
    required_reassociation_frames = int(
        recovery_config.get("association_reassociation_frames") or 5
    )
    if reassociation_events:
        for event in reassociation_events:
            if int(event.get("evidence_count") or 0) < required_reassociation_frames:
                challenger_global_id = str(event.get("challenger_global_id") or "")
                player_id = global_to_player.get(challenger_global_id)
                if player_id in CANONICAL_PLAYERS:
                    local_reassociation_violations[player_id] += 1
    seen_reassociation_events: set[tuple[Any, ...]] = set()
    seen_topology_events: set[tuple[Any, ...]] = set()
    for row in diagnostics:
        player_id = str(row.get("player_id") or "")
        if player_id not in CANONICAL_PLAYERS:
            continue
        reason = " ".join(
            str(row.get(key) or "")
            for key in ("association_reason", "guidance_status", "pre_association_status")
        ).lower()
        reconnects[player_id] += int("recover" in reason or "reconnect" in reason)
        ambiguous[player_id] += int("ambiguous" in reason or bool(row.get("roster_conflict")))
        reassociation_reason = str(row.get("local_slot_reassociation_status") or "")
        if not reassociation_events and reassociation_reason == "reassociated":
            event_key = (
                row.get("canonical_tick"), row.get("view_id"), row.get("local_slot"), reassociation_reason
            )
            if event_key not in seen_reassociation_events:
                seen_reassociation_events.add(event_key)
                if int(row.get("reassociation_evidence_count") or 0) < required_reassociation_frames:
                    local_reassociation_violations[player_id] += 1
    # The event stream contains cumulative ``display_transition_count`` values
    # for the current debounce window. Count each actual state edge once;
    # summing the cumulative value would double-count the same transitions.
    for event in (display_diagnostics or {}).get("events", []) or []:
        if not isinstance(event, dict):
            continue
        player_id = str(event.get("player_id") or "")
        if player_id not in CANONICAL_PLAYERS:
            continue
        previous_state = event.get("previous_display_state")
        display_state = event.get("display_state")
        if not previous_state or previous_state == display_state:
            continue
        event_key = (
            event.get("timestamp_ms"), event.get("view_id"), player_id,
            previous_state, display_state,
        )
        if event_key not in seen_topology_events:
            seen_topology_events.add(event_key)
            topology_transitions[player_id] += 1
        if event.get("display_transition_count") is not None:
            window_key = (event.get("view_id"), event.get("display_window_start_ms"))
            topology_window_counts[player_id][window_key] = max(
                topology_window_counts[player_id].get(window_key, 0),
                int(event.get("display_transition_count") or 0),
            )
    # ``display_transition_count`` is cumulative within a short debounce
    # window. The quality gate is a window gate, so use the worst window for
    # each canonical player instead of summing every window's state edges.
    for player_id, windows in topology_window_counts.items():
        if windows:
            topology_transitions[player_id] = max(windows.values())
    appearance_diagnostics = dict((runtime_diagnostics or {}).get("appearance") or {})
    association_appearance = dict(appearance_diagnostics.get("association") or {})
    galleries_by_global = dict(association_appearance.get("galleries") or {})
    per_view_appearance = dict(appearance_diagnostics.get("per_view") or {})
    summaries: dict[str, PlayerIdentificationSummary] = {}
    attempted = len(ticks)
    for player_id in CANONICAL_PLAYERS:
        observed = sorted(set(timestamps[player_id]))
        gaps: list[float] = []
        if ticks:
            if has_processed_timeline:
                gaps.append(_longest_gap_on_processed_timeline(ticks, observed))
            elif observed:
                gaps.extend([observed[0] - ticks[0], ticks[-1] - observed[-1]])
                gaps.extend(b - a for a, b in zip(observed, observed[1:]))
            else:
                gaps.append(duration)
        history = {view: sorted(ids) for view, ids in source_tracks[player_id].items()}
        global_id = next((gid for gid, mapped in global_to_player.items() if mapped == player_id), None)
        player_galleries = dict(galleries_by_global.get(global_id) or {}) if global_id else {}
        template_updates = sum(int(item.get("template_updates") or 0) for item in player_galleries.values())
        template_freezes = sum(int(item.get("template_freezes") or 0) for item in player_galleries.values())
        descriptor_attempts = sum(int(item.get("attempts") or 0) for item in per_view_appearance.values())
        descriptor_available = sum(int(item.get("available") or 0) for item in per_view_appearance.values())
        summaries[player_id] = PlayerIdentificationSummary(
            player_id=player_id,
            detection_ticks=len(detection_ticks[player_id]),
            canonical_ticks=len(observed),
            detection_coverage=(len(detection_ticks[player_id]) / attempted) if attempted else 0.0,
            canonical_coverage=(len(observed) / attempted) if attempted else 0.0,
            longest_gap_seconds=max(gaps, default=0.0),
            source_track_history=history,
            source_track_count=sum(len(ids) for ids in history.values()),
            reconnect_count=reconnects[player_id],
            ambiguous_count=ambiguous[player_id] + trajectory_ambiguous[player_id],
            quarantined_count=trajectory_quarantined[player_id],
            accepted_count=len(observed),
            cross_side_count=cross_side_samples[player_id],
            local_slot_reassociation_violation_count=local_reassociation_violations[player_id],
            display_topology_transition_count=topology_transitions[player_id],
            appearance=AppearanceQualitySummary(
                descriptor_attempts=descriptor_attempts,
                descriptor_available=descriptor_available,
                template_updates=template_updates,
                template_freezes=template_freezes,
                template_age_ticks=max(
                    (int(item.get("template_age_ticks") or 0) for item in player_galleries.values()),
                    default=0,
                ),
                decision_contributions=int(association_appearance.get("decision_contributions") or 0),
                decision_supports=int(association_appearance.get("decision_supports") or 0),
                decision_conflicts=int(association_appearance.get("decision_conflicts") or 0),
                fallback_reason=(
                    f"non_discriminative_samples:{int(association_appearance.get('fallback_count') or 0)}"
                    if int(association_appearance.get("fallback_count") or 0) > 0
                    else None
                    if template_updates > 0
                    else "legacy_artifact_no_appearance_diagnostics"
                ),
            ),
        )
    raw_funnel = dict((runtime_diagnostics or {}).get("perception_funnel") or {})
    raw_per_view = dict(raw_funnel.get("per_view") or {})
    per_view_funnel: dict[str, dict[str, Any]] = {}
    for view_id in set(raw_per_view) | set(perception_track_ids):
        values = dict(raw_per_view.get(view_id) or {})
        per_view_funnel[str(view_id)] = {
            **values,
            "global_metric_eligible_sample_count": len(perception_sample_ticks.get(str(view_id), set())),
            "raw_detection_trace_available": "raw_detection_count" in values,
        }
    raw_by_end = dict(raw_funnel.get("per_canonical_end") or {})
    per_end_funnel = {
        end: {
            **dict(raw_by_end.get(end) or {}),
            "metric_eligible_sample_count": int(eligible_samples_by_end.get(end, 0)),
        }
        for end in ("end_a", "end_b", "unknown")
    }
    identity_slots: dict[str, dict[str, Any]] = {}
    if frozen_roster or audit_entries:
        for player_id in CANONICAL_PLAYERS:
            entry = audit_entries.get(player_id) or {}
            # 7.3：与 mapping_confirmed_by_player 共用同一判定，避免同一产物双口径。
            confirmed = audit_confirmed_by_player.get(player_id) is True
            identity_slots[player_id] = {
                "status": "confirmed" if confirmed else "unconfirmed",
                "reason": entry.get("reason") or (None if confirmed else "bootstrap_binding_no_simultaneous_observation"),
                "canonical_end": entry.get("canonical_end"),
                "global_player_id": entry.get("global_player_id") if confirmed else None,
                "tracklet_lineage_id": entry.get("tracklet_lineage_id") if confirmed else None,
                "anchor_timestamp_ms": entry.get("anchor_timestamp_ms"),
                "raw_detection_count": None,
                "local_track_count": None,
                "metric_eligible_sample_count": summaries[player_id].canonical_ticks,
                "conflicts_with_roster_json": player_id in mapping_conflict_with_audit,
            }
    artifact = FourPlayerIdentificationQuality(
        job_id=job_id,
        algorithm_version=algorithm_version,
        thresholds=thresholds or IdentificationThresholds(),
        attempted_ticks=attempted,
        duration_seconds=duration,
        confirmed_roster_count=(
            int(frozen_roster.get("confirmed_count") or 0)
            if "confirmed_count" in frozen_roster
            else int(roster.get("confirmed_player_count") or 0)
        ),
        players=summaries,
        candidate_recovery=CandidateRecoveryQuality(
            available="minimum_consecutive_ticks" in candidate_recovery_runtime,
            enabled=bool(candidate_recovery_runtime.get("enabled", False)),
            detail=(
                None
                if "minimum_consecutive_ticks" in candidate_recovery_runtime
                else "历史任务未保存 candidate recovery 诊断"
            ),
            minimum_consecutive_ticks=candidate_recovery_runtime.get("minimum_consecutive_ticks"),
            maximum_step_ft=candidate_recovery_runtime.get("maximum_step_ft"),
            unique_match_margin_ft=candidate_recovery_runtime.get("unique_match_margin_ft"),
            evidence_ttl_ticks=candidate_recovery_runtime.get("evidence_ttl_ticks"),
            pending_evidence_count=candidate_recovery_runtime.get("pending_evidence_count"),
            counters={
                key: int(value)
                for key, value in association_counters.items()
                if str(key).startswith("unmatched_recovery_")
                and isinstance(value, (int, float))
            },
        ),
        mapping_confirmation_available=mapping_confirmation_available,
        mapping_confirmed_by_player=mapping_confirmed_by_player,
        mapping_conflict_with_audit=mapping_conflict_with_audit,
        per_view_funnel=per_view_funnel,
        per_canonical_end_funnel=per_end_funnel,
        identity_slots=identity_slots,
        funnel=PipelineFunnelCounters(
            attempted_ticks=attempted,
            base_detection_ticks=sum(len(values) for values in perception_sample_ticks.values()),
            tracker_fragments=sum(len(values) for values in perception_track_ids.values()),
            local_slot_reassociation_violation_count=sum(local_reassociation_violations.values()),
            display_topology_transition_count=sum(topology_transitions.values()),
            bbox_footpoint_inconsistency_count=sum(
                1
                for event in display_diagnostics.get("events", []) or []
                if isinstance(event, dict)
                and event.get("projection_rejection_reason") == "bbox_footpoint_inconsistency"
            ),
        ),
        camera_profiles=dict(association_appearance.get("profiles") or {}),
    )
    return evaluate_quality(artifact)


def _canonical_end_for_y(value: Any) -> str:
    try:
        y = float(value)
    except (TypeError, ValueError):
        return "unknown"
    if not 0.0 <= y <= 44.0 or abs(y - 22.0) <= 1.5:
        return "unknown"
    return "end_a" if y < 22.0 else "end_b"


def _longest_gap_on_processed_timeline(ticks: list[float], observed: list[float]) -> float:
    """Measure absence only over ticks the joint run actually attempted.

    Selected rally windows can be separated by long unprocessed pauses. Those
    pauses must not count as tracking misses, while an all-player dropout at the
    tail of an analyzed window must still be included even when no trajectory
    sample exists at the final attempted ticks.
    """
    if not ticks:
        return 0.0
    deltas = [right - left for left, right in zip(ticks, ticks[1:]) if right > left]
    local_deltas = [delta for delta in deltas if delta <= 1.0]
    cadence = sorted(local_deltas or deltas)[len(local_deltas or deltas) // 2] if deltas else 0.0
    continuity_limit = max(0.5, cadence * 3.0)
    segments: list[list[float]] = []
    segment_start = 0
    for index in range(1, len(ticks)):
        if ticks[index] - ticks[index - 1] > continuity_limit:
            segments.append(ticks[segment_start:index])
            segment_start = index
    segments.append(ticks[segment_start:])

    match_tolerance = max(0.05, cadence * 0.51)
    longest = 0.0
    for segment in segments:
        if not segment:
            continue
        start, end = segment[0], segment[-1]
        matched: set[float] = set()
        for timestamp in observed:
            if timestamp < start - match_tolerance or timestamp > end + match_tolerance:
                continue
            insertion = bisect_left(segment, timestamp)
            candidates = [index for index in (insertion - 1, insertion) if 0 <= index < len(segment)]
            index = min(candidates, key=lambda candidate: abs(segment[candidate] - timestamp))
            if abs(segment[index] - timestamp) <= match_tolerance:
                matched.add(segment[index])
        if not matched:
            longest = max(longest, end - start)
            continue
        observed_ticks = sorted(matched)
        gaps = [observed_ticks[0] - start, end - observed_ticks[-1]]
        gaps.extend(right - left for left, right in zip(observed_ticks, observed_ticks[1:]))
        longest = max(longest, *gaps)
    return longest


def unavailable_quality(job_id: str, detail: str) -> FourPlayerIdentificationQuality:
    return FourPlayerIdentificationQuality(
        job_id=job_id,
        status="unavailable",
        detail=detail,
        algorithm_version="unknown",
    )
