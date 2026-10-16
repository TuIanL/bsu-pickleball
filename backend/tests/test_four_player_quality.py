from copy import deepcopy

from app.vision.player_tracking_engine.four_player_quality import (
    CANONICAL_PLAYERS,
    FourPlayerIdentificationQuality,
    IdentificationThresholds,
    PlayerIdentificationSummary,
    compare_quality,
    evaluate_quality,
    unavailable_quality,
    build_quality_from_joint_artifacts,
)


def _artifact(job_id: str = "job-baseline") -> FourPlayerIdentificationQuality:
    players = {
        player_id: PlayerIdentificationSummary(
            player_id=player_id,
            detection_coverage=0.8,
            canonical_coverage=0.8,
            longest_gap_seconds=1.0,
        )
        for player_id in CANONICAL_PLAYERS
    }
    return FourPlayerIdentificationQuality(
        job_id=job_id,
        algorithm_version="test-v1",
        attempted_ticks=100,
        confirmed_roster_count=4,
        players=players,
    )


def test_quality_schema_requires_all_four_players():
    payload = _artifact().model_dump()
    payload["players"].pop("Player_2")
    try:
        FourPlayerIdentificationQuality.model_validate(payload)
    except ValueError as exc:
        assert "Player_1..Player_4" in str(exc)
    else:
        raise AssertionError("missing Player_2 must fail closed")


def test_evaluate_quality_reports_per_player_absolute_gate():
    artifact = _artifact()
    artifact.players["Player_2"].canonical_coverage = 0.4
    evaluated = evaluate_quality(artifact)
    assert evaluated.verdict == "fail"
    assert evaluated.absolute_gates["Player_2.coverage"] is False


def test_comparison_rejects_silently_weakened_thresholds():
    baseline = evaluate_quality(_artifact())
    candidate = _artifact("job-new")
    candidate.thresholds = IdentificationThresholds(min_player_coverage=0.5, max_gap_seconds=3.0)
    comparison = compare_quality(baseline, candidate)
    assert comparison.verdict == "fail"
    assert comparison.threshold_compatible is False
    assert "candidate_thresholds_weakened" in comparison.reasons


def test_comparison_separates_hard_absolute_and_relative_gates():
    baseline = evaluate_quality(_artifact())
    candidate = _artifact("job-new")
    candidate.players["Player_2"].canonical_coverage = 0.75
    comparison = compare_quality(baseline, candidate)
    assert comparison.hard_invariants_pass is True
    assert comparison.absolute_gates_pass is True
    assert comparison.relative_gates_pass is False
    assert comparison.verdict == "fail"


def test_comparison_uses_minimum_player_and_targeted_p2_regression_contract():
    baseline = _artifact()
    baseline.players["Player_2"].canonical_coverage = 0.72
    baseline.players["Player_2"].longest_gap_seconds = 1.8
    candidate = _artifact("job-new")
    candidate.players["Player_4"].canonical_coverage = 0.79
    candidate.players["Player_4"].longest_gap_seconds = 1.2
    candidate.players["Player_2"].canonical_coverage = 0.9
    candidate.players["Player_2"].longest_gap_seconds = 1.0

    comparison = compare_quality(evaluate_quality(baseline), evaluate_quality(candidate))

    assert comparison.relative_gates_pass is True
    assert comparison.verdict == "pass"


def test_old_job_without_artifact_is_structured_unavailable():
    artifact = unavailable_quality("legacy-job", "artifact missing")
    assert artifact.status == "unavailable"
    assert artifact.verdict == "unavailable"


def test_quality_round_trip_is_stable():
    payload = deepcopy(evaluate_quality(_artifact()).model_dump(mode="json"))
    assert FourPlayerIdentificationQuality.model_validate(payload).model_dump(mode="json") == payload


def test_joint_quality_excludes_ambiguous_and_ineligible_samples_from_coverage():
    roster = {
        "confirmed_player_count": 4,
        "players": [
            {"global_player_id": f"global_{index}", "player_id": f"Player_{index}"}
            for index in range(1, 5)
        ],
    }
    samples = []
    for index in range(1, 5):
        for frame in range(3):
            samples.append({
                "global_player_id": f"global_{index}",
                "timestamp_seconds": float(frame),
                "reference_frame_index": frame,
                "metric_eligible": not (index == 2 and frame > 0),
                "identity_status": "ambiguous" if index == 2 and frame == 1 else "confirmed_observed",
                "view_observations": {},
            })

    artifact = build_quality_from_joint_artifacts(
        job_id="job-accepted-only",
        algorithm_version="test",
        trajectory={"samples": samples},
        roster=roster,
    )

    assert artifact.players["Player_1"].canonical_coverage == 1.0
    assert artifact.players["Player_2"].canonical_coverage == 1 / 3
    assert artifact.players["Player_2"].ambiguous_count == 1
    assert artifact.players["Player_2"].quarantined_count == 2


