"""P2/P4 overlay flicker regression contract tests.

These tests exercise the safety boundary introduced for the 7--13s regression
window without depending on a particular detector or media file.
"""

from __future__ import annotations

from copy import deepcopy

from app.vision.multiview.association_global import GlobalPlayerAssociator, JointObservation
from app.vision.multiview.court_frame import CourtOrientation
from app.vision.multiview.fused_overlay_builder import FusedPlayerOverlayBuilder, OverlayBuilderConfig
from app.vision.multiview.global_state import GlobalPlayerRegistry
from app.vision.multiview.overlay_display_state import DisplayContext, OverlayDisplayStateMachine
from app.vision.multiview.player_display_diagnostics import (
    PlayerDisplayDiagnosticsArtifact,
    PlayerDisplayDiagnosticsRow,
    build_player_display_diagnostics_payload,
    validate_player_display_diagnostics,
)
from app.vision.player_tracking_engine.four_player_quality import (
    build_quality_from_joint_artifacts,
)


IDENTITY = CourtOrientation.identity


def _observation(
    x: float,
    y: float,
    *,
    slot: str = "Player_2",
    epoch: int = 0,
    lineage: str | None = None,
    track_id: int = 1,
    timestamp_ms: float = 0.0,
    frame: int = 0,
) -> JointObservation:
    return JointObservation(
        view_id="cam_2",
        source_frame_index=frame,
        take_timestamp_ms=timestamp_ms,
        local_x_ft=x,
        local_y_ft=y,
        canonical_x_ft=x,
        canonical_y_ft=y,
        view_player_id=slot,
        local_identity_epoch=epoch,
        tracklet_lineage_id=lineage,
        track_id=track_id,
        confidence=0.9,
    )


def _new_associator(*, reassociation_frames: int = 3) -> tuple[GlobalPlayerRegistry, GlobalPlayerAssociator]:
    registry = GlobalPlayerRegistry(expected_player_count=4)
    for global_id, (x, y) in {
        "global_player_1": (5.0, 8.0),
        "global_player_2": (9.0, 8.0),
    }.items():
        state = registry.ensure(global_id)
        state.roster_status = "provisional"
        state.x_ft, state.y_ft = x, y
        registry.estimator.update(global_id, x, y, 0.0)
    associator = GlobalPlayerAssociator(
        registry,
        reassociation_frames=reassociation_frames,
        switch_margin=0.15,
        reassociation_ambiguity_margin_ft=0.5,
    )
    initial = associator.process_tick(
        [
            _observation(5.0, 8.0, slot="Player_2", lineage="Player_2:epoch:0"),
            _observation(9.0, 8.0, slot="Player_4", lineage="Player_4:epoch:0", track_id=2),
        ],
        0.0,
        {"cam_2": IDENTITY},
        tick=0,
    )
    assert {update.global_id for update in initial} == {"global_player_1", "global_player_2"}
    registry.absorb_measurement("global_player_1", 5.0, 8.0, 0.0)
    registry.absorb_measurement("global_player_2", 9.0, 8.0, 0.0)
    return registry, associator


def test_ambiguous_local_slot_reassociation_is_quarantined() -> None:
    registry, associator = _new_associator()
    update = associator.process_tick(
        [
            _observation(
                7.1,
                8.0,
                epoch=1,
                lineage="Player_2:epoch:1",
                timestamp_ms=33.0,
                frame=1,
            )
        ],
        1 / 30.0,
        {"cam_2": IDENTITY},
        tick=1,
    )

    assert len(update) == 1
    assert update[0].global_id == "global_player_1"
    assert update[0].tentative is True
    assert update[0].quarantined is True
    assert associator.last_tick_local_slot_events[-1]["reason"] == "reassociation_margin_insufficient"
    assert associator.fuse_assignments(update) == {}
    assert registry.reference_slot_occupant("cam_2", "Player_2") == "global_player_1"


