from __future__ import annotations

import json
from pathlib import Path

from app.vision.pickleball_game_analysis.ball_semantic_search_policy import (
    BallSearchPolicy,
    BallSemanticPolicyConfig,
    SemanticAuthority,
    SemanticPhase,
    SemanticTimelineProvider,
)
from app.vision.pickleball_game_analysis.semantic_boundary_calibration import (
    SEMANTIC_BOUNDARY_EVAL_SCHEMA_VERSION,
    SemanticEvidenceLedger,
    SemanticEvidenceSource,
    build_semantic_boundary_evaluation_payload,
    compute_boundary_evaluation_metrics,
    replay_semantic_boundary_cases,
)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "ball_semantic" / "semantic_boundary_calibration_cases.json"


def _fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_evidence_ledger_preserves_provenance_and_deterministic_ids():
    ledger = SemanticEvidenceLedger()
    first = ledger.add_tick(
        1000,
        {
            "timeline_event_type": "rally",
            "player_motion_pixels": 24,
            "serve_candidate_confidence": 0.72,
            "evidence_provenance": {"origin": "runtime_detector", "camera": "cam_1"},
        },
        authority=SemanticAuthority.ALGORITHM,
    )
    second_ledger = SemanticEvidenceLedger()
    second = second_ledger.add_tick(
        1000,
        {
            "timeline_event_type": "rally",
            "player_motion_pixels": 24,
            "serve_candidate_confidence": 0.72,
            "evidence_provenance": {"origin": "runtime_detector", "camera": "cam_1"},
        },
        authority=SemanticAuthority.ALGORITHM,
    )

    assert {record.source for record in first} == {
        SemanticEvidenceSource.ALGORITHMIC,
        SemanticEvidenceSource.OBSERVED,
    }
    assert [record.evidence_id for record in first] == [record.evidence_id for record in second]
    assert all(record.provenance["detail"]["origin"] == "runtime_detector" for record in first)


def test_evidence_freshness_blocks_stale_boundary_confirmation():
    provider = SemanticTimelineProvider.from_events(
        [],
        config=BallSemanticPolicyConfig(min_confirm_ticks=1, grace_window_sec=0.0),
    )
    provider.snapshot(0, evidence={"rally_active": True, "rally_confidence": 0.8})
    stale = provider.snapshot(
        1000,
        evidence={
            "rally_end_evidence_count": 3,
            "semantic_evidence_records": [
                {
                    "kind": "rally_end_signal",
                    "source": "algorithmic",
                    "value": 3,
                    "fresh_until_ms": 100,
                }
            ],
        },
    )

    assert stale.phase == SemanticPhase.RALLY_END_CANDIDATE
    assert stale.boundary_status == "pending_end"
    assert stale.adjudication_reason == "weak_or_partial_end_evidence"
    assert stale.evidence_ids


def test_pending_end_requires_rescue_corroboration_and_can_be_rescued():
    config = BallSemanticPolicyConfig(rescue_min_consecutive_ticks=2)
    provider = SemanticTimelineProvider.from_events([], config=config)
    provider.snapshot(1000, evidence={"rally_active": True, "rally_confidence": 0.9})
    pending = provider.snapshot(1100, evidence={"rally_end_evidence_count": 1})
    first_active = provider.snapshot(
        1200,
        evidence={"rally_active": True, "valid_ball_motion": True, "ball_motion_pixels": 25},
    )
    rescued = provider.snapshot(
        1300,
        evidence={"rally_active": True, "valid_ball_motion": True, "ball_motion_pixels": 28},
    )

    assert pending.boundary_status == "pending_end"
    assert first_active.boundary_status == "pending_end"
    assert first_active.phase == SemanticPhase.RALLY_ACTIVE
    assert rescued.boundary_status == "rescued_active"
    assert rescued.rescue_reason == "active_ball_and_player_evidence_reappeared"
    assert rescued.contradiction_evidence_ids


def test_fixture_replay_is_deterministic_and_covers_boundary_semantics():
    fixture = _fixture()
    first = replay_semantic_boundary_cases(fixture["cases"])
    second = replay_semantic_boundary_cases(fixture["cases"])

    assert first == second
    assert len(first) == 3
    for result, case in zip(first, fixture["cases"]):
        assert result["evidence_ledger"]
        for snapshot, probe in zip(result["snapshots"], case["probes"]):
            assert snapshot["phase"] == probe["expected_phase"], case["id"]
            assert snapshot["boundary_status"] == probe["expected_boundary_status"], case["id"]


def test_boundary_metrics_and_payload_are_versioned():
    provider = SemanticTimelineProvider.from_events(
        [{"id": "rally-start", "event_type": "rally_start", "timestamp_ms": 100, "source": "manual"}]
    )
    snapshot = provider.snapshot(100)
    decision = BallSearchPolicy(provider.config).evaluate(snapshot, raw_candidate_count=2)
    metrics = compute_boundary_evaluation_metrics(
        [snapshot],
        [decision],
        reference_boundaries=[{"kind": "start", "timestamp_ms": 100}],
    )
    payload = build_semantic_boundary_evaluation_payload(
        job_id="job-boundary-test",
        take_id="take-20260720",
        snapshots=[snapshot],
        decisions=[decision],
        evidence_ledger=provider.evidence_ledger.to_list(),
        diagnostics={"policy_version": provider.config.policy_version, "policy_mode": "shadow"},
        reference_boundaries=[{"kind": "start", "timestamp_ms": 100}],
        frame_stride=2,
    )

    assert metrics["boundary_precision"] == 1.0
    assert metrics["boundary_recall"] == 1.0
    assert payload["schema_version"] == SEMANTIC_BOUNDARY_EVAL_SCHEMA_VERSION
    assert payload["artifact_kind"] == "ball_semantic_boundary_eval"
    assert payload["source"]["frame_stride"] == 2
    assert payload["ticks"][0]["decision"]["boundary_status"] == "confirmed_start"


def test_real_20260720_validation_summary_is_bound_to_dual_capture():
    summary_path = FIXTURE_PATH.with_name("semantic_boundary_real_20260720_summary.json")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert summary["validation_mode"] == "real_capture_replay"
    assert summary["capture_date"] == "2026-07-20"
    assert summary["source_media"] == ["174_merged.mp4", "175_merged.mp4"]
    assert summary["metrics"]["boundary_precision"] == 1.0
    assert summary["metrics"]["boundary_recall"] == 1.0
    assert summary["metrics"]["false_suppression_count"] == 0
    assert summary["metrics"]["cross_segment_contamination_count"] == 0
