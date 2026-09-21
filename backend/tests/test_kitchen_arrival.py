from __future__ import annotations

from app.services.kitchen_arrival_service import (
    EXCLUDED_INSUFFICIENT,
    EXCLUDED_UNCERTAIN_CROSSING,
    KITCHEN_ARRIVAL_REFERENCE_V1,
    _trajectory_points,
    build_kitchen_arrival_artifact,
    classify_player_window,
)


def points(values: list[float], *, detected: bool = True) -> list[dict]:
    return [
        {"timestamp_ms": index * 100, "x": 1.0, "y": value, "detected": detected} for index, value in enumerate(values)
    ]


def test_arrival_requires_real_detected_support_and_marks_already_present() -> None:
    result = classify_player_window(points([4.57] * 10), start_ms=0, end_ms=900, line_y=4.572)
    assert result["state"] == "already_present"
    assert result["arrival_time_ms"] == 0
    assert result["detected_support_ms"] >= KITCHEN_ARRIVAL_REFERENCE_V1.arrival_min_detected_support_ms


def test_first_observation_late_in_rally_is_arrived_not_already_present() -> None:
    result = classify_player_window(
        [{"timestamp_ms": 300 + index * 100, "x": 1.0, "y": 4.57, "detected": True} for index in range(8)],
        start_ms=0,
        end_ms=1000,
        line_y=4.572,
    )
    assert result["state"] == "arrived"
    assert result["arrival_time_ms"] == 300


def test_interpolation_cannot_prove_arrival() -> None:
    reference = KITCHEN_ARRIVAL_REFERENCE_V1.model_copy(
        update={"stable_ms": 200, "arrival_min_detected_support_ms": 200}
    )
    result = classify_player_window(
        points([7.0, 4.57, 4.57, 4.57, 4.57], detected=False),
        start_ms=0,
        end_ms=400,
        line_y=4.572,
        reference=reference,
    )
    assert result["state"] == "excluded"
    assert result["reason"] in {EXCLUDED_INSUFFICIENT, EXCLUDED_UNCERTAIN_CROSSING}


def test_gap_that_could_cross_kitchen_line_is_excluded() -> None:
    reference = KITCHEN_ARRIVAL_REFERENCE_V1.model_copy(update={"not_arrived_max_gap_ms": 1000})
    sample_points = [
        {"timestamp_ms": 0, "x": 1.0, "y": 7.0, "detected": True},
        {"timestamp_ms": 100, "x": 1.0, "y": 7.0, "detected": True},
        {"timestamp_ms": 200, "x": 1.0, "y": 4.57, "detected": False},
        {"timestamp_ms": 300, "x": 1.0, "y": 4.57, "detected": False},
        {"timestamp_ms": 400, "x": 1.0, "y": 4.57, "detected": True},
    ]
    result = classify_player_window(sample_points, start_ms=0, end_ms=400, line_y=4.572, reference=reference)
    assert result["state"] == "excluded"
    assert result["reason"] == EXCLUDED_UNCERTAIN_CROSSING


def test_detected_points_crossing_the_band_are_not_not_arrived() -> None:
    result = classify_player_window(
        [
            {"timestamp_ms": 0, "x": 1.0, "y": 3.0, "detected": True},
            {"timestamp_ms": 900, "x": 1.0, "y": 6.2, "detected": True},
        ],
        start_ms=0,
        end_ms=900,
        line_y=4.572,
        reference=KITCHEN_ARRIVAL_REFERENCE_V1.model_copy(
            update={"min_sample_count": 2, "not_arrived_max_gap_ms": 1000}
        ),
    )
    assert result["state"] == "excluded"
    assert result["reason"] == EXCLUDED_UNCERTAIN_CROSSING


def test_missing_context_is_unavailable_and_never_infers_server_team() -> None:
    artifact = build_kitchen_arrival_artifact(
        job_id="job-1",
        video_id="video-1",
        match_format="doubles",
        rallies=[],
        roster=None,
        binding_audit=None,
        trajectory_payload=None,
    )
    assert artifact.status == "unavailable"
    assert artifact.players == []
    assert artifact.reference.schema_version == "kitchen-arrival-reference.v1"


def test_single_is_not_applicable() -> None:
    artifact = build_kitchen_arrival_artifact(
        job_id="job-1",
        video_id="video-1",
        match_format="singles",
        rallies=[],
        roster=None,
        binding_audit=None,
        trajectory_payload=None,
    )
    assert artifact.status == "not_applicable"


def test_fused_global_id_is_resolved_only_by_explicit_frozen_roster_map() -> None:
    roster = {
        "entries": [
            {"canonical_player_id": "Player_1", "display_name": "A1", "team_id": "A"},
            {"canonical_player_id": "Player_2", "display_name": "A2", "team_id": "A"},
        ]
    }
    audit = {
        "status": "available",
        "entries": [
            {"canonical_player_id": "Player_1", "formal_canonical_player_id": "Player_1", "confirmed": True},
            {"canonical_player_id": "Player_2", "formal_canonical_player_id": "Player_2", "confirmed": True},
        ],
    }
    rally = {
        "rally_id": "r1",
        "ordinal": 1,
        "start_ms": 0,
        "end_ms": 900,
        "status": "available",
        "server_team": "A",
        "team_a_end": "end_a",
        "binding": {"method": "direct_segment_link"},
        "context_hash": "ctx-r1",
    }
    trajectory = {
        "schema_version": "fused_player_trajectory.v2",
        "samples": [
            {
                "global_player_id": "global_player_1",
                "timestamp_seconds": index / 10,
                "x_ft": 5.0,
                "y_ft": 15.0,
                "metric_eligible": True,
                "identity_status": "confirmed_observed",
            }
            for index in range(10)
        ],
    }
    artifact = build_kitchen_arrival_artifact(
        job_id="job-1",
        video_id="video-1",
        match_format="doubles",
        rallies=[rally],
        roster=roster,
        binding_audit=audit,
        trajectory_payload=trajectory,
        trajectory_identity_map={"global_player_1": "Player_1"},
    )
    player = next(item for item in artifact.players if item.player_id == "Player_1")
    assert player.sample_count == 1
    assert player.eligible_count == 1
    assert player.arrived_count == 1


def test_confirmed_recovered_fused_points_can_support_arrival_but_interpolation_cannot() -> None:
    common = {
        "global_player_id": "global_player_1",
        "timestamp_seconds": 0.0,
        "x_ft": 5.0,
        "y_ft": 15.0,
        "metric_eligible": True,
    }
    recovered = [
        {**common, "timestamp_seconds": index / 10, "identity_status": "confirmed_recovered"}
        for index in range(10)
    ]
    interpolated = [
        {**common, "timestamp_seconds": index / 10, "identity_status": "interpolated"}
        for index in range(10)
    ]
    assert sum(point["detected"] for point in _trajectory_points(
        {"samples": recovered}, "Player_1", 0, 900, {"global_player_1": "Player_1"}
    )) == 10
    assert sum(point["detected"] for point in _trajectory_points(
        {"samples": interpolated}, "Player_1", 0, 900, {"global_player_1": "Player_1"}
    )) == 0