def test_confirmed_reassociation_is_atomic_and_keeps_slot_bijection() -> None:
    registry, associator = _new_associator(reassociation_frames=3)
    for tick in range(1, 4):
        updates = associator.process_tick(
            [
                _observation(
                    8.5,
                    8.0,
                    epoch=1,
                    lineage="Player_2:epoch:1",
                    timestamp_ms=tick * 33.0,
                    frame=tick,
                )
            ],
            tick / 30.0,
            {"cam_2": IDENTITY},
            tick=tick,
        )
        assert updates

    assert associator.last_tick_local_slot_events[-1]["reason"] == "reassociated"
    assert registry.reference_slot_occupant("cam_2", "Player_2") == "global_player_2"
    assert registry.players["global_player_1"].view_bindings["cam_2"].view_player_id is None
    assert registry.players["global_player_2"].view_bindings["cam_2"].view_player_id == "Player_2"
    assert associator.fuse_assignments(updates)["global_player_2"][2] == ["cam_2"]


def test_projection_collision_and_bbox_footpoint_residual_are_hard_gates() -> None:
    builder = FusedPlayerOverlayBuilder(
        OverlayBuilderConfig(projected_bbox_footpoint_residual_px=10.0)
    )
    builder._current_reference_real_bboxes = {  # noqa: SLF001 - pure gate test
        "global_player_4": (0.0, 0.0, 100.0, 100.0),
    }
    assert builder._projection_collision_reason(  # noqa: SLF001
        gid="global_player_2", bbox=[0.0, 0.0, 100.0, 100.0]
    ) == "projection_collision_with_global_player_4"
    assert builder._projection_footpoint_reason(  # noqa: SLF001
        bbox=[0.0, 0.0, 10.0, 10.0], footpoint=(100.0, 100.0)
    ) == "bbox_footpoint_inconsistency"


def test_topology_debounce_allows_real_recovery_without_box_point_box_flicker() -> None:
    machine = OverlayDisplayStateMachine(
        synthetic_upgrade_confirm_ticks=1,
        topology_debounce_ms=250.0,
    )

    real = machine.step(
        player_id="Player_2",
        view_id="cam_1",
        ctx=DisplayContext(now_ms=0.0, evidence_type="base_observed", has_real_bbox=True),
    )
    rejected = machine.step(
        player_id="Player_2",
        view_id="cam_1",
        ctx=DisplayContext(
            now_ms=100.0,
            evidence_type="cross_view_projected",
            has_valid_point=True,
            projection_rejection_reason="projection_collision_with_global_player_4",
        ),
    )
    debounced = machine.step(
        player_id="Player_2",
        view_id="cam_1",
        ctx=DisplayContext(
            now_ms=150.0,
            evidence_type="cross_view_projected",
            has_synthetic_bbox=True,
            has_valid_point=True,
        ),
    )
    recovered_projection = machine.step(
        player_id="Player_2",
        view_id="cam_1",
        ctx=DisplayContext(
            now_ms=400.0,
            evidence_type="cross_view_projected",
            has_synthetic_bbox=True,
            has_valid_point=True,
        ),
    )
    recovered_real = machine.step(
        player_id="Player_2",
        view_id="cam_1",
        ctx=DisplayContext(now_ms=433.0, evidence_type="base_observed", has_real_bbox=True),
    )

    assert real.state == "REAL_BOX"
    assert rejected.state == "PROJECTED_POINT"
    assert debounced.state == "PROJECTED_POINT"
    assert recovered_projection.state == "PROJECTED_BOX"
    assert recovered_real.state == "REAL_BOX"
    assert debounced.previous_state == "PROJECTED_POINT"
    # The recovery happens after the 250ms topology window, so the state
    # machine starts a fresh diagnostic window instead of carrying forward a
    # stale cumulative count.
    assert recovered_projection.transition_count == 1
    assert recovered_projection.state_sequence == ("PROJECTED_POINT", "PROJECTED_BOX")


