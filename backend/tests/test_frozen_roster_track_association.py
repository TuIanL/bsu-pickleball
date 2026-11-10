from types import SimpleNamespace
import pytest

from app.schemas.tracking import PlayerFramePosition
from app.vision.multiview.association_global import GlobalPlayerAssociator, JointObservation
from app.vision.multiview.association import min_cost_matching
from app.vision.multiview.court_frame import CourtOrientation
from app.vision.multiview.global_state import GlobalPlayerRegistry, ViewBinding
from app.vision.multiview.multiview_joint_run import MultiViewJointRun
from app.vision.player_tracking_engine.view_tracking_session import ViewFrameResult


def test_reused_local_label_does_not_merge_distinct_frozen_roster_tracks():
    positions = [
        PlayerFramePosition(
            frame_index=3450, timestamp=57.5, track_id=track,
            bbox=[x * 20, 35, x * 20 + 50, 162], image_footpoint=[x * 20 + 25, 162],
            court_position=[x, 2.0], confidence=0.9, projection_confidence=0.9,
        )
        for track, x in [(274, 5.0), (275, 15.0)]
    ]
    result = ViewFrameResult(
        frame_index=3450, timestamp=57.5,
        frame_detections=[SimpleNamespace(track_id=p.track_id, player_id="Player_3", source_height=1080) for p in positions],
        frame_positions=positions, render_raw_by_track={}, player_motion_pixels=None,
        local_identity_by_track={274: "Player_3", 275: "Player_3"},
        local_identity_epoch_by_track={274: 0, 275: 0},
    )
    observations = MultiViewJointRun._result_to_observations("cam_1", result, 57_500, use_raw_track_keys=True)
    assert len(observations) == 2
    assert {o.source_local_player_id for o in observations} == {"Player_3"}
    assert all(o.view_player_id == "" for o in observations)
    assert len({GlobalPlayerAssociator.mapping_key(o) for o in observations}) == 2
    registry = GlobalPlayerRegistry()
    for gid, x in [("global_player_1", 5.0), ("global_player_2", 15.0)]:
        state = registry.ensure(gid)
        state.roster_status = "provisional"
        state.x_ft, state.y_ft = x, 2.0
        registry.estimator.update(gid, x, 2.0, 57.5)
    updates = GlobalPlayerAssociator(registry).process_tick(
        observations, 57.5, {"cam_1": CourtOrientation.identity}, tick=1725,
    )
    assert {u.global_id for u in updates} == {"global_player_1", "global_player_2"}
    assert all(not u.tentative for u in updates)


def test_motion_confirmed_anonymous_slot_can_expire_without_evicting_frozen_identity():
    ends = {f"Player_{i}": "end_a" if i <= 2 else "end_b" for i in range(1, 5)}
    registry = GlobalPlayerRegistry(frozen_player_end_by_id=ends)
    for index in range(1, 5):
        state = registry.ensure(f"global_player_{index}")
        state.roster_status = "confirmed"
        state.roster_end = "end_a" if index <= 2 else "end_b"
        state.last_seen_s = 0.0
    registry.players["global_player_2"].frozen_identity_confirmed = True
    candidate = registry.find_or_create_candidate(
        view_id="cam_1", view_player_id="275", identity_epoch=0,
        canonical_x_ft=15.0, canonical_y_ft=2.0, tick=30,
    )
    assert registry.promote_candidate(candidate, 30, now_s=20.0) == "global_player_1"
    assert registry.players["global_player_1"].roster_status == "provisional"
    assert registry.players["global_player_2"].frozen_identity_confirmed


@pytest.mark.parametrize("protected", [None, "frozen", "recent", "single_view", "old_dual"])
def test_long_lost_anonymous_cross_view_slot_requires_current_dual_evidence(protected):
    ends={f"Player_{i}": "end_a" if i<=2 else "end_b" for i in range(1,5)}
    registry=GlobalPlayerRegistry(frozen_player_end_by_id=ends)
    for i in range(1,5):
        state=registry.ensure(f"global_player_{i}")
        state.roster_status="confirmed"
        state.roster_end=ends[f"Player_{i}"]
        state.last_seen_s=4.4
        state.frozen_identity_confirmed=i!=1
    old=registry.players["global_player_1"]
    old.cross_view_anchored=True
    old.association_eligible=False
    old.view_bindings={"cam_2":ViewBinding(track_id=26,visibility="lost",last_seen_take_timestamp_ms=4400)}
    if protected=="frozen":old.frozen_identity_confirmed=True
    if protected=="recent":old.view_bindings["cam_2"].last_seen_take_timestamp_ms=56_000
    cid=registry.find_or_create_candidate(view_id="cam_1",view_player_id="290",identity_epoch=0,canonical_x_ft=15.2,canonical_y_ft=2.1,tick=1719)
    for tick in (1719,1720):
        registry.note_candidate_observation(cid,view_id="cam_1",view_player_id="290",identity_epoch=0,canonical_x_ft=15.2,canonical_y_ft=2.1,tick=tick)
        if protected!="single_view":
            registry.note_candidate_observation(cid,view_id="cam_2",view_player_id="91",identity_epoch=0,canonical_x_ft=15.8,canonical_y_ft=1.4,tick=tick)
    gid=registry.promote_candidate(cid,1721 if protected=="old_dual" else 1720,now_s=57.5)
    if protected:
        assert gid is None
        assert registry.players["global_player_1"] is old
    else:
        assert gid=="global_player_1"
        assert registry.players[gid].cross_view_anchored is False
        assert registry.players[gid].view_bindings=={}
        assert registry.provisional_replacement_events[-1]["reason"]=="stale_anonymous_cross_view_anchor_replaced"


