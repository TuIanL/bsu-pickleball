from types import SimpleNamespace

from app.schemas.rally_context import (
    AnalysisRosterConfirmationEntry,
    AnalysisRosterSnapshotPayload,
)
from app.services.analysis_roster_runtime import (
    RosterAnchor,
    build_bootstrap_binding_audit_payload,
    match_anchor_observations,
    validate_runtime_roster,
)
from app.vision.multiview.multiview_joint_run import MultiViewJointRun, build_perception_trace_windows
from app.vision.multiview.association_global import AssociationUpdate, JointObservation


def _snapshot() -> AnalysisRosterSnapshotPayload:
    entries = [
        AnalysisRosterConfirmationEntry(
            canonical_player_id=f"Player_{index}",
            candidate_id=f"candidate-{index}",
            team_id="A" if index < 3 else "B",
            source_view_id="cam_1",
            anchor_timestamp_ms=100_000,
            anchor_bbox=[100 + index * 150, 100, 160 + index * 150, 260],
            anchor_court_xy=[5.0 + index, 5.0 if index < 3 else 39.0],
        )
        for index in range(1, 5)
    ]
    return AnalysisRosterSnapshotPayload(
        snapshot_id="snapshot-1",
        owner_key="take-1",
        capture_take_id="take-1",
        job_id="job-1",
        status="available",
        source="manual",
        initial_team_a_end="end_a",
        entries=entries,
    )


def test_runtime_roster_checks_hash_slots_team_and_end_mapping():
    snapshot = _snapshot()
    runtime = validate_runtime_roster(snapshot, expected_hash=snapshot.roster_hash)
    assert runtime.available
    assert runtime.player_end_by_id == {
        "Player_1": "end_a", "Player_2": "end_a",
        "Player_3": "end_b", "Player_4": "end_b",
    }
    assert validate_runtime_roster(snapshot, expected_hash="wrong").reason == "roster_snapshot_hash_mismatch"


def test_runtime_roster_rejects_wrong_team_assignment():
    snapshot = _snapshot()
    snapshot.entries[0].team_id = "B"
    # The recalculated hash matches the altered stored snapshot; slot semantics
    # still fail independently of the hash check.
    runtime = validate_runtime_roster(snapshot, expected_hash=snapshot.roster_hash)
    assert runtime.reason == "roster_team_slots_invalid"


def test_anchor_match_requires_same_view_time_and_unique_geometry():
    anchor = RosterAnchor(
        player_id="Player_1", team_id="A", end="end_a", view_id="cam_1",
        timestamp_ms=100_000, bbox=(100.0, 100.0, 160.0, 260.0),
        canonical_xy=(5.0, 5.0), candidate_id="candidate-1",
    )
    hit = SimpleNamespace(
        view_id="cam_1", source_timestamp_ms=100_033.0,
        take_timestamp_ms=100_033.0, bbox=[101.0, 100.0, 161.0, 260.0],
        canonical_x_ft=5.1, canonical_y_ft=5.0,
    )
    wrong_view = SimpleNamespace(**{**hit.__dict__, "view_id": "cam_2"})
    wrong_time = SimpleNamespace(**{**hit.__dict__, "source_timestamp_ms": 101_000.0})
    matches, reasons, _competition = match_anchor_observations((anchor,), [wrong_view, wrong_time, hit])
    assert len(matches) == 1
    assert matches[0][1] is hit
    assert "Player_1" not in reasons


def test_one_observation_cannot_confirm_two_frozen_slots():
    """7.1：同一观测只能确认一个槽位——证据强者胜出，弱者留证落败。

    旧实现把两个槽位一起判为 `bootstrap_binding_conflicting_slots` 全fail，
    导致先到者独占 tracklet；现在按 court 距离 -> IoU -> 时间差裁决。
    """
    shared = SimpleNamespace(
        view_id="cam_1", source_timestamp_ms=100_000.0,
        take_timestamp_ms=100_000.0, bbox=[100.0, 100.0, 160.0, 260.0],
        canonical_x_ft=5.0, canonical_y_ft=5.0,
    )
    # 两个锚点框完全相同 -> court 距离与IoU 完全一致 -> 由时间差决定，
    # 时间相同则退化为按player_id 稳定排序，保证裁决可复现。
    anchors = tuple(
        RosterAnchor(
            player_id=f"Player_{index}", team_id="A", end="end_a", view_id="cam_1",
            timestamp_ms=100_000, bbox=(100.0, 100.0, 160.0, 260.0),
            canonical_xy=(5.0, 5.0), candidate_id=f"candidate-{index}",
        )
        for index in (1, 2)
    )
    matches, reasons, competition = match_anchor_observations(anchors, [shared])

    # 硬不变量：同一观测不得同时确认两个槽位
    confirmed_players = [anchor.player_id for anchor, _obs, _ev in matches]
    assert len(confirmed_players) == len(set(confirmed_players))
    assert len(matches) == 1
    winner = confirmed_players[0]
    loser = "Player_2" if winner == "Player_1" else "Player_1"
    assert loser not in confirmed_players
    assert reasons[loser] == "bootstrap_binding_tracklet_competes_for_slots"
    assert winner not in reasons
    # 落败方必须留证：胜者、双方证据、裁决规则
    detail = competition[loser]
    assert detail["winner_player_id"] == winner
    assert detail["winner_evidence"] is not None
    assert detail["loser_evidence"] is not None
    assert detail["resolution_rule"] == "court_distance_then_bbox_iou_then_time_delta"


