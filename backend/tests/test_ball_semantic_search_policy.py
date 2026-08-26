from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from app.services.analysis_pipeline import AnalysisPipeline, _BallRunContext
from app.vision.pickleball_game_analysis.ball_tracker import BallTracker, BallTrackerConfig
from app.vision.pickleball_game_analysis.schemas import BallCandidate
from app.vision.pickleball_game_analysis.ball_semantic_search_policy import (
    BallBoundaryAction,
    BallPolicyAction,
    BallSearchPolicy,
    BallSemanticPolicyConfig,
    MatchSemanticSnapshot,
    SemanticAuthority,
    SemanticPhase,
    SemanticPolicyMode,
    SemanticTimelineProvider,
    build_semantic_timeline_payload,
    compute_semantic_shadow_metrics,
    serve_candidate_semantic_snapshot,
)


class _Detector:
    def __init__(self, candidates):
        self.candidates = list(candidates)
        self.calls = 0

    def detect(self, _frame, conf=0.18):
        self.calls += 1
        return list(self.candidates)


def _ball_context(*, mode=SemanticPolicyMode.SHADOW, enforce=False):
    detector = _Detector([BallCandidate(120, 120, 0.9, width=8, height=8)])
    tracker = BallTracker(
        detector=detector,
        config=BallTrackerConfig(
            tentative_min_hits=1,
            lock_min_hits=1,
            max_box_area_ratio=0.01,
        ),
    )
    config = BallSemanticPolicyConfig(
        mode=mode,
        enforce_authoritative_non_play=enforce,
    )
    provider = SemanticTimelineProvider.from_events(
        [{"id": "np-1", "event_type": "non_play_start", "timestamp_ms": 0, "source": "manual"}],
        config=config,
    )
    return _BallRunContext(
        tracker=tracker,
        semantic_provider=provider,
        semantic_policy=BallSearchPolicy(config),
    ), detector, provider


def test_unknown_snapshot_falls_back_to_legacy_behavior():
    snapshot = MatchSemanticSnapshot.unknown(1000)
    decision = BallSearchPolicy().evaluate(snapshot, raw_candidate_count=2)

    assert snapshot.phase == SemanticPhase.UNKNOWN
    assert decision.action == BallPolicyAction.FALLBACK
    assert decision.tracker_update_allowed is True
    assert decision.formal_publish_allowed is True
    assert decision.semantic_fallback is True


def test_shadow_non_play_records_suppression_recommendation_without_changing_effective_behavior():
    provider = SemanticTimelineProvider.from_events(
        [{"id": "np-1", "event_type": "non_play_start", "timestamp_ms": 1000, "source": "manual"}],
    )
    snapshot = provider.snapshot(1500)
    decision = BallSearchPolicy().evaluate(snapshot, raw_candidate_count=1)

    assert snapshot.phase == SemanticPhase.NON_PLAY_CONFIRMED
    assert snapshot.authority == SemanticAuthority.MANUAL
    assert decision.action == BallPolicyAction.SOFT_GATE
    assert decision.recommended_formal_publish is False
    assert decision.formal_publish_allowed is True
    assert decision.diagnostics["shadow_effective_behavior"] is True


def test_enforced_authoritative_non_play_blocks_formal_candidate_but_keeps_raw_evidence():
    provider = SemanticTimelineProvider.from_events(
        [{"id": "np-1", "event_type": "non_play_start", "timestamp_ms": 1000, "source": "corrected"}],
        config=BallSemanticPolicyConfig(
            mode=SemanticPolicyMode.ENFORCED,
            enforce_authoritative_non_play=True,
        ),
    )
    snapshot = provider.snapshot(1500)
    decision = BallSearchPolicy(provider.config).evaluate(snapshot, raw_candidate_count=3)

    assert decision.action == BallPolicyAction.SUPPRESS_FORMAL
    assert decision.tracker_update_allowed is False
    assert decision.formal_publish_allowed is False
    assert decision.diagnostics["raw_candidate_count"] == 3


