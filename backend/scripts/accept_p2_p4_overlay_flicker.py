#!/usr/bin/env python3
"""Validate the P2/P4 7--13s regression window on a newly created Job.

This validator deliberately consumes published artifacts only. It never treats
refreshing the old ``job-43e7475fd8`` artifacts as a new analysis run.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


TARGETS = {"Player_2", "Player_4"}
QUARANTINE_REASONS = {
    "reassociation_ambiguous",
    "local_slot_conflict",
    "reassociation_margin_insufficient",
}


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _window(value: Any, start: float, end: float) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return start <= number <= end


def validate(artifact_root: Path, baseline_path: Path) -> dict[str, Any]:
    baseline = _read(baseline_path)
    overlay = _read(artifact_root / "fused_player_overlay.json")
    diagnostics = _read(artifact_root / "player_display_diagnostics.json")
    trajectory = _read(artifact_root / "fused_player_trajectory.json")
    roster_path = artifact_root / "roster.json"
    roster = _read(roster_path) if roster_path.exists() else {}

    start, end = (float(value) for value in baseline.get("window_seconds", [7.0, 13.0]))
    config = baseline.get("acceptance_config") or {}
    frames = [
        frame for frame in overlay.get("frames", []) or []
        if _window(frame.get("timestamp_seconds"), start, end)
    ]
    frame_players = {
        player_id: [
            player for frame in frames for player in frame.get("players", []) or []
            if player.get("player_id") == player_id
        ]
        for player_id in TARGETS
    }
    duplicate_ids = [
        (frame.get("frame_index"), player_id)
        for frame in frames
        for player_id in TARGETS
        if sum(
            player.get("player_id") == player_id
            for player in frame.get("players", []) or []
        ) > 1
    ]
    residual_violations = []
    rejected_with_bbox = []
    topology_violations = []
    for player_id, players in frame_players.items():
        for player in players:
            residual = player.get("bbox_footpoint_residual_px")
            if residual is not None and float(residual) > float(
                config.get("projected_bbox_footpoint_residual_px", 80.0)
            ):
                residual_violations.append((player_id, player.get("frame_index"), residual))
            if player.get("projection_rejection_reason") and player.get("bbox") is not None:
                rejected_with_bbox.append((player_id, player.get("projection_rejection_reason")))
            if int(player.get("display_transition_count") or 0) > int(
                config.get("max_display_topology_transitions", 12)
            ):
                topology_violations.append((player_id, player.get("display_transition_count")))

    expected_global_ids = dict(
        baseline.get("canonical_global_ids")
        or {player_id: f"global_player_{player_id.rsplit('_', 1)[-1]}" for player_id in TARGETS}
    )
    actual_global_ids = {
        str(item.get("player_id")): str(item.get("global_player_id"))
        for item in roster.get("players", []) or []
        if item.get("player_id") in TARGETS and item.get("global_player_id")
    }
    roster_identity_mismatches = [
        (player_id, expected_global_ids.get(player_id), actual_global_ids.get(player_id))
        for player_id in TARGETS
        if player_id in actual_global_ids
        and actual_global_ids.get(player_id) != expected_global_ids.get(player_id)
    ]
    diag_rows = [
        row for row in diagnostics.get("rows", []) or []
        if row.get("player_id") in TARGETS and _window(row.get("timestamp_ms", 0) / 1000.0, start, end)
    ]
    reassociation_events = [
        event for event in diagnostics.get("events", []) or []
        if isinstance(event, dict)
        and event.get("local_slot") in TARGETS
        and _window(event.get("timestamp_ms", 0) / 1000.0, start, end)
    ]
    required_reassociation_frames = int(config.get("association_reassociation_frames", 5))
    confirmed_reassociation_events = [
        event for event in reassociation_events
        if event.get("reason") == "reassociated"
    ]
    reassociation_violations = [
        event for event in confirmed_reassociation_events
        if int(event.get("evidence_count") or 0) < required_reassociation_frames
    ]
    quarantined_reassociation_events = [
        event for event in reassociation_events
        if event.get("reason") in QUARANTINE_REASONS
    ]
    trajectory_samples = [
        sample for sample in trajectory.get("samples", []) or []
        if _window(sample.get("timestamp_seconds"), start, end)
        and sample.get("global_player_id") in set(expected_global_ids.values())
    ]
    formal_ambiguous = [
        sample for sample in trajectory_samples
        if str(sample.get("identity_status") or "") in {"ambiguous", "unresolved"}
        and bool(sample.get("metric_eligible"))
    ]
    checks = {
        "new_job_id": overlay.get("job_id") != baseline.get("job_id"),
        "window_present": bool(frames),
        "canonical_identity_is_stable": not duplicate_ids and not roster_identity_mismatches,
        "unconfirmed_reassociation_zero": not reassociation_violations,
        "quarantined_samples_not_formal": not formal_ambiguous,
        "rejected_projection_has_no_bbox": not rejected_with_bbox,
        "bbox_footpoint_residual_within_config": not residual_violations,
        "display_topology_transition_within_config": not topology_violations,
    }
    return {
        "schema_version": "p2-p4-overlay-flicker-acceptance.v1",
        "job_id": overlay.get("job_id"),
        "baseline_job_id": baseline.get("job_id"),
        "window_seconds": [start, end],
        "verdict": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "counts": {
            "overlay_frames": len(frames),
            "p2_overlay_entities": len(frame_players["Player_2"]),
            "p4_overlay_entities": len(frame_players["Player_4"]),
            "diagnostic_rows": len(diag_rows),
            "reassociation_violations": len(reassociation_violations),
            "confirmed_reassociation_events": len(confirmed_reassociation_events),
            "quarantined_reassociation_events": len(quarantined_reassociation_events),
            "formal_ambiguous_samples": len(formal_ambiguous),
            "residual_violations": len(residual_violations),
            "rejected_projection_with_bbox": len(rejected_with_bbox),
        },
        "failures": {
            "duplicate_ids": duplicate_ids,
            "roster_identity_mismatches": roster_identity_mismatches,
            "reassociation_violations": reassociation_violations,
            "formal_ambiguous_samples": formal_ambiguous,
            "residual_violations": residual_violations,
            "rejected_projection_with_bbox": rejected_with_bbox,
            "topology_violations": topology_violations,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument(
        "--baseline",
        type=Path,
        default=Path("backend/fixtures/four_player_identification/p2-p4-overlay-flicker-job-43e7475fd8.json"),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = validate(args.artifact_root, args.baseline)
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if result["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