def test_tracklet_competition_prefers_evidence_strength_over_arrival_order():
    """7.1：证据更强者胜出，与锚点到达顺序无关（job-faf852782a 的 P4/P3场景）。"""
    track = SimpleNamespace(
        view_id="cam_1", source_timestamp_ms=100_000.0,
        take_timestamp_ms=100_000.0, bbox=[100.0, 100.0, 160.0, 260.0],
        canonical_x_ft=5.0, canonical_y_ft=5.0,
    )
    # Player_3 的锚点框与观测完全重合（IoU=1.0, court 距离=0）
    near = RosterAnchor(
        player_id="Player_3", team_id="B", end="end_b", view_id="cam_1",
        timestamp_ms=100_000, bbox=(100.0, 100.0, 160.0, 260.0),
        canonical_xy=(5.0, 5.0), candidate_id="candidate-3",
    )
    # Player_4 的锚点框略偏（court 距离 0.66ft、IoU 0.86）—— 仍是次优
    far = RosterAnchor(
        player_id="Player_4", team_id="B", end="end_b", view_id="cam_1",
        timestamp_ms=100_000, bbox=(103.0, 103.0, 163.0, 263.0),
        canonical_xy=(5.7, 5.0), candidate_id="candidate-4",
    )

    # 先传near（若按旧逻辑它会先到并独占）
    matches, reasons, competition = match_anchor_observations((near, far), [track])

    assert len(matches) == 1
    winner, loser = "Player_3", "Player_4"
    assert matches[0][0].player_id == winner
    assert reasons[loser] == "bootstrap_binding_tracklet_competes_for_slots"
    assert competition[loser]["winner_player_id"] == winner
    # 顺序反过来结论必须一致：证据强者始终胜出
    matches_reversed, reasons_reversed, competition_reversed = match_anchor_observations(
        (far, near), [track]
    )
    assert matches_reversed[0][0].player_id == winner
    assert reasons_reversed[loser] == "bootstrap_binding_tracklet_competes_for_slots"
    assert competition_reversed[loser]["winner_player_id"] == winner


def test_tracklet_competition_prefers_smaller_court_distance_over_iou():
    """7.1：court 距离优先于 bbox IoU（canonical 空间跨机位可比）。"""
    track = SimpleNamespace(
        view_id="cam_1", source_timestamp_ms=100_000.0,
        take_timestamp_ms=100_000.0, bbox=[100.0, 100.0, 160.0, 260.0],
        canonical_x_ft=5.0, canonical_y_ft=5.0,
    )
    # 高 IoU 但 court 距离远
    high_iou = RosterAnchor(
        player_id="Player_1", team_id="A", end="end_a", view_id="cam_1",
        timestamp_ms=100_000, bbox=(100.0, 100.0, 160.0, 260.0),
        canonical_xy=(7.9, 5.0), candidate_id="candidate-1",
    )
    # IoU 略低但 court 距离几乎为零
    low_iou = RosterAnchor(
        player_id="Player_2", team_id="A", end="end_a", view_id="cam_1",
        timestamp_ms=100_000, bbox=(101.0, 101.0, 161.0, 261.0),
        canonical_xy=(5.05, 5.0), candidate_id="candidate-2",
    )

    matches, reasons, _competition = match_anchor_observations((high_iou, low_iou), [track])

    assert len(matches) == 1
    assert matches[0][0].player_id == "Player_2"
    assert reasons["Player_1"] == "bootstrap_binding_tracklet_competes_for_slots"