def test_unconfirmed_frozen_mapping_preserves_raw_local_and_global_funnel_counts():
    slots = [
        {
            "canonical_player_id": f"Player_{index}",
            "canonical_end": "end_a" if index <= 2 else "end_b",
            "confirmed": False,
            "reason": "bootstrap_binding_no_simultaneous_observation",
        }
        for index in range(1, 5)
    ]
    artifact = build_quality_from_joint_artifacts(
        job_id="job-unconfirmed",
        trajectory={"samples": [{
            "global_player_id": "global_player_1",
            "timestamp_seconds": 18.0,
            "take_timestamp_ms": 18_000,
            "y_ft": 8.0,
            "metric_eligible": True,
            "identity_status": "confirmed_observed",
            "view_observations": {
                "cam_1": {"source_track_id": 11, "view_status": "available"},
            },
        }]},
        roster={
            "confirmed_player_count": 4,
            "players": [{"global_player_id": "global_player_1", "player_id": None, "mapping_confirmed": False}],
        },
        runtime_diagnostics={
            "frozen_roster": {
                "confirmed_count": 0,
                "anchor_binding_audit": {"entries": slots},
            },
            "perception_funnel": {
                "per_view": {"cam_1": {
                    "available_ticks": 1,
                    "raw_detection_count": 8,
                    "roi_filtered_base_count": 6,
                    "local_track_count": 4,
                    "local_candidate_count": 2,
                    "global_candidate_observation_count": 2,
                }},
                "per_canonical_end": {"end_a": {
                    "global_input_observation_count": 3,
                    "global_candidate_observation_count": 1,
                    "assigned_observation_count": 2,
                }},
            },
        },
    )

    assert artifact.players["Player_1"].canonical_ticks == 0
    assert artifact.confirmed_roster_count == 0
    assert artifact.funnel.base_detection_ticks == 1
    assert artifact.funnel.tracker_fragments == 1
    assert artifact.per_view_funnel["cam_1"]["raw_detection_count"] == 8
    assert artifact.per_view_funnel["cam_1"]["local_track_count"] == 4
    assert artifact.per_canonical_end_funnel["end_a"]["metric_eligible_sample_count"] == 1
    assert artifact.identity_slots["Player_1"]["status"] == "unconfirmed"
    assert artifact.hard_invariants["two_confirmed_players_per_canonical_end"] is False


def test_processed_timeline_catches_full_player_dropout_after_last_trajectory_sample():
    slots = [
        {
            "canonical_player_id": f"Player_{index}",
            "formal_canonical_player_id": f"Player_{index}",
            "canonical_end": "end_a" if index <= 2 else "end_b",
            "confirmed": True,
        }
        for index in range(1, 5)
    ]
    samples = [
        {
            "global_player_id": f"global_player_{index}",
            "timestamp_seconds": float(timestamp),
            "take_timestamp_ms": timestamp * 1000,
            "y_ft": 5.0 if index <= 2 else 39.0,
            "metric_eligible": True,
            "identity_status": "confirmed_observed",
            "view_observations": {},
        }
        for index in range(1, 5)
        for timestamp in (0, 1, 2)
    ]
    artifact = build_quality_from_joint_artifacts(
        job_id="job-tail-dropout",
        trajectory={"samples": samples},
        roster={
            "confirmed_player_count": 4,
            "players": [
                {"global_player_id": f"global_player_{index}", "player_id": f"Player_{index}", "mapping_confirmed": True}
                for index in range(1, 5)
            ],
        },
        runtime_diagnostics={
            "frozen_roster": {
                "confirmed_count": 4,
                "anchor_binding_audit": {"entries": slots},
            },
            "processed_tick_count": 6,
            "processed_tick_timestamps_ms": [0, 1000, 2000, 3000, 4000, 5000],
        },
    )

    assert artifact.attempted_ticks == 6
    assert artifact.players["Player_1"].canonical_coverage == 0.5
    assert artifact.players["Player_1"].longest_gap_seconds == 3.0
    assert artifact.absolute_gates["Player_1.longest_gap"] is False
    assert artifact.verdict == "fail"


def _dual_source_inputs(*, roster_confirmed: bool, audit_confirmed: bool):
    """构造 roster.json 与 anchor_binding_audit 对Player_4 给出互斥结论的输入。"""
    slots = []
    for index in range(1, 5):
        player_id = f"Player_{index}"
        confirmed = audit_confirmed if player_id == "Player_4" else True
        slots.append({
            "canonical_player_id": player_id,
            "canonical_end": "end_a" if index <= 2 else "end_b",
            "confirmed": confirmed,
            "formal_canonical_player_id": player_id if confirmed else None,
            "global_player_id": f"global_player_{index}" if confirmed else "global_player_2",
            "reason": None if confirmed else "anchor_global_end_conflict",
        })
    roster = {
        "confirmed_player_count": 4,
        "players": [
            {
                "global_player_id": f"global_player_{index}",
                "player_id": f"Player_{index}",
                "mapping_confirmed": roster_confirmed if index == 4 else True,
            }
            for index in range(1, 5)
        ],
    }
    samples = [
        {
            "global_player_id": f"global_player_{index}",
            "timestamp_seconds": float(frame),
            "metric_eligible": True,
            "identity_status": "confirmed_observed",
            "view_observations": {},
        }
        for index in range(1, 5)
        for frame in range(3)
    ]
    runtime_diagnostics = {
        "frozen_roster": {"confirmed_count": 4, "anchor_binding_audit": {"entries": slots}},
        "processed_tick_count": 3,
        "processed_tick_timestamps_ms": [0, 1000, 2000],
    }
    return samples, roster, runtime_diagnostics


