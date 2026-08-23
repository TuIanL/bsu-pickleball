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