def test_raw_track_mode_keeps_formal_player_visible_behind_baseline():
    position = PlayerFramePosition(
        frame_index=1, timestamp=1.0, track_id=368, bbox=[300, 400, 500, 850],
        image_footpoint=[400, 850], court_position=[2.5, 46.8],
        confidence=0.9, projection_confidence=0.9, valid=False,
        is_inside_court=False, projection_status="outside_court_visible",
    )
    result = ViewFrameResult(
        frame_index=1, timestamp=1.0,
        frame_detections=[SimpleNamespace(track_id=368, player_id="Player_3", source_height=1080)],
        frame_positions=[position], render_raw_by_track={}, player_motion_pixels=None,
    )
    observations = MultiViewJointRun._result_to_observations("cam_1", result, 1000, use_raw_track_keys=True)
    assert len(observations) == 1
    assert observations[0].track_id == 368
    assert observations[0].view_player_id == ""
    assert observations[0].local_y_ft == 46.8
    position.projection_status = "outside_tracking_area"
    assert MultiViewJointRun._result_to_observations("cam_1", result, 1000, use_raw_track_keys=True) == []


def test_full_frozen_roster_waitlist_still_recovers_from_other_camera():
    ends = {f"Player_{i}": "end_a" if i <= 2 else "end_b" for i in range(1, 5)}
    registry = GlobalPlayerRegistry(frozen_player_end_by_id=ends)
    for i, (x, y) in enumerate([(5, 8), (15, 8), (5, 36), (15, 36)], 1):
        state = registry.ensure(f"global_player_{i}")
        state.roster_status = "confirmed"
        state.roster_end = ends[f"Player_{i}"]
        state.frozen_identity_confirmed = True
        state.frozen_player_id = f"Player_{i}"
        state.x_ft, state.y_ft = x, y
        registry.estimator.update(state.global_player_id, x, y, 0.0)
    state = registry.players["global_player_1"]
    state.view_bindings["cam_2"] = ViewBinding(visibility="lost")
    associator = GlobalPlayerAssociator(registry)
    for tick in range(1, 5):
        donor = JointObservation("cam_1", tick, tick * 33.0, 5.0, 8.0, track_id=1, confidence=0.9)
        candidate = JointObservation(
            "cam_2", tick, tick * 33.0, 5.1, 8.0, track_id=25,
            tracking_status="candidate", tracklet_lineage_id="cam_2:track:25", confidence=0.9,
        )
        updates = associator.process_tick(
            [donor], tick / 30, {"cam_1": CourtOrientation.identity, "cam_2": CourtOrientation.identity},
            tick=tick, candidate_observations=[candidate], available_views={"cam_1", "cam_2"},
        )
    assert associator.diagnostics["unmatched_recovery_accepted"] >= 1
    assert any(u.view_id == "cam_2" and u.global_id == "global_player_1" for u in updates)
    assert len(registry.players) == 4


def test_strong_raw_track_match_retains_history_for_reanchor():
    registry = GlobalPlayerRegistry()
    state = registry.ensure("global_player_1")
    state.roster_status = "confirmed"
    state.x_ft, state.y_ft = 5.0, 8.0
    registry.estimator.update(state.global_player_id, 5.0, 8.0, 0.0)
    associator = GlobalPlayerAssociator(registry)
    observation = JointObservation("cam_1", 1, 33.0, 5.0, 8.0, track_id=255, confidence=0.9)
    associator.process_tick([observation], 1 / 30, {"cam_1": CourtOrientation.identity}, tick=1)
    assert registry.historical_bindings[("cam_1", "255")] == "global_player_1"


def test_recovery_sparse_pairs_do_not_create_edges_or_raise_keyerror():
    costs = {"near-left": {"P1": 0.1}, "near-right": {"P2": 0.2}}
    assert set(min_cost_matching(list(costs), ["P1", "P2"], costs)) == {("near-left", "P1"), ("near-right", "P2")}
    assert min_cost_matching(["unknown"], ["P1"], {}) == []