def test_pre_serve_does_not_accept_stationary_handheld_ball():
    provider = SemanticTimelineProvider.from_events(
        [],
        config=BallSemanticPolicyConfig(),
    )
    snapshot = provider.snapshot(2000, evidence={"serve_candidate_confidence": 0.6})
    decision = BallSearchPolicy().evaluate(snapshot)

    assert snapshot.phase == SemanticPhase.PRE_SERVE
    assert decision.action == BallPolicyAction.SERVE_REACQUIRE
    assert decision.accept_stationary_candidate is False


def test_post_rally_can_reacquire_serve_before_next_rally():
    provider = SemanticTimelineProvider.from_events(
        [
            {"id": "np-1", "event_type": "non_play_start", "timestamp_ms": 0, "source": "manual"},
            {"id": "np-2", "event_type": "non_play_end", "timestamp_ms": 1000, "source": "manual"},
        ]
    )

    prepare = provider.snapshot(1500, evidence={"serve_candidate_confidence": 0.60})
    assert prepare.phase == SemanticPhase.PRE_SERVE
    assert BallSearchPolicy().evaluate(prepare).action == BallPolicyAction.SERVE_REACQUIRE

    armed = provider.snapshot(
        1600,
        evidence={"serve_candidate_confidence": 0.60, "serve_armed": True},
    )
    assert armed.phase == SemanticPhase.SERVE_ARMED
    assert BallSearchPolicy().evaluate(armed).action == BallPolicyAction.SERVE_REACQUIRE


def test_single_weak_end_signal_does_not_end_rally():
    provider = SemanticTimelineProvider.from_events([])
    first = provider.snapshot(1000, evidence={"rally_active": True, "rally_confidence": 0.8})
    assert first.phase == SemanticPhase.RALLY_ACTIVE

    next_snapshot = provider.snapshot(1100, evidence={"rally_end_evidence_count": 1})
    assert next_snapshot.phase == SemanticPhase.RALLY_ACTIVE

    candidate = provider.snapshot(1200, evidence={"rally_end_evidence_count": 2})
    assert candidate.phase == SemanticPhase.RALLY_END_CANDIDATE


def test_payload_is_replayable_and_serializable():
    snapshot = MatchSemanticSnapshot.unknown(0)
    decision = BallSearchPolicy().evaluate(snapshot)
    payload = build_semantic_timeline_payload(
        job_id="job-1",
        take_id="take-1",
        snapshots=[snapshot],
        decisions=[decision],
        frame_stride=2,
        timestamp_provenance={"clock": "CanonicalAnalysisClock"},
    )

    assert payload["schema_version"] == "ball_semantic_timeline.v1"
    assert payload["artifact_kind"] == "ball_semantic_timeline"
    assert payload["timestamp_provenance"]["time_unit"] == "milliseconds"
    assert payload["diagnostics"]["semantic_shadow_metrics"]["unknown_ratio"] == 1.0
    assert payload["snapshots"][0]["phase"] == "UNKNOWN"
    assert payload["decisions"][0]["action"] == "fallback"


def test_payload_preserves_rollout_boundary_and_before_after_diagnostics():
    config = BallSemanticPolicyConfig(
        mode=SemanticPolicyMode.ENFORCED,
        enforced_rollout_enabled=True,
        rollout_id="real-take-20260720",
    )
    provider = SemanticTimelineProvider.from_events(
        [{"id": "np-1", "event_type": "non_play_start", "timestamp_ms": 0, "source": "manual"}],
        config=config,
    )
    snapshot = provider.snapshot(100)
    decision = BallSearchPolicy(config).evaluate(snapshot, raw_candidate_count=3)
    payload = build_semantic_timeline_payload(
        job_id="job-enforced",
        take_id="take-20260720",
        snapshots=[snapshot],
        decisions=[decision],
        diagnostics={
            "rollout_id": config.rollout_id,
            "boundary_events": [{"action_id": snapshot.boundary_action_id, "applied": True}],
            "formal_candidate_count_before": 3,
            "formal_candidate_count_after": 0,
        },
    )

    assert payload["diagnostics"]["rollout_id"] == "real-take-20260720"
    assert payload["diagnostics"]["boundary_events"][0]["action_id"] == snapshot.boundary_action_id
    assert payload["decisions"][0]["boundary_action"] == "seal_formal_segment"
    assert payload["decisions"][0]["formal_candidate_count_after"] == 0
    assert payload["diagnostics"]["semantic_shadow_metrics"]["hard_gate_tick_count"] == 1