def _anchor_run(anchors):
    class _Associator:
        def __init__(self):
            self.mapping = {}

        @staticmethod
        def observation_key(observation):
            return observation.view_player_id or str(observation.track_id)

        @classmethod
        def mapping_key(cls, observation):
            return (observation.view_id, cls.observation_key(observation), observation.local_identity_epoch)

    class _Registry:
        def __init__(self):
            self.historical_bindings = {}
            self.confirmed = []

        def confirm_frozen_identity(self, global_id, player_id, **kwargs):
            self.confirmed.append((global_id, player_id, kwargs))
            return True, None

    run = MultiViewJointRun.__new__(MultiViewJointRun)
    run.runtime_roster = SimpleNamespace(available=True, anchors=tuple(anchors), roster_hash="hash")
    run._frozen_anchor_track_keys = {}
    run._frozen_anchor_audit = {}
    run._perception_trace_window_specs = {}
    run.associator = _Associator()
    run.registry = _Registry()
    return run


def test_anchor_follows_raw_track_from_candidate_to_formal_with_changed_local_label():
    anchor = RosterAnchor(
        player_id="Player_1", team_id="A", end="end_a", view_id="cam_1",
        timestamp_ms=100_000, bbox=(100.0, 100.0, 160.0, 260.0),
        canonical_xy=(5.0, 5.0), candidate_id="candidate-1",
    )
    run = _anchor_run((anchor,))
    candidate = JointObservation(
        view_id="cam_1", source_frame_index=1, take_timestamp_ms=100_000,
        source_timestamp_ms=100_000, local_x_ft=5.0, local_y_ft=5.0,
        track_id=293, tracklet_lineage_id="cam_1:track:293", bbox=[100, 100, 160, 260],
        tracking_status="anchor_evidence",
    )
    run._process_frozen_roster_anchors(
        observations=[], anchor_evidence_observations=[candidate], take_timestamp_ms=100_000
    )
    assert run._frozen_anchor_audit["Player_1"]["reason"] == "bootstrap_binding_waiting_global_association"

    formal = JointObservation(
        view_id="cam_1", source_frame_index=2, take_timestamp_ms=100_500,
        source_timestamp_ms=100_500, local_x_ft=5.1, local_y_ft=5.0,
        view_player_id="Player_3", local_identity_epoch=0,
        track_id=293, tracklet_lineage_id="cam_1:Player_3:epoch:0",
        bbox=[100, 100, 160, 260], tracking_status="detected",
    )
    run.associator.mapping[run.associator.mapping_key(formal)] = "global_player_1"
    run._process_frozen_roster_anchors(observations=[formal], take_timestamp_ms=100_500)

    assert run.registry.confirmed[0][0:2] == ("global_player_1", "Player_1")
    assert run._frozen_anchor_audit["Player_1"]["confirmed"] is True
    assert run._frozen_anchor_audit["Player_1"]["track_id"] == 293


def test_distinct_raw_tracks_reusing_one_player_label_keep_separate_anchor_keys():
    anchors = tuple(
        RosterAnchor(
            player_id=f"Player_{index}", team_id="A", end="end_a", view_id="cam_1",
            timestamp_ms=100_000,
            bbox=(float(x), 100.0, float(x + 60), 260.0),
            canonical_xy=(float(court_x), 5.0), candidate_id=f"candidate-{index}",
        )
        for index, x, court_x in ((1, 100, 5), (2, 300, 15))
    )
    run = _anchor_run(anchors)
    observations = [
        JointObservation(
            view_id="cam_1", source_frame_index=1, take_timestamp_ms=100_000,
            source_timestamp_ms=100_000, local_x_ft=float(court_x), local_y_ft=5.0,
            view_player_id="Player_3", local_identity_epoch=0,
            track_id=track_id, bbox=[x, 100, x + 60, 260], tracking_status="detected",
        )
        for track_id, x, court_x in ((11, 100, 5), (12, 300, 15))
    ]

    run._process_frozen_roster_anchors(observations=observations, take_timestamp_ms=100_000)

    assert run._frozen_anchor_track_keys[("cam_1", "track:11", 0)][0] == "Player_1"
    assert run._frozen_anchor_track_keys[("cam_1", "track:12", 0)][0] == "Player_2"
    assert run._frozen_anchor_audit["Player_1"]["reason"] == "bootstrap_binding_waiting_global_association"
    assert run._frozen_anchor_audit["Player_2"]["reason"] == "bootstrap_binding_waiting_global_association"