def test_audit_overrides_roster_json_when_mapping_sources_disagree():
    """7.3：两个来源冲突时以 anchor_binding_audit 为唯一权威来源。"""
    samples, roster, runtime_diagnostics = _dual_source_inputs(
        roster_confirmed=True,
        audit_confirmed=False,
    )

    artifact = build_quality_from_joint_artifacts(
        job_id="job-dual-source",
        algorithm_version="test",
        trajectory={"samples": samples},
        roster=roster,
        runtime_diagnostics=runtime_diagnostics,
    )

    # 审计说未确认 -> 两个口径必须一致地报告未确认
    assert artifact.mapping_confirmed_by_player["Player_4"] is False
    assert artifact.identity_slots["Player_4"]["status"] == "unconfirmed"
    assert artifact.identity_slots["Player_4"]["metric_eligible_sample_count"] == 0
    # 冲突本身必须被留证，而不是静默取其一
    assert "Player_4" in artifact.mapping_conflict_with_audit
    conflict = artifact.mapping_conflict_with_audit["Player_4"]
    assert conflict["audit_confirmed"] is False
    assert conflict["roster_json_confirmed"] is True
    assert conflict["audit_reason"] == "anchor_global_end_conflict"
    assert artifact.identity_slots["Player_4"]["conflicts_with_roster_json"] is True


def test_mapping_source_conflict_fails_identity_single_source_gate():
    """7.3：双源冲突无法判定谁为真，verdict 必须 fail-closed。"""
    samples, roster, runtime_diagnostics = _dual_source_inputs(
        roster_confirmed=True,
        audit_confirmed=False,
    )

    artifact = evaluate_quality(build_quality_from_joint_artifacts(
        job_id="job-dual-source-fail",
        algorithm_version="test",
        trajectory={"samples": samples},
        roster=roster,
        runtime_diagnostics=runtime_diagnostics,
    ))

    assert artifact.hard_invariants["identity_audit_single_source"] is False
    assert "identity_audit_single_source" in artifact.failure_reasons
    assert artifact.verdict == "fail"


def test_consistent_sources_pass_identity_single_source_gate():
    """7.3：两来源一致时不应误报冲突，且确认槽位照常计入覆盖。"""
    samples, roster, runtime_diagnostics = _dual_source_inputs(
        roster_confirmed=True,
        audit_confirmed=True,
    )

    artifact = evaluate_quality(build_quality_from_joint_artifacts(
        job_id="job-single-source",
        algorithm_version="test",
        trajectory={"samples": samples},
        roster=roster,
        runtime_diagnostics=runtime_diagnostics,
    ))

    assert artifact.mapping_conflict_with_audit == {}
    assert artifact.hard_invariants["identity_audit_single_source"] is True
    assert artifact.mapping_confirmed_by_player["Player_4"] is True
    assert artifact.identity_slots["Player_4"]["status"] == "confirmed"
    assert artifact.identity_slots["Player_4"]["metric_eligible_sample_count"] == 3
    assert "identity_audit_single_source" not in artifact.failure_reasons


def test_audit_confirmed_requires_formal_slot_self_reference():
    """7.3：`confirmed=True` 但 formal 槽位回指他人时不得计为该槽位确认。"""
    slots = [
        {
            "canonical_player_id": "Player_1",
            "canonical_end": "end_a",
            "confirmed": True,
            # 回指 Player_2 -> Player_1 不得被计为 confirmed
            "formal_canonical_player_id": "Player_2",
            "global_player_id": "global_player_1",
        }
    ]
    artifact = build_quality_from_joint_artifacts(
        job_id="job-formal-mismatch",
        algorithm_version="test",
        trajectory={"samples": []},
        roster={
            "confirmed_player_count": 1,
            "players": [{
                "global_player_id": "global_player_1",
                "player_id": "Player_1",
                "mapping_confirmed": True,
            }],
        },
        runtime_diagnostics={
            "frozen_roster": {"confirmed_count": 1, "anchor_binding_audit": {"entries": slots}},
        },
    )

    assert artifact.mapping_confirmed_by_player["Player_1"] is False
    assert artifact.identity_slots["Player_1"]["status"] == "unconfirmed"
    # 该冲突同样必须留证
    assert "Player_1" in artifact.mapping_conflict_with_audit