def test_semantic_fixture_replay_covers_non_play_serve_rally_loss_and_post_rally():
    fixture_path = Path(__file__).parent / "fixtures" / "ball_semantic" / "semantic_search_cases.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert fixture["schema_version"] == "ball_semantic_fixture.v1"

    for case in fixture["cases"]:
        provider = SemanticTimelineProvider.from_events(case["events"])
        policy = BallSearchPolicy(provider.config)
        for probe in case["probes"]:
            snapshot = provider.snapshot(probe["timestamp_ms"], evidence=probe.get("evidence"))
            decision = policy.evaluate(snapshot, raw_candidate_count=2)
            assert snapshot.phase.value == probe["expected_phase"], case["id"]
            assert decision.action.value == probe["expected_action"], case["id"]


def test_enforced_gating_fixture_replays_boundary_and_fail_open_contract():
    fixture_path = Path(__file__).parent / "fixtures" / "ball_semantic" / "semantic_enforced_gating_cases.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert fixture["schema_version"] == "ball_semantic_enforced_fixture.v1"

    config = BallSemanticPolicyConfig(
        mode=SemanticPolicyMode.ENFORCED,
        enforced_rollout_enabled=True,
        rollout_id="fixture-enforced",
    )
    for case in fixture["cases"]:
        provider = SemanticTimelineProvider.from_events(case["events"], config=config)
        policy = BallSearchPolicy(config)
        for probe in case["probes"]:
            snapshot = provider.snapshot(probe["timestamp_ms"], evidence=probe.get("evidence"))
            decision = policy.evaluate(snapshot, raw_candidate_count=2)
            assert snapshot.phase.value == probe["expected_phase"], case["id"]
            assert decision.action.value == probe["expected_action"], case["id"]
            assert snapshot.boundary_action.value == probe["expected_boundary"], case["id"]
            assert decision.hard_gate_active is probe["expected_hard_gate"], case["id"]


def test_shadow_and_enforced_replay_share_one_detector_candidate_pass():
    shadow_context, shadow_detector, _ = _ball_context(mode=SemanticPolicyMode.SHADOW)
    enforced_context, enforced_detector, _ = _ball_context(
        mode=SemanticPolicyMode.ENFORCED,
        enforce=True,
    )
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    for context in (shadow_context, enforced_context):
        AnalysisPipeline._process_ball_frame(
            context=context,
            frame=frame,
            frame_index=0,
            timestamp=0.0,
            homography=None,
            frame_width=640,
            frame_height=480,
        )

    assert shadow_detector.calls == 1
    assert enforced_detector.calls == 1
    assert shadow_context.semantic_raw_candidate_count == enforced_context.semantic_raw_candidate_count == 1
    assert shadow_context.samples[0].source != "semantic_warm"
    assert shadow_context.samples[0].diagnostics["formal_candidate_count_after"] == 1
    assert enforced_context.samples[0].publication_eligible is False
    assert enforced_context.samples[0].quality_status == "diagnostic_only"


def test_shadow_metrics_report_suppression_unknown_and_serve_latency():
    snapshots = [
        MatchSemanticSnapshot.unknown(0),
        MatchSemanticSnapshot(
            take_timestamp_ms=1000,
            phase=SemanticPhase.NON_PLAY_CONFIRMED,
            phase_confidence=1.0,
            authority=SemanticAuthority.MANUAL,
            semantic_fallback=False,
        ),
        MatchSemanticSnapshot(
            take_timestamp_ms=2000,
            phase=SemanticPhase.SERVE_ARMED,
            phase_confidence=0.8,
            authority=SemanticAuthority.ALGORITHM,
            semantic_fallback=False,
        ),
    ]
    decisions = [
        BallSearchPolicy().evaluate(snapshots[0], raw_candidate_count=2),
        BallSearchPolicy().evaluate(snapshots[1], raw_candidate_count=3),
        BallSearchPolicy().evaluate(snapshots[2], raw_candidate_count=1),
    ]

    metrics = compute_semantic_shadow_metrics(
        snapshots,
        decisions,
        duration_seconds=60.0,
        accepted_timestamps_ms=[2500],
    )

    assert metrics["raw_candidate_count"] == 6
    assert metrics["recommended_suppressed_candidate_count"] == 3
    assert metrics["effective_suppressed_candidate_count"] == 0
    assert metrics["non_play_candidate_count_per_minute"] == 3.0
    assert metrics["unknown_ratio"] == 1 / 3
    assert metrics["serve_to_first_reliable_observation_latency_ms"] == 500.0


