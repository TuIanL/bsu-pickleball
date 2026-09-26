"""Compose canonical Shot facts into first-formal-bounce landings."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import Counter
from datetime import UTC, datetime
from math import hypot, isfinite
from typing import Any, Iterable

from app.schemas.shot_landings import (
    LandingProfileSnapshot,
    ShotLanding,
    ShotLandingDiagnostics,
    ShotLandingsArtifact,
    ShotLandingSummary,
)
from app.schemas.shot_rally_events import ShotRallyEventsArtifact

CLASSIFICATION_PROFILE = LandingProfileSnapshot(
    profile_id="landing-classification.v1",
    parameters={"default_boundary_uncertainty_ft": 0.1, "semantics": "descriptive_not_officiating"},
)
ORIENTATION_PROFILE = LandingProfileSnapshot(
    profile_id="landing-orientation.v1",
    parameters={
        "contact_neighborhood_ms": 250,
        "minimum_direction_displacement_ft": 2.0,
        "left_right_semantics": "attacker_facing_target",
    },
)
PROJECT12_PROFILE = LandingProfileSnapshot(
    profile_id="project12.v1",
    parameters={
        "columns": [
            {"id": "L", "u_min": 0.0, "u_max": 1 / 3},
            {"id": "C", "u_min": 1 / 3, "u_max": 2 / 3},
            {"id": "R", "u_min": 2 / 3, "u_max": 1.0},
        ],
        "rows": [
            {"id": "K", "distance_net_ft": [0.0, 7.0], "basis": "physical_nvz"},
            {"id": "T", "distance_net_ft": [7.0, 12.0], "basis": "project_analytic"},
            {"id": "D", "distance_net_ft": [12.0, 17.0], "basis": "project_analytic"},
            {"id": "VD", "distance_net_ft": [17.0, 22.0], "basis": "project_analytic"},
        ],
    },
)

COURT_WIDTH_FT = 20.0
COURT_LENGTH_FT = 44.0
NET_Y_FT = 22.0
CONTACT_NEIGHBORHOOD_MS = 250
MIN_DIRECTION_DISPLACEMENT_FT = 2.0
DEFAULT_BOUNDARY_UNCERTAINTY_FT = 0.1


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _point(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    x, y = _finite_number(value[0]), _finite_number(value[1])
    return (x, y) if x is not None and y is not None else None


def classify_court_location(
    x_ft: float,
    y_ft: float,
    uncertainty_ft: float | None = None,
) -> str:
    """Descriptive geometry classification; the uncertainty band is unknown."""
    tolerance = uncertainty_ft if uncertainty_ft is not None and uncertainty_ft >= 0 else DEFAULT_BOUNDARY_UNCERTAINTY_FT
    outside_dx = max(-x_ft, 0.0, x_ft - COURT_WIDTH_FT)
    outside_dy = max(-y_ft, 0.0, y_ft - COURT_LENGTH_FT)
    boundary_distance = (
        hypot(outside_dx, outside_dy)
        if outside_dx or outside_dy
        else min(x_ft, COURT_WIDTH_FT - x_ft, y_ft, COURT_LENGTH_FT - y_ft)
    )
    if boundary_distance <= tolerance:
        return "unknown"
    if 0.0 < x_ft < COURT_WIDTH_FT and 0.0 < y_ft < COURT_LENGTH_FT:
        return "inside_court"
    return "outside_court"


def project12_zone(u: float, distance_from_net_ft: float, *, eligible: bool = True) -> tuple[str, int] | None:
    """Map an eligible normalized target-half point to project12.v1."""
    if not eligible or not (isfinite(u) and isfinite(distance_from_net_ft)):
        return None
    if not (0.0 <= u <= 1.0 and 0.0 <= distance_from_net_ft <= 22.0):
        return None
    col_index = 0 if u < 1 / 3 else 1 if u < 2 / 3 else 2
    if distance_from_net_ft < 7.0:
        row_index, row = 0, "K"
    elif distance_from_net_ft < 12.0:
        row_index, row = 1, "T"
    elif distance_from_net_ft < 17.0:
        row_index, row = 2, "D"
    else:
        row_index, row = 3, "VD"
    col = ("L", "C", "R")[col_index]
    return f"{row}-{col}", row_index * 3 + col_index + 1


def _event_time(event: dict[str, Any] | None) -> float:
    if not event:
        return float("inf")
    value = _finite_number(event.get("timestamp_sec"))
    return value if value is not None else float("inf")


def _sample_timestamp_ms(sample: dict[str, Any]) -> int | None:
    if (value := _finite_number(sample.get("timestamp_ms"))) is not None:
        return round(value)
    if (value := _finite_number(sample.get("take_timestamp_ms"))) is not None:
        return round(value)
    if (value := _finite_number(sample.get("timestamp_seconds"))) is not None:
        return round(value * 1000)
    if (value := _finite_number(sample.get("timestamp_sec"))) is not None:
        return round(value * 1000)
    return None


def _sample_player_id(sample: dict[str, Any]) -> str | None:
    for key in ("player_id", "canonical_player_id", "global_player_id"):
        value = sample.get(key)
        if isinstance(value, str) and value.startswith("Player_"):
            return value
    return None


def _sample_xy(sample: dict[str, Any]) -> tuple[float, float] | None:
    if (point := _point(sample.get("court_xy"))) is not None:
        return point
    x_value = sample.get("x_ft")
    if x_value is None:
        x_value = sample.get("canonical_x_ft")
    y_value = sample.get("y_ft")
    if y_value is None:
        y_value = sample.get("canonical_y_ft")
    x = _finite_number(x_value)
    y = _finite_number(y_value)
    return (x, y) if x is not None and y is not None else None


def _iter_player_samples(payload: dict[str, Any] | None) -> Iterable[dict[str, Any]]:
    if not payload:
        return []
    flat = payload.get("samples")
    if isinstance(flat, list):
        return [item for item in flat if isinstance(item, dict)]
    nested: list[dict[str, Any]] = []
    for player in payload.get("players") or []:
        if not isinstance(player, dict):
            continue
        player_id = player.get("player_id")
        for sample in player.get("samples") or []:
            if isinstance(sample, dict):
                nested.append({"player_id": player_id, **sample})
    return nested


def _player_side_index(payload: dict[str, Any] | None) -> dict[str, list[tuple[int, float]]]:
    index: dict[str, list[tuple[int, float]]] = {}
    for sample in _iter_player_samples(payload):
        player_id = _sample_player_id(sample)
        if not player_id or str(sample.get("projection_status") or "") in {"projection_failed", "invalid"}:
            continue
        timestamp_ms, point = _sample_timestamp_ms(sample), _sample_xy(sample)
        if timestamp_ms is not None and point is not None and abs(point[1] - NET_Y_FT) > 1e-9:
            index.setdefault(player_id, []).append((timestamp_ms, point[1]))
    for samples in index.values():
        samples.sort()
    return index


def hitter_side_at_contact(
    player_trajectory_payload: dict[str, Any] | None,
    hitter_player_id: str | None,
    contact_ms: int | None,
    *,
    sample_index: dict[str, list[tuple[int, float]]] | None = None,
) -> str | None:
    if not hitter_player_id or contact_ms is None:
        return None
    index = sample_index if sample_index is not None else _player_side_index(player_trajectory_payload)
    samples = index.get(hitter_player_id, [])
    left = bisect_left(samples, (contact_ms - CONTACT_NEIGHBORHOOD_MS, float("-inf")))
    right = bisect_right(samples, (contact_ms + CONTACT_NEIGHBORHOOD_MS, float("inf")))
    if left == right:
        return None
    _, y_ft = min(samples[left:right], key=lambda item: (abs(item[0] - contact_ms), item[1]))
    return "near" if y_ft < NET_Y_FT else "far"


def _first_shot_point(segments: list[dict[str, Any]]) -> tuple[float, float] | None:
    samples = [sample for segment in segments for sample in (segment.get("samples") or []) if isinstance(sample, dict)]
    samples.sort(key=lambda item: (_finite_number(item.get("timestamp_sec")) or float("inf"), int(item.get("frame_index") or 0)))
    for sample in samples:
        point = _point(sample.get("court_xy"))
        if point is not None:
            return point
    return None


def _direction_target_half(segments: list[dict[str, Any]], landing_y_ft: float) -> str | None:
    start = _first_shot_point(segments)
    if start is None:
        return None
    delta_y = landing_y_ft - start[1]
    if abs(delta_y) < MIN_DIRECTION_DISPLACEMENT_FT:
        return None
    return "far" if delta_y > 0 else "near"


def _uncertainty(event: dict[str, Any]) -> float | None:
    direct = _finite_number(event.get("calibration_uncertainty_ft"))
    if direct is not None and direct >= 0:
        return direct
    diagnostics = event.get("diagnostics")
    nested = _finite_number(diagnostics.get("calibration_uncertainty_ft")) if isinstance(diagnostics, dict) else None
    return nested if nested is not None and nested >= 0 else None


def _empty_landing(shot: Any, status: str, diagnostics: list[str]) -> ShotLanding:
    return ShotLanding(
        landing_id=f"landing-{shot.shot_id}",
        shot_id=shot.shot_id,
        rally_id=shot.rally_id,
        ordinal_in_rally=shot.ordinal_in_rally,
        hitter_player_id=shot.hitter_player_id,
        shot_stage=shot.stage,
        landing_status=status,
        source_artifacts=["shot-rally-events.v1", "reconstructed-ball-trajectory"],
        diagnostics=diagnostics,
    )


def build_shot_landings(
    *,
    job_id: str,
    video_id: str | None,
    shot_events: ShotRallyEventsArtifact,
    reconstructed_payload: dict[str, Any] | None,
    player_trajectory_payload: dict[str, Any] | None = None,
    generated_at: str | None = None,
) -> ShotLandingsArtifact:
    generated_at = generated_at or datetime.now(UTC).isoformat()
    normalization_profile = ORIENTATION_PROFILE.model_copy(deep=True)
    zone_profiles = {"paper_6": None, "project_12": PROJECT12_PROFILE.model_copy(deep=True)}
    if reconstructed_payload is None:
        return ShotLandingsArtifact(
            job_id=job_id,
            video_id=video_id,
            status="unavailable",
            detail="缺少 reconstructed trajectory，无法组合 Shot Landing",
            generated_at=generated_at,
            normalization_profile=normalization_profile,
            zone_profiles=zone_profiles,
            source_artifacts=["shot-rally-events.v1", "reconstructed-ball-trajectory"],
            diagnostics=ShotLandingDiagnostics(warnings=["reconstructed trajectory missing"]),
        )

    segments_by_id = {
        str(item.get("segment_id")): item
        for item in reconstructed_payload.get("segments") or []
        if isinstance(item, dict) and item.get("segment_id")
    }
    events_by_id = {
        str(item.get("event_id")): item
        for item in reconstructed_payload.get("events") or []
        if isinstance(item, dict) and item.get("event_id")
    }
    missing_segments: set[str] = set()
    missing_events: set[str] = set()
    results: list[ShotLanding] = []

    sample_index = _player_side_index(player_trajectory_payload)
    for shot in sorted(shot_events.shots, key=lambda item: (item.start_ms, item.shot_id)):
        requested_ids = list(shot.trajectory.segment_ids)
        shot_segments: list[dict[str, Any]] = []
        for segment_id in requested_ids:
            segment = segments_by_id.get(segment_id)
            if segment is None:
                missing_segments.add(segment_id)
            else:
                shot_segments.append(segment)
        if len(shot_segments) != len(requested_ids):
            results.append(_empty_landing(shot, "unavailable", ["canonical shot references missing segment"])); continue

        shot_segments.sort(
            key=lambda segment: (
                _event_time(events_by_id.get(str(segment.get("end_event_id")))),
                str(segment.get("segment_id") or ""),
            )
        )
        bounce_segment = next(
            (segment for segment in shot_segments if str(segment.get("end_event_type") or "").lower() == "bounce"),
            None,
        )
        if bounce_segment is None:
            end_types = {str(segment.get("end_event_type") or "").lower() for segment in shot_segments}
            status = "no_bounce_before_next_contact" if "hit" in end_types else "unavailable"
            results.append(_empty_landing(shot, status, [])); continue

        event_id = str(bounce_segment.get("end_event_id") or "")
        event = events_by_id.get(event_id)
        if event is None:
            if event_id:
                missing_events.add(event_id)
            results.append(_empty_landing(shot, "unavailable", ["bounce segment references missing event"])); continue
        event_status = str(event.get("event_status") or "confirmed").lower()
        if event_status != "confirmed":
            results.append(_empty_landing(shot, "ambiguous_bounce", [f"bounce event status={event_status}"])); continue

        point = _point(event.get("court_xy"))
        if point is None:
            item = _empty_landing(shot, "bounce_without_court_coordinate", [])
            results.append(item.model_copy(update={
                "bounce_event_id": event_id,
                "source_event_id": event_id,
                "source_segment_id": str(bounce_segment.get("segment_id")),
                "frame_index": event.get("frame_index"),
                "timestamp_ms": round(float(event.get("timestamp_sec", 0.0)) * 1000),
                "bounce_confidence": event.get("confidence"),
            })); continue

        x_ft, y_ft = point
        uncertainty = _uncertainty(event)
        court_location = classify_court_location(x_ft, y_ft, uncertainty)
        hitter_side = hitter_side_at_contact(player_trajectory_payload, shot.hitter_player_id, shot.contact_ms, sample_index=sample_index)
        target_half: str | None = None
        basis = "unavailable"
        if hitter_side is not None:
            target_half = "far" if hitter_side == "near" else "near"
            basis = "hitter_position_at_contact"
        else:
            target_half = _direction_target_half(shot_segments, y_ft)
            if target_half is not None:
                basis = "trajectory_direction"

        target_relation = "unknown"
        orientation = "unavailable"
        target_x = target_y = u = v = None
        if target_half is not None:
            if abs(y_ft - NET_Y_FT) <= (uncertainty if uncertainty is not None else DEFAULT_BOUNDARY_UNCERTAINTY_FT):
                target_relation = "unknown"
            else:
                target_relation = "target_half" if ((target_half == "far" and y_ft > NET_Y_FT) or (target_half == "near" and y_ft < NET_Y_FT)) else "own_half"
            if target_half == "far":
                orientation = "identity"
                target_x, target_y = x_ft, y_ft
            else:
                orientation = "rotate_180"
                target_x, target_y = COURT_WIDTH_FT - x_ft, COURT_LENGTH_FT - y_ft
            u = target_x / COURT_WIDTH_FT
            v = (target_y - NET_Y_FT) / NET_Y_FT

        eligible = court_location == "inside_court" and target_relation == "target_half" and u is not None and v is not None
        zone = project12_zone(u or 0.0, (v or 0.0) * NET_Y_FT, eligible=eligible)
        results.append(ShotLanding(
            landing_id=f"landing-{shot.shot_id}",
            shot_id=shot.shot_id,
            rally_id=shot.rally_id,
            ordinal_in_rally=shot.ordinal_in_rally,
            bounce_event_id=event_id,
            frame_index=event.get("frame_index"),
            timestamp_ms=round(float(event.get("timestamp_sec", 0.0)) * 1000),
            hitter_player_id=shot.hitter_player_id,
            shot_stage=shot.stage,
            landing_status="available",
            landing_x_ft=x_ft,
            landing_y_ft=y_ft,
            court_location=court_location,
            target_relation=target_relation,
            target_half=target_half,
            orientation_transform=orientation,
            target_x_ft=target_x,
            target_y_ft=target_y,
            landing_u=u,
            landing_v=v,
            zone_12=zone[0] if zone else None,
            zone_12_id=zone[1] if zone else None,
            zone_12_profile="project12.v1" if zone else None,
            landing_source=str(event.get("landing_source") or "single_view_ground"),
            bounce_confidence=event.get("confidence"),
            geometry_quality=event.get("geometry_quality"),
            calibration_uncertainty_ft=uncertainty,
            canonicalization_basis=basis,
            source_segment_id=str(bounce_segment.get("segment_id")),
            source_event_id=event_id,
            source_artifacts=["shot-rally-events.v1", "reconstructed-ball-trajectory"],
        ))

    formal_bounces = [item for item in results if item.landing_status in {"available", "bounce_without_court_coordinate"}]
    measurable = [item for item in formal_bounces if item.landing_status == "available"]
    zoned = [item for item in results if item.zone_12 is not None]
    zone_counts = Counter(item.zone_12 for item in zoned if item.zone_12)
    denominator = len(formal_bounces)
    summary = ShotLandingSummary(
        shot_count=len(results),
        available_landing_count=len(measurable),
        formal_bounce_shot_count=denominator,
        spatially_measurable_count=len(measurable),
        no_bounce_before_next_contact_count=sum(item.landing_status == "no_bounce_before_next_contact" for item in results),
        zone_eligible_count=len(zoned),
        spatial_measurability_numerator=len(measurable),
        spatial_measurability_denominator=denominator,
        spatial_measurability_rate=round(len(measurable) / denominator, 4) if denominator else None,
        zone_12_counts=dict(sorted(zone_counts.items())),
    )
    detail = f"已组合 {len(results)} 个 canonical Shot，{len(measurable)} 个落点具有可用球场坐标"
    return ShotLandingsArtifact(
        job_id=job_id,
        video_id=video_id,
        status="available" if shot_events.status == "available" else shot_events.status,
        detail=detail if shot_events.status == "available" else shot_events.detail,
        generated_at=generated_at,
        normalization_profile=normalization_profile,
        zone_profiles=zone_profiles,
        landings=results,
        summary=summary,
        diagnostics=ShotLandingDiagnostics(
            warnings=[],
            missing_segment_ids=sorted(missing_segments),
            missing_event_ids=sorted(missing_events),
        ),
        source_artifacts=["shot-rally-events.v1", "reconstructed-ball-trajectory"],
    )
