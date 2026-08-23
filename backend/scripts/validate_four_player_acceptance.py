#!/usr/bin/env python3
"""Validate a completed real four-player Job against baseline and fixed-time evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.vision.player_tracking_engine.four_player_quality import (
    FourPlayerIdentificationQuality,
    build_quality_from_joint_artifacts,
    compare_quality,
    evaluate_quality,
)


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _nearest_frame(overlay: dict[str, Any], timestamp_s: float) -> dict[str, Any] | None:
    frames = list(overlay.get("frames") or [])
    return min(frames, key=lambda frame: abs(float(frame.get("timestamp_seconds") or 0.0) - timestamp_s), default=None)


def validate(root: Path, baseline_path: Path) -> dict[str, Any]:
    published_quality = FourPlayerIdentificationQuality.model_validate(
        _read(root / "four_player_identification_quality.json")
    )
    # Rebuild derived coverage from authoritative samples so the runner uses
    # the current accepted/quarantine contract even for a completed Job whose
    # stored quality summary predates a validator fix.
    quality = build_quality_from_joint_artifacts(
        job_id=published_quality.job_id,
        algorithm_version=published_quality.algorithm_version,
        thresholds=published_quality.thresholds,
        trajectory=_read(root / "fused_player_trajectory.json"),
        roster=_read(root / "roster.json"),
        display_diagnostics=_read(root / "player_display_diagnostics.json"),
        runtime_diagnostics=_read(root / "fused_diagnostics.json"),
    )
    baseline = evaluate_quality(FourPlayerIdentificationQuality.model_validate(_read(baseline_path)))
    comparison = compare_quality(baseline, quality)
    overlay = _read(root / "fused_player_overlay.json")
    roster = _read(root / "roster.json")
    visualization = _read(root / "position_visualizations" / "structured" / "data.json")

    frame_2s = _nearest_frame(overlay, 2.0)
    frame_4s = _nearest_frame(overlay, 4.0)
    p2_2s = next((p for p in (frame_2s or {}).get("players", []) if p.get("player_id") == "Player_2"), None)
    p2_4s = next((p for p in (frame_4s or {}).get("players", []) if p.get("player_id") == "Player_2"), None)
    detector_backed = bool(
        p2_2s
        and p2_2s.get("bbox")
        and p2_2s.get("evidence_type") in {"base_observed", "guided_observed", "refined_observed"}
    )
    p2_owner_safe = bool(
        p2_4s
        and p2_4s.get("target_player_slot") in {None, "Player_2"}
        and p2_4s.get("bbox_memory_owner_global_id") != "global_player_1"
    )
    p2_viz = dict((visualization.get("identity_quality") or {}).get("players", {}).get("Player_2") or {})
    checks = {
        "quality_absolute_gates": quality.verdict == "pass",
        "baseline_non_regression": comparison.verdict == "pass",
        "p2_detector_backed_at_2s": detector_backed,
        "p2_does_not_use_p1_bbox_owner_at_4s": p2_owner_safe,
        "confirmed_four_player_roster": roster.get("confirmed_player_count") == 4,
        "duplicate_binding_zero": quality.hard_invariants.get("duplicate_binding_zero", False),
        "identity_switch_zero": quality.hard_invariants.get("identity_switch_zero", False),
        "cross_side_zero": quality.hard_invariants.get("cross_side_zero", False),
        "p2_visualization_sufficient": p2_viz.get("sufficiency") == "sufficient",
        "appearance_diagnostics_present": any(
            player.appearance.descriptor_attempts > 0 for player in quality.players.values()
        ),
    }
    return {
        "schema_version": "four-player-identification-acceptance.v1",
        "job_id": quality.job_id,
        "baseline_job_id": baseline.job_id,
        "verdict": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "quality_failure_reasons": quality.failure_reasons,
        "comparison_reasons": comparison.reasons,
        "players": {
            player_id: {
                "canonical_coverage": player.canonical_coverage,
                "longest_gap_seconds": player.longest_gap_seconds,
                "quarantined_count": player.quarantined_count,
            }
            for player_id, player in quality.players.items()
        },
        "p2_2s": p2_2s,
        "p2_4s": p2_4s,
        "camera_profiles": quality.camera_profiles,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
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