def test_non_play_end_returns_post_rally_until_next_serve_evidence():
    provider = SemanticTimelineProvider.from_events(
        [
            {"id": "np-1", "event_type": "non_play_start", "timestamp_ms": 1000, "source": "manual"},
            {"id": "np-2", "event_type": "non_play_end", "timestamp_ms": 2000, "source": "manual"},
        ]
    )

    snapshot = provider.snapshot(2500)

    assert snapshot.phase == SemanticPhase.POST_RALLY
    assert snapshot.authority == SemanticAuthority.MANUAL


def test_timeline_can_leave_non_play_for_rally_and_reenter_non_play():
    provider = SemanticTimelineProvider.from_events(
        [
            {"id": "np-1", "event_type": "non_play_start", "timestamp_ms": 0, "source": "manual"},
            {"id": "np-2", "event_type": "non_play_end", "timestamp_ms": 100, "source": "manual"},
            {"id": "rally-1", "event_type": "rally_start", "timestamp_ms": 100, "source": "manual"},
            {"id": "rally-1-end", "event_type": "rally_end", "timestamp_ms": 200, "source": "manual"},
            {"id": "np-3", "event_type": "non_play_start", "timestamp_ms": 200, "source": "manual"},
        ]
    )

    assert provider.snapshot(50).phase == SemanticPhase.NON_PLAY_CONFIRMED
    assert provider.snapshot(150).phase == SemanticPhase.RALLY_ACTIVE
    assert provider.snapshot(250).phase == SemanticPhase.NON_PLAY_CONFIRMED


def test_serve_detector_candidate_is_evidence_not_a_rally_result():
    snapshot = serve_candidate_semantic_snapshot(
        {
            "id": "serve-1",
            "timestamp_seconds": 3.2,
            "confidence": 0.81,
            "reason": "pre-still + receiver waiting",
            "source_signals": ["tracking", "roi"],
        }
    )

    assert snapshot.phase == SemanticPhase.SERVE_ARMED
    assert snapshot.authority == SemanticAuthority.ALGORITHM
    assert snapshot.evidence["serve_candidate_id"] == "serve-1"
    assert snapshot.policy_decision == BallPolicyAction.SERVE_REACQUIRE


def test_single_view_shadow_mode_keeps_formal_tracker_behavior():
    context, detector, _provider = _ball_context()
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    AnalysisPipeline._process_ball_frame(
        context=context,
        frame=frame,
        frame_index=0,
        timestamp=0.0,
        homography=None,
        frame_width=640,
        frame_height=480,
    )

    assert detector.calls == 1
    assert context.samples[0].accepted is True
    assert context.samples[0].diagnostics["semantic_decision"]["policy_mode"] == "shadow"
    assert context.semantic_suppressed_count == 0


def test_single_view_without_semantic_provider_keeps_legacy_path_for_rollback():
    detector = _Detector([BallCandidate(120, 120, 0.9, width=8, height=8)])
    tracker = BallTracker(
        detector=detector,
        config=BallTrackerConfig(tentative_min_hits=1, lock_min_hits=1, max_box_area_ratio=0.01),
    )
    context = _BallRunContext(tracker=tracker)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    AnalysisPipeline._process_ball_frame(
        context=context,
        frame=frame,
        frame_index=0,
        timestamp=0.0,
        homography=None,
        frame_width=640,
        frame_height=480,
    )

    assert detector.calls == 1
    assert context.samples[0].accepted is True
    assert context.semantic_snapshots == []
    assert context.semantic_decisions == []


