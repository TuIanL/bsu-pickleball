"""语义回合边界校准、证据账本和可重放评估。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping, Sequence

from app.vision.pickleball_game_analysis.ball_semantic_search_policy import (
    BallSearchDecision,
    BallSemanticPolicyConfig,
    MatchSemanticSnapshot,
    SemanticAuthority,
    SemanticPhase,
    SemanticTimelineProvider,
)


SEMANTIC_BOUNDARY_EVAL_SCHEMA_VERSION = "ball_semantic_boundary_eval.v1"


class SemanticEvidenceSource(StrEnum):
    AUTHORITATIVE = "authoritative"
    OBSERVED = "observed"
    ALGORITHMIC = "algorithmic"
    NONE = "none"


def _jsonable(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _stable_id(timestamp_ms: float, kind: str, source: str, payload: Any, provenance: Any) -> str:
    body = json.dumps(
        {
            "timestamp_ms": round(float(timestamp_ms), 3),
            "kind": kind,
            "source": source,
            "payload": _jsonable(payload),
            "provenance": _jsonable(provenance),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"evidence-{hashlib.sha1(body.encode('utf-8')).hexdigest()[:16]}"


@dataclass(frozen=True)
class SemanticEvidenceRecord:
    """一条不可变、可回放的语义证据。"""

    evidence_id: str
    timestamp_ms: float
    kind: str
    source: SemanticEvidenceSource
    authority: SemanticAuthority
    confidence: float | None = None
    fresh_until_ms: float | None = None
    payload_summary: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)

    def is_stale(self, timestamp_ms: float) -> bool:
        return self.fresh_until_ms is not None and float(timestamp_ms) > self.fresh_until_ms

    def to_dict(self, *, timestamp_ms: float | None = None) -> dict[str, Any]:
        stale = self.is_stale(timestamp_ms) if timestamp_ms is not None else False
        return {
            "evidence_id": self.evidence_id,
            "timestamp_ms": self.timestamp_ms,
            "kind": self.kind,
            "source": self.source.value,
            "authority": self.authority.value,
            "confidence": self.confidence,
            "fresh_until_ms": self.fresh_until_ms,
            "payload_summary": _jsonable(self.payload_summary),
            "provenance": _jsonable(self.provenance),
            "stale": stale,
        }


@dataclass
class SemanticEvidenceLedger:
    """按 canonical tick 保存 evidence，不随状态聚合而丢失来源。"""

    records: list[SemanticEvidenceRecord] = field(default_factory=list)

    def add_tick(
        self,
        timestamp_ms: float,
        evidence: Mapping[str, Any] | None,
        *,
        authority: SemanticAuthority = SemanticAuthority.NONE,
        freshness_seconds: float = 0.5,
    ) -> tuple[SemanticEvidenceRecord, ...]:
        evidence_map = dict(evidence or {})
        created: list[SemanticEvidenceRecord] = []
        explicit = evidence_map.get("semantic_evidence_records")
        if isinstance(explicit, Sequence) and not isinstance(explicit, (str, bytes)):
            for item in explicit:
                if not isinstance(item, Mapping):
                    continue
                created.append(self._record_from_mapping(timestamp_ms, item, authority, freshness_seconds))

        known = {
            "timeline_event_type": "timeline",
            "timeline_event_ids": "timeline",
            "player_motion_pixels": "player_activity",
            "player_observation_count": "player_activity",
            "global_player_count": "player_activity",
            "player_context_ready": "player_activity",
            "serve_candidate_confidence": "serve_detector",
            "serve_armed": "serve_detector",
            "serve_candidate_id": "serve_detector",
            "ball_motion_pixels": "ball_motion",
            "valid_ball_motion": "ball_motion",
            "ball_continuity": "ball_continuity",
            "rally_active": "rally_activity",
            "rally_confidence": "rally_activity",
            "rally_end_evidence_count": "rally_end_signal",
            "rally_end_confirmed": "rally_end_signal",
            "ball_visibility": "ball_visibility",
            "court_region": "court_context",
            "ball_in_court": "court_context",
        }
        explicit_keys = {
            str(item.get("key") or item.get("kind"))
            for item in explicit
            if isinstance(item, Mapping) and (item.get("key") is not None or item.get("kind") is not None)
        } if isinstance(explicit, Sequence) and not isinstance(explicit, (str, bytes)) else set()
        explicit_kinds = {
            str(item.get("kind"))
            for item in explicit
            if isinstance(item, Mapping) and item.get("kind") is not None
        } if isinstance(explicit, Sequence) and not isinstance(explicit, (str, bytes)) else set()
        for key, kind in known.items():
            if key not in evidence_map or key in explicit_keys or kind in explicit_kinds:
                continue
            value = evidence_map[key]
            source = self._source_for(kind, evidence_map, authority)
            provenance = self._provenance_for(evidence_map, kind)
            created.append(
                self._record(
                    timestamp_ms,
                    kind,
                    source,
                    authority,
                    value,
                    provenance,
                    freshness_seconds,
                )
            )
        self.records.extend(created)
        return tuple(created)

    def _record_from_mapping(
        self,
        timestamp_ms: float,
        item: Mapping[str, Any],
        authority: SemanticAuthority,
        freshness_seconds: float,
    ) -> SemanticEvidenceRecord:
        kind = str(item.get("kind") or item.get("key") or "custom")
        source_raw = str(item.get("source") or SemanticEvidenceSource.OBSERVED.value)
        try:
            source = SemanticEvidenceSource(source_raw)
        except ValueError:
            source = SemanticEvidenceSource.OBSERVED
        record_authority = item.get("authority", authority)
        try:
            record_authority = SemanticAuthority(str(getattr(record_authority, "value", record_authority)))
        except ValueError:
            record_authority = authority
        payload = item.get("payload_summary", item.get("value", item.get("payload", {})))
        provenance = dict(item.get("provenance") or {})
        return self._record(
            timestamp_ms,
            kind,
            source,
            record_authority,
            payload,
            provenance,
            freshness_seconds,
            evidence_id=str(item.get("evidence_id") or "") or None,
            confidence=item.get("confidence"),
            fresh_until_ms=item.get("fresh_until_ms"),
        )

    @staticmethod
    def _source_for(kind: str, evidence: Mapping[str, Any], authority: SemanticAuthority) -> SemanticEvidenceSource:
        if authority in {SemanticAuthority.MANUAL, SemanticAuthority.CORRECTED} and kind == "timeline":
            return SemanticEvidenceSource.AUTHORITATIVE
        if authority == SemanticAuthority.ALGORITHM and kind == "timeline":
            return SemanticEvidenceSource.ALGORITHMIC
        if kind in {"serve_detector", "rally_activity", "rally_end_signal"}:
            return SemanticEvidenceSource.ALGORITHMIC
        if kind in {"player_activity", "ball_motion", "ball_continuity", "ball_visibility", "court_context"}:
            return SemanticEvidenceSource.OBSERVED
        return SemanticEvidenceSource.NONE

    @staticmethod
    def _provenance_for(evidence: Mapping[str, Any], kind: str) -> dict[str, Any]:
        explicit = evidence.get(f"{kind}_provenance")
        if isinstance(explicit, Mapping):
            return dict(explicit)
        origin = evidence.get("evidence_provenance") or evidence.get("provenance")
        if isinstance(origin, Mapping):
            return {"origin": origin.get("origin", "runtime"), "detail": dict(origin)}
        if isinstance(origin, str):
            return {"origin": origin}
        return {"origin": "runtime"}

    @staticmethod
    def _record(
        timestamp_ms: float,
        kind: str,
        source: SemanticEvidenceSource,
        authority: SemanticAuthority,
        payload: Any,
        provenance: Mapping[str, Any],
        freshness_seconds: float,
        *,
        evidence_id: str | None = None,
        confidence: Any = None,
        fresh_until_ms: Any = None,
    ) -> SemanticEvidenceRecord:
        try:
            normalized_confidence = max(0.0, min(1.0, float(confidence))) if confidence is not None else None
        except (TypeError, ValueError):
            normalized_confidence = None
        if normalized_confidence is None and isinstance(payload, (int, float)):
            if 0.0 <= float(payload) <= 1.0 and ("confidence" in kind or kind in {"serve_detector", "rally_activity"}):
                normalized_confidence = float(payload)
        try:
            expiry = float(fresh_until_ms) if fresh_until_ms is not None else float(timestamp_ms) + max(0.0, freshness_seconds) * 1000.0
        except (TypeError, ValueError):
            expiry = float(timestamp_ms) + max(0.0, freshness_seconds) * 1000.0
        payload_summary = payload if isinstance(payload, Mapping) else {"value": _jsonable(payload)}
        provenance_dict = dict(provenance)
        return SemanticEvidenceRecord(
            evidence_id=evidence_id or _stable_id(timestamp_ms, kind, source.value, payload_summary, provenance_dict),
            timestamp_ms=float(timestamp_ms),
            kind=kind,
            source=source,
            authority=authority,
            confidence=normalized_confidence,
            fresh_until_ms=expiry,
            payload_summary=dict(payload_summary),
            provenance=provenance_dict,
        )

    def ids_for(self, timestamp_ms: float) -> tuple[str, ...]:
        return tuple(record.evidence_id for record in self.records if record.timestamp_ms == float(timestamp_ms))

    def to_list(self) -> list[dict[str, Any]]:
        return [record.to_dict() for record in self.records]


def _boundary_events(
    snapshots: Sequence[MatchSemanticSnapshot],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for snapshot in snapshots:
        status = getattr(snapshot, "boundary_status", "none")
        if status not in {"confirmed_start", "confirmed_end"}:
            continue
        events.append(
            {
                "kind": "start" if status == "confirmed_start" else "end",
                "timestamp_ms": float(snapshot.take_timestamp_ms),
                "status": status,
                "action": snapshot.boundary_action.value,
                "action_id": snapshot.boundary_action_id,
                "evidence_ids": list(getattr(snapshot, "evidence_ids", ())),
            }
        )
    return events


def _reference_events(reference_boundaries: Sequence[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in reference_boundaries or ():
        try:
            timestamp = float(item.get("timestamp_ms", item.get("time_ms", 0)))
        except (TypeError, ValueError):
            continue
        kind = str(item.get("kind", item.get("type", ""))).lower()
        if kind in {"rally_start", "start", "confirmed_start"}:
            kind = "start"
        elif kind in {"rally_end", "end", "confirmed_end"}:
            kind = "end"
        else:
            continue
        result.append({"kind": kind, "timestamp_ms": timestamp, "id": item.get("id")})
    return sorted(result, key=lambda item: (item["timestamp_ms"], item["kind"]))


def compute_boundary_evaluation_metrics(
    snapshots: Sequence[MatchSemanticSnapshot],
    decisions: Sequence[BallSearchDecision],
    *,
    reference_boundaries: Sequence[Mapping[str, Any]] | None = None,
    tolerance_ms: float = 250.0,
) -> dict[str, Any]:
    """计算不依赖模型权重的边界质量指标。"""

    predicted = _boundary_events(snapshots)
    reference = _reference_events(reference_boundaries)
    matched_predicted: set[int] = set()
    matched_reference: set[int] = set()
    latencies: list[float] = []
    for ref_index, ref in enumerate(reference):
        candidates = [
            (index, item)
            for index, item in enumerate(predicted)
            if index not in matched_predicted
            and item["kind"] == ref["kind"]
            and abs(item["timestamp_ms"] - ref["timestamp_ms"]) <= tolerance_ms
        ]
        if not candidates:
            continue
        pred_index, item = min(candidates, key=lambda pair: abs(pair[1]["timestamp_ms"] - ref["timestamp_ms"]))
        matched_predicted.add(pred_index)
        matched_reference.add(ref_index)
        latencies.append(item["timestamp_ms"] - ref["timestamp_ms"])

    predicted_count = len(predicted)
    reference_count = len(reference)
    true_positive = len(matched_predicted)
    false_positive = max(0, predicted_count - true_positive)
    false_negative = max(0, reference_count - len(matched_reference))
    non_authoritative_suppression = sum(
        1
        for decision in decisions
        if not decision.formal_publish_allowed
        and decision.authority not in {SemanticAuthority.MANUAL, SemanticAuthority.CORRECTED}
    )
    return {
        "tolerance_ms": float(tolerance_ms),
        "predicted_boundary_count": predicted_count,
        "reference_boundary_count": reference_count,
        "true_positive_count": true_positive,
        "false_positive_count": false_positive,
        "false_negative_count": false_negative,
        "boundary_precision": true_positive / predicted_count if predicted_count else None,
        "boundary_recall": true_positive / reference_count if reference_count else None,
        "confirmation_latency_ms": sum(latencies) / len(latencies) if latencies else None,
        "latencies_ms": latencies,
        "algorithmic_suppression_tick_count": non_authoritative_suppression,
        "false_suppression_count": sum(
            1
            for decision in decisions
            if not decision.formal_publish_allowed
            and not decision.hard_gate_active
            and decision.authority not in {SemanticAuthority.MANUAL, SemanticAuthority.CORRECTED}
        ),
        "cross_segment_contamination_count": sum(
            int(decision.diagnostics.get("cross_segment_contamination_count", 0) or 0)
            for decision in decisions
        ),
        "reference_status": "available" if reference else "not_provided",
    }


def build_semantic_boundary_evaluation_payload(
    *,
    job_id: str,
    take_id: str | None,
    snapshots: Sequence[MatchSemanticSnapshot],
    decisions: Sequence[BallSearchDecision],
    evidence_ledger: Sequence[Mapping[str, Any]] | None = None,
    diagnostics: Mapping[str, Any] | None = None,
    reference_boundaries: Sequence[Mapping[str, Any]] | None = None,
    frame_stride: int | None = None,
    timestamp_provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    diagnostics_map = dict(diagnostics or {})
    return {
        "schema_version": SEMANTIC_BOUNDARY_EVAL_SCHEMA_VERSION,
        "artifact_kind": "ball_semantic_boundary_eval",
        "job_id": job_id,
        "capture_take_id": take_id,
        "policy_version": diagnostics_map.get("policy_version"),
        "rollout": {
            "mode": diagnostics_map.get("policy_mode", "shadow"),
            "rollout_id": diagnostics_map.get("rollout_id"),
            "enabled": bool(diagnostics_map.get("rollout_enabled", False)),
        },
        "source": {
            "frame_stride": frame_stride,
            "timestamp_provenance": dict(timestamp_provenance or {}),
        },
        "evidence_ledger": list(evidence_ledger or diagnostics_map.get("evidence_ledger", ())),
        "ticks": [
            {
                "timestamp_ms": snapshot.take_timestamp_ms,
                "snapshot": snapshot.to_dict(),
                    "decision": decisions[index].to_dict() if index < len(decisions) else None,
            }
            for index, snapshot in enumerate(snapshots)
        ],
        "boundary_events": _boundary_events(snapshots),
        "reference_boundaries": _reference_events(reference_boundaries),
        "metrics": compute_boundary_evaluation_metrics(
            snapshots,
            decisions,
            reference_boundaries=reference_boundaries,
        ),
        "diagnostics": diagnostics_map,
    }


def replay_semantic_boundary_cases(
    cases: Sequence[Mapping[str, Any]],
    *,
    config: BallSemanticPolicyConfig | None = None,
) -> list[dict[str, Any]]:
    """按 fixture 的事件/探针重放 phase 与 policy decision。"""

    from app.vision.pickleball_game_analysis.ball_semantic_search_policy import BallSearchPolicy

    active_config = config or BallSemanticPolicyConfig()
    results: list[dict[str, Any]] = []
    for case in cases:
        provider = SemanticTimelineProvider.from_events(case.get("events", ()), config=active_config)
        policy = BallSearchPolicy(active_config)
        snapshots: list[MatchSemanticSnapshot] = []
        decisions: list[BallSearchDecision] = []
        for probe in case.get("probes", ()):
            snapshot = provider.snapshot(
                float(probe.get("timestamp_ms", 0)),
                evidence=probe.get("evidence"),
            )
            decision = policy.evaluate(snapshot, raw_candidate_count=int(probe.get("raw_candidate_count", 0) or 0))
            snapshots.append(snapshot)
            decisions.append(decision)
        results.append(
            {
                "id": case.get("id"),
                "snapshots": [snapshot.to_dict() for snapshot in snapshots],
                "decisions": [decision.to_dict() for decision in decisions],
                "metrics": compute_boundary_evaluation_metrics(
                    snapshots,
                    decisions,
                    reference_boundaries=case.get("reference_boundaries"),
                ),
                "evidence_ledger": provider.evidence_ledger.to_list(),
            }
        )
    return results


__all__ = [
    "SEMANTIC_BOUNDARY_EVAL_SCHEMA_VERSION",
    "SemanticEvidenceLedger",
    "SemanticEvidenceRecord",
    "SemanticEvidenceSource",
    "build_semantic_boundary_evaluation_payload",
    "compute_boundary_evaluation_metrics",
    "replay_semantic_boundary_cases",
]