def test_display_diagnostics_round_trip_and_legacy_defaults() -> None:
    row = PlayerDisplayDiagnosticsRow(
        canonical_tick=7,
        timestamp_ms=7000.0,
        player_id="Player_2",
        view_id="cam_2",
        local_slot="Player_2",
        local_identity_epoch=3,
        tracklet_lineage_id="Player_2:epoch:3",
        local_slot_reassociation_status="reassociation_pending",
        incumbent_global_player_id="global_player_4",
        challenger_global_player_id="global_player_2",
        reassociation_evidence_count=2,
    )
    payload = build_player_display_diagnostics_payload(
        job_id="job-new",
        video_id="take-new",
        reference_view_id="cam_1",
        rows=[row],
        events=[
            {
                "player_id": "Player_2",
                "view_id": "cam_1",
                "timestamp_ms": 7000.0,
                "previous_display_state": "REAL_BOX",
                "display_state": "PROJECTED_POINT",
                "display_transition_count": 1,
            }
        ],
    )
    validate_player_display_diagnostics(payload)
    parsed = PlayerDisplayDiagnosticsArtifact.model_validate(payload)
    assert parsed.rows[0].tracklet_lineage_id == "Player_2:epoch:3"
    assert parsed.events[0]["display_state"] == "PROJECTED_POINT"

    legacy = deepcopy(payload)
    for field in (
        "local_slot",
        "local_identity_epoch",
        "tracklet_lineage_id",
        "local_slot_reassociation_status",
        "incumbent_global_player_id",
        "challenger_global_player_id",
        "reassociation_evidence_count",
    ):
        legacy["rows"][0].pop(field, None)
    legacy.pop("events")
    legacy_parsed = PlayerDisplayDiagnosticsArtifact.model_validate(legacy)
    assert legacy_parsed.rows[0].local_slot is None
    assert legacy_parsed.events == []


def test_quality_gate_rejects_reassociation_violation_and_counts_state_edges_once() -> None:
    roster = {
        "confirmed_player_count": 4,
        "players": [
            {"global_player_id": f"global_player_{index}", "player_id": f"Player_{index}"}
            for index in range(1, 5)
        ],
    }
    samples = [
        {
            "global_player_id": f"global_player_{index}",
            "timestamp_seconds": float(tick),
            "metric_eligible": True,
            "identity_status": "confirmed_observed",
            "view_observations": {},
        }
        for index in range(1, 5)
        for tick in range(2)
    ]
    display_diagnostics = {
        "rows": [
            {
                "canonical_tick": 1,
                "timestamp_ms": 1000.0,
                "player_id": "Player_2",
                "view_id": "cam_2",
                "local_slot": "Player_2",
                "local_slot_reassociation_status": "reassociation_ambiguous",
            }
        ],
        "events": [
            {
                "timestamp_ms": 990.0,
                "view_id": "cam_2",
                "player_id": "Player_2",
                "local_slot": "Player_2",
                "reason": "reassociated",
                "challenger_global_id": "global_player_2",
                "evidence_count": 1,
            },
            {
                "timestamp_ms": 1000.0,
                "view_id": "cam_1",
                "player_id": "Player_2",
                "previous_display_state": "HIDDEN",
                "display_state": "PROJECTED_POINT",
                "display_transition_count": 1,
            },
            {
                "timestamp_ms": 1033.0,
                "view_id": "cam_1",
                "player_id": "Player_2",
                "previous_display_state": "PROJECTED_POINT",
                "display_state": "PROJECTED_BOX",
                "display_transition_count": 2,
            },
            {
                "timestamp_ms": 1066.0,
                "view_id": "cam_1",
                "player_id": "Player_2",
                "previous_display_state": "PROJECTED_BOX",
                "display_state": "PROJECTED_BOX",
                "display_transition_count": 2,
            },
        ],
    }

    artifact = build_quality_from_joint_artifacts(
        job_id="job-new",
        trajectory={"samples": samples},
        roster=roster,
        display_diagnostics=display_diagnostics,
    )

    assert artifact.players["Player_2"].local_slot_reassociation_violation_count == 1
    assert artifact.players["Player_2"].display_topology_transition_count == 2
    assert artifact.funnel.display_topology_transition_count == 2
    assert artifact.verdict == "fail"
    assert artifact.hard_invariants["local_slot_reassociation_zero"] is False