def test_single_view_enforced_non_play_does_not_pollute_blacklist():
    context, detector, provider = _ball_context(
        mode=SemanticPolicyMode.ENFORCED,
        enforce=True,
    )
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    AnalysisPipeline._process_ball_frame(
        context=context,
        frame=frame,
        frame_index=0,
        timestamp=0.0,
        homography=None,
        frame_width=640,
        frame_height=480,
    )

    assert detector.calls == 1
    assert context.samples[0].accepted is False
    assert context.samples[0].quality_status == "diagnostic_only"
    assert context.semantic_suppressed_count == 1
    assert context.tracker._stationary_blacklist == {}


def test_semantic_boundary_actions_are_edge_triggered_and_replayable():
    config = BallSemanticPolicyConfig(
        mode=SemanticPolicyMode.ENFORCED,
        enforced_rollout_enabled=True,
    )
    provider = SemanticTimelineProvider.from_events(
        [
            {"id": "np-1", "event_type": "non_play_start", "timestamp_ms": 0, "source": "manual"},
            {"id": "np-2", "event_type": "non_play_end", "timestamp_ms": 1000, "source": "manual"},
            {"id": "rally-1", "event_type": "rally_start", "timestamp_ms": 1200, "source": "corrected"},
        ],
        config=config,
    )

    first = provider.snapshot(100)
    repeated = provider.snapshot(200)
    prepare = provider.snapshot(1100, evidence={"serve_candidate_confidence": 0.60})
    armed = provider.snapshot(1150, evidence={"serve_candidate_confidence": 0.60, "serve_armed": True})
    active = provider.snapshot(1250)

    assert first.boundary_action == BallBoundaryAction.SEAL_FORMAL_SEGMENT
    assert first.boundary_action_id == "semantic-boundary:np-1:NON_PLAY_CONFIRMED"
    assert repeated.boundary_action == BallBoundaryAction.NONE
    assert prepare.boundary_action == BallBoundaryAction.WARM_REACQUIRE
    assert armed.boundary_action == BallBoundaryAction.SERVE_REACQUIRE
    assert active.boundary_action == BallBoundaryAction.OPEN_FORMAL_SEGMENT
    assert active.formal_segment_lifecycle.value == "open"


def test_authoritative_rally_end_generates_seal_action_without_repeated_reset():
    provider = SemanticTimelineProvider.from_events(
        [
            {"id": "rally-1", "event_type": "rally_start", "timestamp_ms": 0, "source": "manual"},
            {"id": "rally-1-end", "event_type": "rally_end", "timestamp_ms": 1000, "source": "manual"},
        ]
    )

    active = provider.snapshot(500)
    ended = provider.snapshot(1000)
    repeated = provider.snapshot(1100)

    assert active.phase == SemanticPhase.RALLY_ACTIVE
    assert ended.boundary_action == BallBoundaryAction.SEAL_FORMAL_SEGMENT
    assert ended.boundary_action_id == "semantic-boundary:rally-1-end:POST_RALLY"
    assert repeated.boundary_action == BallBoundaryAction.NONE


def test_tracker_semantic_boundary_reset_is_idempotent_and_opens_new_segment():
    detector = _Detector([BallCandidate(120, 120, 0.9, width=8, height=8)])
    tracker = BallTracker(
        detector=detector,
        config=BallTrackerConfig(tentative_min_hits=1, lock_min_hits=1, max_box_area_ratio=0.01),
    )
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    tracker.update(frame, frame_index=0, timestamp_sec=0.0)
    assert tracker.semantic_lifecycle_snapshot()["trajectory_length"] == 1

    sealed = tracker.apply_semantic_boundary(
        BallBoundaryAction.SEAL_FORMAL_SEGMENT.value,
        "boundary-1",
        timestamp_sec=1.0,
    )
    duplicate = tracker.apply_semantic_boundary(
        BallBoundaryAction.SEAL_FORMAL_SEGMENT.value,
        "boundary-1",
        timestamp_sec=1.1,
    )
    opened = tracker.apply_semantic_boundary(
        BallBoundaryAction.OPEN_FORMAL_SEGMENT.value,
        "boundary-2",
        timestamp_sec=2.0,
    )

    assert sealed["applied"] is True
    assert sealed["after"]["formal_segment_lifecycle"] == "sealed"
    assert sealed["after"]["trajectory_length"] == 0
    assert duplicate["duplicate"] is True
    assert opened["after"]["formal_segment_lifecycle"] == "open"
    assert opened["after"]["formal_segment_id"] == "semantic-segment-1"