def test_live_anchor_confirmation_requires_current_unquarantined_assignment():
    anchor = RosterAnchor(
        player_id="Player_1", team_id="A", end="end_a", view_id="cam_1",
        timestamp_ms=100_000, bbox=(100.0, 100.0, 160.0, 260.0),
        canonical_xy=(5.0, 5.0), candidate_id="candidate-1",
    )
    run = _anchor_run((anchor,))
    observation = JointObservation(
        "cam_1", 1, 100_000, 5.0, 5.0, track_id=274,
        bbox=[100, 100, 160, 260], source_timestamp_ms=100_000,
    )
    run.associator.mapping[run.associator.mapping_key(observation)] = "stale-global"
    quarantined = AssociationUpdate("stale-global", "cam_1", observation, 0.9, quarantined=True)
    run._process_frozen_roster_anchors(
        observations=[observation], accepted_updates=[quarantined], take_timestamp_ms=100_000,
    )
    assert run.registry.confirmed == []
    assert not run._frozen_anchor_audit["Player_1"]["confirmed"]
    accepted = AssociationUpdate("actual-global", "cam_1", observation, 0.9)
    run._process_frozen_roster_anchors(
        observations=[observation], accepted_updates=[accepted], take_timestamp_ms=100_000,
    )
    assert run.registry.confirmed[0][:2] == ("actual-global", "Player_1")


def test_perception_trace_windows_follow_short_clip_range_and_roster_anchors():
    anchors = tuple(
        SimpleNamespace(player_id=f"Player_{index}", timestamp_ms=timestamp_ms)
        for index, timestamp_ms in ((1, 55_500), (2, 57_500), (3, 62_500))
    )
    windows = build_perception_trace_windows(start_s=0.0, end_s=120.0, anchors=anchors)

    assert windows["opening"]["window_seconds"] == [0.0, 4.0]
    assert windows["midpoint"]["window_seconds"] == [58.0, 62.0]
    assert windows["late"]["window_seconds"] == [118.0, 120.0]
    assert windows["frozen_roster_anchor_Player_1"]["window_seconds"] == [53.5, 57.5]
    assert windows["frozen_roster_anchor_Player_3"]["anchor_player_ids"] == ["Player_3"]
    assert all(window["window_seconds"][1] <= 120.0 for window in windows.values())


def test_two_observations_cannot_ambiguously_confirm_one_frozen_slot():
    anchor = RosterAnchor(
        player_id="Player_1", team_id="A", end="end_a", view_id="cam_1",
        timestamp_ms=100_000, bbox=(100.0, 100.0, 160.0, 260.0),
        canonical_xy=(5.0, 5.0), candidate_id="candidate-1",
    )
    observations = [
        SimpleNamespace(
            view_id="cam_1", source_timestamp_ms=100_000.0,
            take_timestamp_ms=100_000.0, bbox=[100.0, 100.0, 160.0, 260.0],
            canonical_x_ft=5.0, canonical_y_ft=5.0,
        ),
        SimpleNamespace(
            view_id="cam_1", source_timestamp_ms=100_000.0,
            take_timestamp_ms=100_000.0, bbox=[101.0, 100.0, 161.0, 260.0],
            canonical_x_ft=5.0, canonical_y_ft=5.0,
        ),
    ]

    matches, reasons, _competition = match_anchor_observations((anchor,), observations)

    assert matches == []
    assert reasons == {"Player_1": "bootstrap_binding_ambiguous_match"}


def test_independent_audit_always_records_four_slots_and_only_confirmed_binding():
    audit = build_bootstrap_binding_audit_payload(
        job_id="job-1",
        roster_hash="hash-1",
        audit={
            "entries": [{
                "canonical_player_id": "Player_1",
                "formal_canonical_player_id": "Player_1",
                "global_player_id": "global_player_1",
                "tracklet_lineage_id": "cam_1:Player_1:epoch:0",
                "local_identity_epoch": 0,
                "source_view_id": "cam_1",
                "canonical_end": "end_a",
                "confirmed": True,
                "method": "anchor_simultaneous_match",
                "evidence": {"view_id": "cam_1", "time_delta_ms": 33, "bbox_iou": 0.8},
            }]
        },
    )
    assert audit.status == "partial"
    assert len(audit.entries) == 4
    assert audit.p_slot_to_formal_player() == {"Player_1": "Player_1"}
    assert audit.entries[0].evidence.bbox_iou == 0.8


