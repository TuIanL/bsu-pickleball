"""Serving-team kitchen-line arrival calculator.

The calculator is deliberately small and deterministic.  It consumes only a
Job-bound rally context, the confirmed identity audit, formal rally windows and
the real player trajectory artifact.  It never reads live scoring state.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.schemas.kitchen_arrival import (
    KitchenArrivalArtifact,
    KitchenArrivalDiagnostics,
    KitchenArrivalPlayerResult,
    KitchenArrivalRallyResult,
    KitchenArrivalReference,
)

COURT_LENGTH_M = 13.4112
FEET_TO_METERS = 0.3048
KITCHEN_LINE_FROM_END_M = 15.0 * FEET_TO_METERS
KITCHEN_LINE_FROM_NET_M = 7.0 * FEET_TO_METERS

# This is a versioned product reference, not a hidden model threshold.  A
# deployment can replace it by passing an explicit reference to the builder;
# the complete value is always written into the artifact for auditability.
KITCHEN_ARRIVAL_REFERENCE_V1 = KitchenArrivalReference(
    arrival_band_m=0.75,
    stable_ms=500,
    arrival_min_detected_support_ms=250,
    not_arrived_min_coverage_ratio=0.80,
    not_arrived_max_gap_ms=500,
    min_sample_count=3,
    calibration_status="locked_reference",
    provenance={
        "source": "product_reference_v1",
        "coordinate_system": "player_trajectory.court_m",
        "calibration_note": "参数已版本化；后续人工回放校准不得覆盖既有版本",
    },
)


def configured_kitchen_arrival_reference() -> KitchenArrivalReference:
    """Load the versioned reference from deployment configuration.

    The module constant remains a safe test/default fallback, while production
    runs can calibrate the values through the `PICKLEBALL_KITCHEN_ARRIVAL_*`
    settings without editing calculator code.
    """
    try:
        from app.core.config import get_settings

        settings = get_settings()
        return KITCHEN_ARRIVAL_REFERENCE_V1.model_copy(
            update={
                "arrival_band_m": settings.kitchen_arrival_band_m,
                "stable_ms": settings.kitchen_arrival_stable_ms,
                "arrival_min_detected_support_ms": settings.kitchen_arrival_min_detected_support_ms,
                "not_arrived_min_coverage_ratio": settings.kitchen_arrival_min_coverage_ratio,
                "not_arrived_max_gap_ms": settings.kitchen_arrival_max_gap_ms,
                "min_sample_count": settings.kitchen_arrival_min_sample_count,
                "provenance": {
                    **KITCHEN_ARRIVAL_REFERENCE_V1.provenance,
                    "source": "deployment_settings:PICKLEBALL_KITCHEN_ARRIVAL_*",
                },
            }
        )
    except Exception:  # noqa: BLE001 - configuration fallback is deterministic
        return KITCHEN_ARRIVAL_REFERENCE_V1

EXCLUDED_NO_CONTEXT = "missing_or_unconfirmed_rally_context"
EXCLUDED_NO_FORMAL_BINDING = "formal_window_binding_unavailable"
EXCLUDED_NO_IDENTITY_AUDIT = "identity_audit_unavailable"
EXCLUDED_NO_TRAJECTORY = "missing_player_trajectory"
EXCLUDED_INSUFFICIENT = "insufficient_track_coverage"
EXCLUDED_UNCERTAIN_CROSSING = "uncertain_crossing_interval"


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists() or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _display_names(roster: Any) -> dict[str, str | None]:
    entries = roster.get("entries", []) if isinstance(roster, dict) else getattr(roster, "entries", [])
    result: dict[str, str | None] = {}
    for entry in entries or []:
        player_id = (
            entry.get("canonical_player_id") if isinstance(entry, dict) else getattr(entry, "canonical_player_id", None)
        )
        if player_id:
            result[str(player_id)] = (
                entry.get("display_name") if isinstance(entry, dict) else getattr(entry, "display_name", None)
            )
    return result


def _roster_entries(roster: Any) -> list[dict[str, Any]]:
    entries = roster.get("entries", []) if isinstance(roster, dict) else getattr(roster, "entries", [])
    output: list[dict[str, Any]] = []
    for entry in entries or []:
        if isinstance(entry, dict):
            output.append(entry)
        else:
            output.append(entry.model_dump(mode="json") if hasattr(entry, "model_dump") else {})
    return output


def _audit_available(binding_audit: Any | None, player_id: str) -> bool:
    if binding_audit is None:
        return False
    status = binding_audit.get("status") if isinstance(binding_audit, dict) else getattr(binding_audit, "status", None)
    if status != "available":
        return False
    entries = (
        binding_audit.get("entries", []) if isinstance(binding_audit, dict) else getattr(binding_audit, "entries", [])
    )
    for item in entries or []:
        canonical = (
            item.get("canonical_player_id") if isinstance(item, dict) else getattr(item, "canonical_player_id", None)
        )
        formal = (
            item.get("formal_canonical_player_id")
            if isinstance(item, dict)
            else getattr(item, "formal_canonical_player_id", None)
        )
        confirmed = item.get("confirmed") if isinstance(item, dict) else getattr(item, "confirmed", False)
        if canonical == player_id:
            return bool(confirmed and formal == player_id)
    return False


def _context_value(context: Any, key: str, default: Any = None) -> Any:
    return context.get(key, default) if isinstance(context, dict) else getattr(context, key, default)


def _trajectory_points(
    payload: dict[str, Any] | None,
    player_id: str,
    start_ms: int,
    end_ms: int,
    identity_map: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    if not payload:
        return []
    raw_players = payload.get("players")
    aliases = [player_id]
    if identity_map:
        aliases.extend(global_id for global_id, canonical_id in identity_map.items() if canonical_id == player_id)
    raw: list[dict[str, Any]] = []
    if isinstance(raw_players, dict):
        for alias in aliases:
            candidate = raw_players.get(alias)
            if isinstance(candidate, list):
                raw.extend(item for item in candidate if isinstance(item, dict))
    if not raw and isinstance(payload.get("samples"), list):
        raw = [
            item
            for item in payload["samples"]
            if isinstance(item, dict)
            and (
                str(item.get("global_player_id")) in aliases
                or str(item.get("player_id")) in aliases
            )
        ]
    points: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            timestamp_ms = int(
                round(float(item.get("timestamp_seconds", item.get("take_timestamp_ms", 0.0) / 1000.0)) * 1000.0)
            )
            if "x_ft" in item or "y_ft" in item:
                x = float(item.get("x_ft")) * FEET_TO_METERS
                y = float(item.get("y_ft")) * FEET_TO_METERS
            else:
                x = float(item.get("smoothed_court_x", item.get("court_x")))
                y = float(item.get("smoothed_court_y", item.get("court_y")))
        except (TypeError, ValueError):
            continue
        if timestamp_ms < start_ms or timestamp_ms > end_ms:
            continue
        points.append(
            {
                "timestamp_ms": timestamp_ms,
                "x": x,
                "y": y,
                "detected": bool(
                    not item.get("is_interpolated", False)
                    and item.get("identity_status", "confirmed_observed") != "interpolated"
                    and (
                        item.get("source", "detector") == "detector"
                        and item.get("tracking_status", "detected") in {"detected", "tentative", "active"}
                        or item.get("metric_eligible") is True
                        and item.get("identity_status", "confirmed_observed")
                        in {"confirmed_observed", "confirmed_recovered", "reacquired"}
                    )
                ),
            }
        )
    return sorted(points, key=lambda point: point["timestamp_ms"])


def _line_y(end: str | None) -> float | None:
    if end == "end_a":
        return KITCHEN_LINE_FROM_END_M
    if end == "end_b":
        return COURT_LENGTH_M - KITCHEN_LINE_FROM_END_M
    return None


def _max_gap(points: list[dict[str, Any]], start_ms: int, end_ms: int) -> int:
    detected_points = [point for point in points if point["detected"]]
    if not detected_points:
        return max(0, end_ms - start_ms)
    gaps = [detected_points[0]["timestamp_ms"] - start_ms, end_ms - detected_points[-1]["timestamp_ms"]]
    gaps.extend(
        b["timestamp_ms"] - a["timestamp_ms"]
        for a, b in zip(detected_points, detected_points[1:], strict=False)
    )
    return max(gaps, default=0)


def _coverage(points: list[dict[str, Any]], start_ms: int, end_ms: int) -> float:
    duration = max(1, end_ms - start_ms)
    detected_points = [point for point in points if point["detected"]]
    if len(detected_points) < 2:
        return 0.0
    observed_span = max(0, detected_points[-1]["timestamp_ms"] - detected_points[0]["timestamp_ms"])
    return min(1.0, observed_span / duration)


def _has_uncertain_crossing(points: list[dict[str, Any]], line_y: float, reference: KitchenArrivalReference) -> bool:
    for before, after in zip(points, points[1:], strict=False):
        before_distance = before["y"] - line_y
        after_distance = after["y"] - line_y
        before_in_band = abs(before_distance) <= reference.arrival_band_m
        after_in_band = abs(after_distance) <= reference.arrival_band_m
        crosses_band = before_in_band or after_in_band or (
            before_distance < -reference.arrival_band_m
            and after_distance > reference.arrival_band_m
        ) or (
            before_distance > reference.arrival_band_m
            and after_distance < -reference.arrival_band_m
        )
        if crosses_band:
            return True
    return False


def classify_player_window(
    points: list[dict[str, Any]],
    *,
    start_ms: int,
    end_ms: int,
    line_y: float,
    reference: KitchenArrivalReference = KITCHEN_ARRIVAL_REFERENCE_V1,
) -> dict[str, Any]:
    """Classify one serving-player trajectory window.

    The return value is intentionally plain data so unit tests and later
    calibration tooling can exercise the state machine without a database.
    """
    if len(points) < reference.min_sample_count:
        return {
            "state": "excluded",
            "reason": EXCLUDED_INSUFFICIENT,
            "coverage_ratio": _coverage(points, start_ms, end_ms),
            "max_gap_ms": _max_gap(points, start_ms, end_ms),
            "detected_support_ms": 0,
        }
    coverage = _coverage(points, start_ms, end_ms)
    max_gap_ms = _max_gap(points, start_ms, end_ms)
    in_band = [abs(point["y"] - line_y) <= reference.arrival_band_m for point in points]
    detected_support_ms = 0
    arrival_time_ms: int | None = None
    run_start: int | None = None
    for index, point in enumerate(points):
        if in_band[index]:
            run_start = point["timestamp_ms"] if run_start is None else run_start
            run_end = point["timestamp_ms"]
            if run_end - run_start >= reference.stable_ms:
                window_points = [candidate for candidate in points if run_start <= candidate["timestamp_ms"] <= run_end]
                detected_support_ms = sum(
                    max(0, b["timestamp_ms"] - a["timestamp_ms"])
                    for a, b in zip(window_points, window_points[1:], strict=False)
                    if a["detected"] and b["detected"]
                )
                if detected_support_ms >= reference.arrival_min_detected_support_ms:
                    arrival_time_ms = run_start
                    break
        else:
            run_start = None
    if arrival_time_ms is not None:
        first_ts = points[0]["timestamp_ms"]
        start_tolerance_ms = max(1, reference.stable_ms // 5)
        already_present = arrival_time_ms <= first_ts + 1 and first_ts - start_ms <= start_tolerance_ms
        return {
            "state": "already_present" if already_present else "arrived",
            "reason": None,
            "arrival_time_ms": 0 if already_present else max(0, arrival_time_ms - start_ms),
            "coverage_ratio": coverage,
            "max_gap_ms": max_gap_ms,
            "detected_support_ms": detected_support_ms,
        }
    if coverage < reference.not_arrived_min_coverage_ratio or max_gap_ms > reference.not_arrived_max_gap_ms:
        return {
            "state": "excluded",
            "reason": EXCLUDED_INSUFFICIENT,
            "coverage_ratio": coverage,
            "max_gap_ms": max_gap_ms,
            "detected_support_ms": detected_support_ms,
        }
    if _has_uncertain_crossing(points, line_y, reference):
        return {
            "state": "excluded",
            "reason": EXCLUDED_UNCERTAIN_CROSSING,
            "coverage_ratio": coverage,
            "max_gap_ms": max_gap_ms,
            "detected_support_ms": detected_support_ms,
        }
    if any(in_band):
        return {
            "state": "excluded",
            "reason": EXCLUDED_INSUFFICIENT,
            "coverage_ratio": coverage,
            "max_gap_ms": max_gap_ms,
            "detected_support_ms": detected_support_ms,
        }
    return {
        "state": "not_arrived",
        "reason": None,
        "coverage_ratio": coverage,
        "max_gap_ms": max_gap_ms,
        "detected_support_ms": detected_support_ms,
    }


def build_kitchen_arrival_artifact(
    *,
    job_id: str,
    video_id: str | None,
    match_format: str,
    rallies: Iterable[Any],
    roster: Any | None,
    binding_audit: Any | None,
    trajectory_payload: dict[str, Any] | None,
    trajectory_identity_map: dict[str, str] | None = None,
    reference: KitchenArrivalReference = KITCHEN_ARRIVAL_REFERENCE_V1,
    generated_at: str | None = None,
) -> KitchenArrivalArtifact:
    generated_at = generated_at or datetime.now(UTC).isoformat()
    base = dict(
        job_id=job_id,
        video_id=video_id,
        generated_at=generated_at,
        reference=reference,
        source_artifacts=[
            "analysis-rally-context.v1",
            "bootstrap-binding-audit.v1",
            "players_trajectory.json",
            "fused_player_trajectory.v2",
        ],
        provenance={"calculator": "serving_team_kitchen_line_arrival", "calculation_version": "kitchen-arrival.v1"},
    )
    if match_format != "doubles":
        return KitchenArrivalArtifact(status="not_applicable", detail="单打任务不适用发球队厨房线到位率", **base)
    names = _display_names(roster)
    roster_entries = _roster_entries(roster)
    team_by_player = {
        str(item.get("canonical_player_id")): item.get("team_id")
        for item in roster_entries
        if item.get("canonical_player_id") and item.get("team_id") in {"A", "B"}
    }
    if roster is None or not trajectory_payload:
        players = [
            KitchenArrivalPlayerResult(
                player_id=player_id,
                display_name=names.get(player_id),
                team_id=team,
                status="unavailable",
                reason="缺少冻结名册或真实球员轨迹，无法计算厨房线到位率",
            )
            for player_id, team in sorted(team_by_player.items())
        ]
        return KitchenArrivalArtifact(
            status="unavailable", detail="缺少冻结名册或真实球员轨迹，无法计算厨房线到位率", players=players, **base
        )
    if (
        binding_audit is None
        or (binding_audit.get("status") if isinstance(binding_audit, dict) else getattr(binding_audit, "status", None))
        != "available"
    ):
        players = [
            KitchenArrivalPlayerResult(
                player_id=player_id,
                display_name=names.get(player_id),
                team_id=team,
                status="unavailable",
                reason="身份连续性审计不可用，厨房线到位率已安全降级",
            )
            for player_id, team in sorted(team_by_player.items())
        ]
        return KitchenArrivalArtifact(
            status="unavailable", detail="身份连续性审计不可用，厨房线到位率已安全降级", players=players, **base
        )
    rally_results: list[KitchenArrivalRallyResult] = []
    diagnostics_reasons: Counter[str] = Counter()
    for rally in rallies:
        rally_id = str(_context_value(rally, "rally_id", ""))
        ordinal = int(_context_value(rally, "ordinal", 1))
        status = _context_value(rally, "status")
        server_team = _context_value(rally, "server_team")
        start_ms = int(_context_value(rally, "start_ms", 0))
        raw_end_ms = _context_value(rally, "end_ms", start_ms)
        end_ms = int(raw_end_ms) if raw_end_ms is not None else start_ms
        binding = _context_value(rally, "binding")
        binding_method = _context_value(binding, "method") if binding is not None else "unavailable"
        if status != "available":
            diagnostics_reasons[EXCLUDED_NO_CONTEXT] += 1
            continue
        if binding_method == "unavailable":
            diagnostics_reasons[EXCLUDED_NO_FORMAL_BINDING] += 1
            continue
        if server_team not in {"A", "B"}:
            diagnostics_reasons[EXCLUDED_NO_CONTEXT] += 1
            continue
        server_players = [player for player, team in team_by_player.items() if team == server_team]
        end = _context_value(rally, "team_a_end" if server_team == "A" else "team_b_end")
        line_y = _line_y(end)
        if line_y is None:
            diagnostics_reasons[EXCLUDED_NO_CONTEXT] += len(server_players) or 1
            continue
        for player_id in server_players:
            if not _audit_available(binding_audit, player_id):
                diagnostics_reasons[EXCLUDED_NO_IDENTITY_AUDIT] += 1
                continue
            points = _trajectory_points(
                trajectory_payload,
                player_id,
                start_ms,
                end_ms,
                identity_map=trajectory_identity_map,
            )
            if not points:
                diagnostics_reasons[EXCLUDED_NO_TRAJECTORY] += 1
                state = {
                    "state": "excluded",
                    "reason": EXCLUDED_NO_TRAJECTORY,
                    "coverage_ratio": 0.0,
                    "max_gap_ms": end_ms - start_ms,
                    "detected_support_ms": 0,
                }
            else:
                state = classify_player_window(
                    points, start_ms=start_ms, end_ms=end_ms, line_y=line_y, reference=reference
                )
                if state.get("reason"):
                    diagnostics_reasons[str(state["reason"])] += 1
            rally_results.append(
                KitchenArrivalRallyResult(
                    rally_id=rally_id,
                    ordinal=ordinal,
                    player_id=player_id,
                    display_name=names.get(player_id),
                    team_id=server_team,
                    server_team=server_team,
                    state=state["state"],
                    eligible=state["state"] in {"arrived", "already_present", "not_arrived"},
                    already_present=state["state"] == "already_present",
                    arrived=state["state"] in {"arrived", "already_present"},
                    arrival_time_ms=state.get("arrival_time_ms"),
                    coverage_ratio=state.get("coverage_ratio"),
                    max_gap_ms=state.get("max_gap_ms"),
                    detected_support_ms=state.get("detected_support_ms", 0),
                    excluded_reason=state.get("reason"),
                    evidence_ids=sorted(
                        {
                            rally_id,
                            str(_context_value(rally, "context_hash") or "analysis-rally-context.v1"),
                            "bootstrap-binding-audit.v1",
                            "players_trajectory.json",
                        }
                    ),
                    provenance={
                        "context_hash": _context_value(rally, "context_hash"),
                        "binding_method": binding_method,
                        "line_end": end,
                    },
                )
            )

    grouped: dict[str, list[KitchenArrivalRallyResult]] = defaultdict(list)
    for item in rally_results:
        grouped[item.player_id].append(item)
    player_results: list[KitchenArrivalPlayerResult] = []
    for player_id, team_id in sorted(team_by_player.items()):
        samples = grouped.get(player_id, [])
        eligible = [item for item in samples if item.eligible]
        arrived = [item for item in eligible if item.arrived]
        excluded = [item for item in samples if not item.eligible]
        status = "available" if len(eligible) >= reference.min_sample_count else "insufficient_evidence"
        player_results.append(
            KitchenArrivalPlayerResult(
                player_id=player_id,
                display_name=names.get(player_id),
                team_id=team_id,
                arrived_count=len(arrived),
                eligible_count=len(eligible),
                sample_count=len(samples),
                excluded_count=len(excluded),
                arrival_rate=(len(arrived) / len(eligible)) if status == "available" and eligible else None,
                status=status,
                reason=None if status == "available" else "有效发球回合样本不足，暂不展示百分比",
                rally_ids=[item.rally_id for item in samples],
            )
        )
    diagnostics = KitchenArrivalDiagnostics(
        total_rallies=len({item.rally_id for item in rally_results}),
        eligible_samples=sum(item.eligible for item in rally_results),
        excluded_samples=sum(not item.eligible for item in rally_results),
        excluded_reasons=dict(sorted(diagnostics_reasons.items())),
        coverage_ratios={
            f"{item.rally_id}:{item.player_id}": round(item.coverage_ratio or 0.0, 4) for item in rally_results
        },
        max_gaps_ms={f"{item.rally_id}:{item.player_id}": item.max_gap_ms or 0 for item in rally_results},
        warnings=[],
    )
    if not rally_results:
        return KitchenArrivalArtifact(
            status="unavailable", detail="没有可绑定的正式发球回合与冻结身份", diagnostics=diagnostics, **base
        )
    if not any(item.eligible for item in rally_results):
        return KitchenArrivalArtifact(
            status="insufficient_evidence",
            detail="正式回合存在，但没有足够真实轨迹形成到位统计",
            players=player_results,
            rallies=rally_results,
            diagnostics=diagnostics,
            **base,
        )
    return KitchenArrivalArtifact(
        status="available",
        detail=f"已生成 {len(rally_results)} 条发球队厨房线到位样本",
        players=player_results,
        rallies=rally_results,
        diagnostics=diagnostics,
        **base,
    )
