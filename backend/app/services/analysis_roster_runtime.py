"""Validated, read-only frozen roster input for joint tracking."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

from app.schemas.rally_context import (
    AnalysisRosterSnapshotPayload,
    BootstrapBindingAuditEntry,
    BootstrapBindingAuditPayload,
    BootstrapBindingEvidence,
)


@dataclass(frozen=True)
class RosterAnchor:
    player_id: str
    team_id: str
    end: str | None
    view_id: str
    timestamp_ms: int
    bbox: tuple[float, float, float, float] | None
    canonical_xy: tuple[float, float] | None
    candidate_id: str | None
    bootstrap_run_id: str | None = None


@dataclass(frozen=True)
class RuntimeRoster:
    status: str
    reason: str | None
    roster_hash: str | None
    initial_team_a_end: str | None
    anchors: tuple[RosterAnchor, ...] = ()

    @property
    def available(self) -> bool:
        return self.status == "available" and self.reason is None

    @property
    def player_end_by_id(self) -> dict[str, str]:
        return {
            anchor.player_id: anchor.end
            for anchor in self.anchors
            if anchor.end is not None
        }


def validate_runtime_roster(
    snapshot: AnalysisRosterSnapshotPayload | None,
    *,
    expected_hash: str | None,
    expected_player_count: int = 4,
) -> RuntimeRoster:
    """Fail closed on stale or structurally ambiguous frozen roster input."""
    if snapshot is None:
        return RuntimeRoster("unavailable", "roster_snapshot_missing", None, None)
    try:
        actual_hash = snapshot.roster_hash
    except Exception:
        return RuntimeRoster("unavailable", "roster_snapshot_invalid", None, None)
    if not expected_hash:
        return RuntimeRoster("unavailable", "job_roster_hash_missing", actual_hash, snapshot.initial_team_a_end)
    if actual_hash != expected_hash:
        return RuntimeRoster("unavailable", "roster_snapshot_hash_mismatch", actual_hash, snapshot.initial_team_a_end)
    if snapshot.status != "available":
        return RuntimeRoster(
            "unavailable",
            snapshot.unavailable_reason or "roster_snapshot_not_available",
            actual_hash,
            snapshot.initial_team_a_end,
        )
    if expected_player_count == 4:
        expected_ids = {f"Player_{index}" for index in range(1, 5)}
        ids = [entry.canonical_player_id for entry in snapshot.entries]
        if len(ids) != 4 or set(ids) != expected_ids or len(set(ids)) != 4:
            return RuntimeRoster("unavailable", "roster_slots_invalid", actual_hash, snapshot.initial_team_a_end)
        team_by_player = {entry.canonical_player_id: entry.team_id for entry in snapshot.entries}
        if any(team_by_player.get(f"Player_{index}") != "A" for index in (1, 2)) or any(
            team_by_player.get(f"Player_{index}") != "B" for index in (3, 4)
        ):
            return RuntimeRoster("unavailable", "roster_team_slots_invalid", actual_hash, snapshot.initial_team_a_end)
        if snapshot.initial_team_a_end not in {"end_a", "end_b"}:
            return RuntimeRoster("unavailable", "initial_team_a_end_unavailable", actual_hash, None)
    anchors: list[RosterAnchor] = []
    for entry in snapshot.entries:
        if not entry.source_view_id or int(entry.anchor_timestamp_ms or 0) <= 0:
            return RuntimeRoster("unavailable", "roster_anchor_missing", actual_hash, snapshot.initial_team_a_end)
        bbox: tuple[float, float, float, float] | None = None
        if entry.anchor_bbox is not None:
            values = tuple(float(value) for value in entry.anchor_bbox)
            if len(values) != 4 or not all(isfinite(value) for value in values):
                return RuntimeRoster("unavailable", "roster_anchor_bbox_invalid", actual_hash, snapshot.initial_team_a_end)
            if values[2] <= values[0] or values[3] <= values[1]:
                return RuntimeRoster("unavailable", "roster_anchor_bbox_invalid", actual_hash, snapshot.initial_team_a_end)
            bbox = values  # type: ignore[assignment]
        xy: tuple[float, float] | None = None
        if entry.anchor_court_xy is not None:
            values = tuple(float(value) for value in entry.anchor_court_xy)
            if len(values) != 2 or not all(isfinite(value) for value in values):
                return RuntimeRoster("unavailable", "roster_anchor_court_xy_invalid", actual_hash, snapshot.initial_team_a_end)
            xy = values  # type: ignore[assignment]
        if bbox is None and xy is None:
            return RuntimeRoster("unavailable", "roster_anchor_evidence_missing", actual_hash, snapshot.initial_team_a_end)
        end = None
        if expected_player_count == 4 and snapshot.initial_team_a_end:
            team_a_end = snapshot.initial_team_a_end
            end = team_a_end if entry.team_id == "A" else ("end_b" if team_a_end == "end_a" else "end_a")
        anchors.append(
            RosterAnchor(
                player_id=entry.canonical_player_id,
                team_id=entry.team_id,
                end=end,
                view_id=entry.source_view_id,
                timestamp_ms=int(entry.anchor_timestamp_ms),
                bbox=bbox,
                canonical_xy=xy,
                candidate_id=entry.candidate_id,
                bootstrap_run_id=entry.bootstrap_run_id,
            )
        )
    return RuntimeRoster("available", None, actual_hash, snapshot.initial_team_a_end, tuple(anchors))


def load_runtime_roster(db: Any, job_id: str, expected_hash: str | None, *, expected_player_count: int = 4) -> RuntimeRoster:
    from app.services.analysis_rally_context_service import roster_payload_for_job

    try:
        snapshot = roster_payload_for_job(db, job_id)
    except Exception:
        snapshot = None
    return validate_runtime_roster(
        snapshot,
        expected_hash=expected_hash,
        expected_player_count=expected_player_count,
    )


def _bbox_iou(left: tuple[float, ...] | None, right: tuple[float, ...] | None) -> float | None:
    if left is None or right is None:
        return None
    x1, y1 = max(left[0], right[0]), max(left[1], right[1])
    x2, y2 = min(left[2], right[2]), min(left[3], right[3])
    if x2 <= x1 or y2 <= y1:
        return 0.0
    intersection = (x2 - x1) * (y2 - y1)
    area_left = (left[2] - left[0]) * (left[3] - left[1])
    area_right = (right[2] - right[0]) * (right[3] - right[1])
    return intersection / max(1e-9, area_left + area_right - intersection)


def match_anchor_observations(
    anchors: tuple[RosterAnchor, ...],
    observations: list[Any],
    *,
    time_tolerance_ms: float = 400.0,
    minimum_bbox_iou: float = 0.30,
    maximum_court_distance_ft: float = 3.0,
    ambiguity_margin: float = 0.12,
) -> tuple[
    list[tuple[RosterAnchor, Any, dict[str, object]]],
    dict[str, str],
    dict[str, dict[str, object]],
]:
    """Match simultaneous tracker observations to anchors one-to-one.

    A match requires same-view time evidence plus either bbox overlap or a
    calibrated court-position match. Player numbers and track ordering never
    contribute to the score.

    7.1：第三个返回值`competition_evidence` 给出落败槽位的竞争证据（胜者、双方
    证据、裁决规则）。同一观测被多个锚点命中时按证据强度保留胜者，落败者返回
    `bootstrap_binding_tracklet_competes_for_slots`，而不是全部判为冲突失败。
    """
    choices: dict[str, list[tuple[float, Any, dict[str, object]]]] = {}
    reasons: dict[str, str] = {}
    for anchor in anchors:
        candidate_rows: list[tuple[float, Any, dict[str, object]]] = []
        saw_simultaneous_observation = False
        for observation in observations:
            if getattr(observation, "view_id", None) != anchor.view_id:
                continue
            source_ms = getattr(observation, "source_timestamp_ms", None)
            if source_ms is None:
                source_ms = getattr(observation, "take_timestamp_ms", None)
            if source_ms is None:
                continue
            delta_ms = abs(float(source_ms) - anchor.timestamp_ms)
            if delta_ms > time_tolerance_ms:
                continue
            saw_simultaneous_observation = True
            obs_bbox_raw = getattr(observation, "bbox", None)
            obs_bbox = tuple(float(value) for value in obs_bbox_raw) if obs_bbox_raw and len(obs_bbox_raw) == 4 else None
            bbox_iou = _bbox_iou(anchor.bbox, obs_bbox)
            obs_xy = (
                getattr(observation, "canonical_x_ft", None),
                getattr(observation, "canonical_y_ft", None),
            )
            court_distance = None
            if anchor.canonical_xy is not None and all(value is not None for value in obs_xy):
                court_distance = ((anchor.canonical_xy[0] - float(obs_xy[0])) ** 2 + (anchor.canonical_xy[1] - float(obs_xy[1])) ** 2) ** 0.5
            bbox_match = bbox_iou is not None and bbox_iou >= minimum_bbox_iou
            court_match = court_distance is not None and court_distance <= maximum_court_distance_ft
            if not bbox_match and not court_match:
                continue
            time_score = max(0.0, 1.0 - delta_ms / max(1.0, time_tolerance_ms))
            geometry_scores = []
            if bbox_match and bbox_iou is not None:
                geometry_scores.append(bbox_iou)
            if court_match and court_distance is not None:
                geometry_scores.append(max(0.0, 1.0 - court_distance / maximum_court_distance_ft))
            score = 0.55 * time_score + 0.45 * max(geometry_scores)
            evidence: dict[str, object] = {
                "view_id": anchor.view_id,
                "time_delta_ms": int(round(delta_ms)),
                "bbox_iou": round(bbox_iou, 4) if bbox_iou is not None else None,
                "court_distance_ft": round(court_distance, 4) if court_distance is not None else None,
            }
            candidate_rows.append((score, observation, evidence))
        choices[anchor.player_id] = sorted(candidate_rows, key=lambda row: row[0], reverse=True)
        if not candidate_rows:
            reasons[anchor.player_id] = (
                "bootstrap_binding_insufficient_evidence"
                if saw_simultaneous_observation
                else "bootstrap_binding_no_simultaneous_observation"
            )

    proposed: list[tuple[RosterAnchor, Any, dict[str, object], float]] = []
    anchor_by_id = {anchor.player_id: anchor for anchor in anchors}
    for player_id, rows in choices.items():
        if not rows:
            continue
        if len(rows) > 1 and rows[0][0] - rows[1][0] < ambiguity_margin:
            reasons[player_id] = "bootstrap_binding_ambiguous_match"
            continue
        proposed.append((anchor_by_id[player_id], rows[0][1], rows[0][2], rows[0][0]))

    owners: dict[int, list[str]] = {}
    for anchor, observation, _evidence, _score in proposed:
        owners.setdefault(id(observation), []).append(anchor.player_id)
    conflicted_players = {
        player for players in owners.values() if len(players) > 1 for player in players
    }

    # 7.1：同一观测被多个锚点命中时按证据强度裁决，而不是让所有竞争者一起失败。
    # 此前 `bootstrap_binding_conflicting_slots` 会把 P3/P4 同时判失败，先到者
    # 反而独占tracklet；实测 job-faf852782a 的 P4（IoU 0.8575 / 0.6614ft）因此
    # 输给了先到的 P3。强度依次比较 court 距离 -> bbox IoU -> 时间差，
    # 三者都由已有 evidence 字段提供，不引入新打分模型。
    def _evidence_strength(evidence: dict[str, object]) -> tuple[float, float, float]:
        court = evidence.get("court_distance_ft")
        iou = evidence.get("bbox_iou")
        delta = evidence.get("time_delta_ms")
        return (
            float(court) if isinstance(court, (int, float)) else float("inf"),
            -float(iou) if isinstance(iou, (int, float)) else float("inf"),
            float(delta) if isinstance(delta, (int, float)) else float("inf"),
        )

    proposed_by_player = {
        anchor.player_id: evidence for anchor, _observation, evidence, _score in proposed
    }
    competition_evidence: dict[str, dict[str, object]] = {}
    winners: set[str] = set()
    for players in owners.values():
        if len(players) < 2:
            continue
        ranked = sorted(
            players,
            key=lambda pid: _evidence_strength(proposed_by_player.get(pid, {})),
        )
        winner = ranked[0]
        winners.add(winner)
        for loser in ranked[1:]:
            competition_evidence[loser] = {
                "winner_player_id": winner,
                "winner_evidence": proposed_by_player.get(winner),
                "loser_evidence": proposed_by_player.get(loser),
                "resolution_rule": "court_distance_then_bbox_iou_then_time_delta",
            }
            reasons[loser] = "bootstrap_binding_tracklet_competes_for_slots"

    matches = [
        (anchor, observation, evidence)
        for anchor, observation, evidence, _score in proposed
        if anchor.player_id not in conflicted_players or anchor.player_id in winners
    ]
    return matches, reasons, competition_evidence


def build_bootstrap_binding_audit_payload(
    *,
    job_id: str,
    roster_hash: str | None,
    audit: dict[str, Any] | None,
    unavailable_reason: str | None = None,
) -> BootstrapBindingAuditPayload:
    """Convert joint-run anchor conclusions to the durable public audit contract."""
    raw_entries = audit.get("entries") if isinstance(audit, dict) else None
    entries: list[BootstrapBindingAuditEntry] = []
    for index, raw in enumerate(raw_entries if isinstance(raw_entries, list) else []):
        if not isinstance(raw, dict):
            continue
        player_id = str(raw.get("canonical_player_id") or "")
        if player_id not in {f"Player_{number}" for number in range(1, 5)}:
            continue
        global_player_id = raw.get("global_player_id")
        confirmed = bool(
            raw.get("confirmed") is True
            and raw.get("formal_canonical_player_id") == player_id
            and isinstance(global_player_id, str)
            and global_player_id
        )
        raw_evidence = raw.get("evidence") if isinstance(raw.get("evidence"), dict) else {}
        evidence = BootstrapBindingEvidence(
            view_id=raw_evidence.get("view_id") or raw.get("source_view_id"),
            time_delta_ms=_optional_int(raw_evidence.get("time_delta_ms")),
            bbox_iou=_optional_float(raw_evidence.get("bbox_iou")),
            court_distance_ft=_optional_float(raw_evidence.get("court_distance_ft")),
            multiview_corroborated=(
                bool(raw_evidence["multiview_corroborated"])
                if raw_evidence.get("multiview_corroborated") is not None
                else None
            ),
            competing_formal_players=_optional_int(raw_evidence.get("competing_formal_players")) or 0,
            competing_slots=_optional_int(raw_evidence.get("competing_slots")) or 0,
            track_id=_optional_int(raw_evidence.get("track_id")),
            tracklet_lineage_id=(
                str(raw_evidence["tracklet_lineage_id"])
                if raw_evidence.get("tracklet_lineage_id") is not None else None
            ),
            local_identity_epoch=_optional_int(raw_evidence.get("local_identity_epoch")),
            local_identity_reason=(
                str(raw_evidence["local_identity_reason"])
                if raw_evidence.get("local_identity_reason") is not None else None
            ),
            tracking_status=(
                str(raw_evidence["tracking_status"])
                if raw_evidence.get("tracking_status") is not None else None
            ),
            global_player_id=(
                str(raw_evidence["global_player_id"])
                if raw_evidence.get("global_player_id") is not None else None
            ),
        )
        entries.append(
            BootstrapBindingAuditEntry(
                canonical_player_id=player_id,
                slot_index=_optional_int(raw.get("slot_index")) if raw.get("slot_index") is not None else index,
                candidate_id=raw.get("candidate_id"),
                bootstrap_run_id=raw.get("bootstrap_run_id"),
                source_view_id=raw.get("source_view_id"),
                anchor_timestamp_ms=_optional_int(raw.get("anchor_timestamp_ms")) or 0,
                anchor_bbox=raw.get("anchor_bbox"),
                anchor_court_xy=raw.get("anchor_court_xy"),
                formal_canonical_player_id=player_id if confirmed else None,
                global_player_id=str(global_player_id) if confirmed else None,
                tracklet_lineage_id=(str(raw["tracklet_lineage_id"]) if confirmed and raw.get("tracklet_lineage_id") else None),
                local_identity_epoch=(
                    _optional_int(raw.get("local_identity_epoch"))
                    if confirmed and raw.get("local_identity_epoch") is not None else None
                ),
                method=(
                    str(raw.get("method"))
                    if confirmed and raw.get("method") in {"anchor_simultaneous_match", "anchor_simultaneous_multiview"}
                    else "unavailable"
                ),
                confidence=_optional_float(raw.get("confidence")),
                confirmed=confirmed,
                reason=raw.get("reason") or (None if confirmed else "bootstrap_binding_no_simultaneous_observation"),
                evidence=evidence,
            )
        )
    present = {entry.canonical_player_id for entry in entries}
    fallback_reason = unavailable_reason or (
        str(audit.get("unavailable_reason") or "bootstrap_binding_runtime_unavailable")
        if isinstance(audit, dict) else "bootstrap_binding_runtime_unavailable"
    )
    for index in range(4):
        player_id = f"Player_{index + 1}"
        if player_id in present:
            continue
        entries.append(
            BootstrapBindingAuditEntry(
                canonical_player_id=player_id,
                slot_index=index,
                method="unavailable",
                confirmed=False,
                reason=fallback_reason,
            )
        )
    entries.sort(key=lambda entry: entry.canonical_player_id)
    confirmed_count = sum(entry.confirmed for entry in entries)
    status = "available" if entries and confirmed_count == 4 else "partial" if confirmed_count else "unavailable"
    reason = None if status == "available" else unavailable_reason or (
        str(audit.get("unavailable_reason") or "bootstrap_binding_partial") if isinstance(audit, dict)
        else "bootstrap_binding_runtime_unavailable"
    )
    return BootstrapBindingAuditPayload(
        job_id=job_id,
        roster_hash=roster_hash or "unavailable",
        status=status,
        unavailable_reason=reason,
        entries=entries,
    )


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    try:
        result = float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    return result if result is None or isfinite(result) else None