def test_enforced_pre_serve_candidate_is_warm_only_until_rally_active():
    detector = _Detector([BallCandidate(120, 120, 0.9, width=8, height=8)])
    tracker = BallTracker(
        detector=detector,
        config=BallTrackerConfig(tentative_min_hits=1, lock_min_hits=1, max_box_area_ratio=0.01),
    )
    config = BallSemanticPolicyConfig(
        mode=SemanticPolicyMode.ENFORCED,
        enforced_rollout_enabled=True,
    )
    provider = SemanticTimelineProvider.from_events(
        [
            {"id": "a-start", "event_type": "non_play_start", "timestamp_ms": 0, "source": "manual"},
            {"id": "b-end", "event_type": "non_play_end", "timestamp_ms": 0, "source": "manual"},
        ],
        config=config,
    )
    context = _BallRunContext(
        tracker=tracker,
        semantic_provider=provider,
        semantic_policy=BallSearchPolicy(config),
    )
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    context.semantic_provider.state_machine.phase = SemanticPhase.POST_RALLY
    context.semantic_evidence = {"serve_candidate_confidence": 0.60}
    AnalysisPipeline._process_ball_frame(
        context=context,
        frame=frame,
        frame_index=1,
        timestamp=1.1,
        homography=None,
        frame_width=640,
        frame_height=480,
        player_motion_pixels=0.0,
    )

    warm_sample = context.samples[-1]
    assert warm_sample.source == "semantic_warm"
    assert warm_sample.publication_eligible is False
    assert warm_sample.quality_status == "warm_diagnostic"
    assert context.detections == []


def test_single_view_authoritative_boundary_seals_old_formal_state_and_reopens_next_segment():
    detector = _Detector([BallCandidate(120, 120, 0.9, width=8, height=8)])
    tracker = BallTracker(
        detector=detector,
        config=BallTrackerConfig(tentative_min_hits=1, lock_min_hits=1, max_box_area_ratio=0.01),
    )
    config = BallSemanticPolicyConfig(
        mode=SemanticPolicyMode.ENFORCED,
        enforced_rollout_enabled=True,
    )
    provider = SemanticTimelineProvider.from_events(
        [
            {"id": "rally-1", "event_type": "rally_start", "timestamp_ms": 0, "source": "manual"},
            {"id": "np-1", "event_type": "non_play_start", "timestamp_ms": 100, "source": "manual"},
            {"id": "np-2", "event_type": "non_play_end", "timestamp_ms": 200, "source": "manual"},
            {"id": "rally-2", "event_type": "rally_start", "timestamp_ms": 300, "source": "manual"},
        ],
        config=config,
    )
    context = _BallRunContext(
        tracker=tracker,
        semantic_provider=provider,
        semantic_policy=BallSearchPolicy(config),
    )
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    for frame_index, timestamp in enumerate((0.0, 0.15, 0.35, 0.40)):
        AnalysisPipeline._process_ball_frame(
            context=context,
            frame=frame,
            frame_index=frame_index,
            timestamp=timestamp,
            homography=None,
            frame_width=640,
            frame_height=480,
        )

    assert context.samples[0].accepted is True
    assert context.samples[1].quality_status == "diagnostic_only"
    assert context.samples[1].publication_eligible is False
    assert context.samples[2].accepted is True
    assert context.samples[3].accepted is True
    assert context.samples[3].publication_eligible is True
    assert context.semantic_segment_ids == ["semantic-segment-1", "semantic-segment-2"]
    assert len(context.semantic_boundary_events) == 3
    assert sum(1 for event in context.semantic_boundary_events if event.get("duplicate")) == 0