def test_unconfirmed_audit_preserves_track_and_local_identity_failure_evidence():
    audit = build_bootstrap_binding_audit_payload(
        job_id="job-1",
        roster_hash="hash-1",
        audit={"entries": [{
            "canonical_player_id": "Player_1",
            "source_view_id": "cam_1",
            "anchor_timestamp_ms": 55_500,
            "confirmed": False,
            "reason": "bootstrap_binding_waiting_global_association",
            "evidence": {
                "view_id": "cam_1",
                "track_id": 293,
                "tracklet_lineage_id": "cam_1:track:293",
                "local_identity_epoch": 0,
                "local_identity_reason": "no lock manager hint",
                "tracking_status": "anchor_evidence",
                "global_player_id": "global_player_1",
            },
        }]},
    )

    entry = audit.entries[0]
    assert entry.reason == "bootstrap_binding_waiting_global_association"
    assert entry.confirmed is False
    assert entry.evidence.track_id == 293
    assert entry.evidence.local_identity_reason == "no lock manager hint"
    assert entry.evidence.global_player_id == "global_player_1"


def test_invalid_frozen_roster_still_publishes_unavailable_conclusions_for_all_slots():
    audit = build_bootstrap_binding_audit_payload(
        job_id="job-1", roster_hash=None, audit=None, unavailable_reason="roster_snapshot_hash_mismatch"
    )
    assert audit.status == "unavailable"
    assert len(audit.entries) == 4
    assert {entry.reason for entry in audit.entries} == {"roster_snapshot_hash_mismatch"}


def test_perception_trace_carries_stage_funnel_metric_samples_and_roster_audit():
    anchor = RosterAnchor(
        player_id="Player_1", team_id="A", end="end_a", view_id="cam_1",
        timestamp_ms=289_083, bbox=(100.0, 100.0, 160.0, 260.0),
        canonical_xy=(5.0, 5.0), candidate_id="candidate-1",
    )
    run = MultiViewJointRun.__new__(MultiViewJointRun)
    run.runtimes = {"cam_1": object()}
    run.runtime_roster = SimpleNamespace(anchors=(anchor,), roster_hash="roster-hash")
    run._frozen_anchor_audit = {}
    run.perception_stage_trace = {
        "opening_0m20": {
            "window_seconds": [18.0, 22.0],
            "ticks": 0,
            "metric_scope_ticks": 0,
            "per_view": {
                "cam_1": {
                    "raw_detection_count": 0,
                    "roi_filtered_base_count": 0,
                    "local_track_count": 0,
                    "local_candidate_count": 0,
                    "global_formal_observation_count": 0,
                    "global_candidate_observation_count": 0,
                    "unassigned_formal_observation_count": 0,
                    "unassigned_formal_reason_counts": {},
                    "assigned_observation_count": 0,
                    "metric_eligible_fused_player_count": 0,
                }
            },
            "per_canonical_end": {
                end: {
                    "global_formal_observation_count": 0,
                    "global_candidate_observation_count": 0,
                    "assigned_observation_count": 0,
                    "metric_eligible_fused_player_count": 0,
                }
                for end in ("end_a", "end_b", "unknown")
            },
            "roster_anchor_audit": {"confirmed_player_ids": [], "unresolved_reasons": {}},
        }
    }
    run._perception_trace_window_specs = {"opening_0m20": {"window_seconds": [18.0, 22.0]}}
    observation = SimpleNamespace(view_id="cam_1", canonical_y_ft=5.0)
    update = SimpleNamespace(global_id="global_player_1", view_id="cam_1", observation=observation, tentative=False)

    run._record_perception_trace_window(
        timestamp_s=20.0,
        metric_eligible_tick=True,
        prepared_by_view={"cam_1": SimpleNamespace(raw_detections=[1, 2], roi_filtered_base=[1])},
        view_results={"cam_1": SimpleNamespace(frame_detections=[1], candidate_detections=[2, 3])},
        observations=[observation],
        candidate_observations=[observation],
        updates=[update],
        fused={"global_player_1": (5.0, 5.0, ["cam_1"])},
    )

    trace = run.perception_stage_trace["opening_0m20"]
    assert trace["ticks"] == trace["metric_scope_ticks"] == 1
    assert trace["per_view"]["cam_1"] == {
        "raw_detection_count": 2,
        "roi_filtered_base_count": 1,
        "local_track_count": 1,
        "local_candidate_count": 2,
        "global_formal_observation_count": 1,
        "global_candidate_observation_count": 1,
        "unassigned_formal_observation_count": 0,
        "unassigned_formal_reason_counts": {},
        "assigned_observation_count": 1,
        "metric_eligible_fused_player_count": 1,
    }
    assert trace["per_canonical_end"]["end_a"]["metric_eligible_fused_player_count"] == 1
    assert trace["roster_anchor_audit"]["unresolved_reasons"] == {
        "Player_1": "bootstrap_binding_anchor_not_reached"
    }
