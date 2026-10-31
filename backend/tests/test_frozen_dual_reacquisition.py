import pytest

from app.vision.multiview.association_global import GlobalPlayerAssociator, JointObservation
from app.vision.multiview.court_frame import CourtOrientation
from app.vision.multiview.global_state import GlobalPlayerRegistry, ViewBinding


def run_reentry(guard=None):
    registry = GlobalPlayerRegistry(frozen_player_end_by_id={
        f"Player_{i}": "end_a" if i <= 2 else "end_b" for i in range(1, 5)
    })
    for i, (x, y) in enumerate([(5, 8), (15, 8), (5, 35), (17, 36)], 1):
        state = registry.ensure(f"global_player_{i}")
        state.roster_status = "confirmed"
        state.lifecycle = "confirmed"
        state.roster_end = "end_a" if i <= 2 else "end_b"
        state.frozen_player_id = f"Player_{i}"
        state.frozen_identity_confirmed = True
        state.frozen_identity_confirmed_from_ms = 1000
        state.x_ft, state.y_ft = x, y
        state.last_seen_s = 0. if i == 3 or (i == 4 and guard == "two_missing") else 10.
        state.association_eligible = i != 3
        registry.estimator.update(state.global_player_id, x, y, state.last_seen_s)
        if i == 3:
            state.view_bindings = {v: ViewBinding(track_id=3, visibility="lost") for v in ("cam_1", "cam_2")}
    if guard == "foreign_history":
        registry.historical_bindings[("cam_1", "100")] = "global_player_4"
        registry.historical_bindings[("cam_2", "200")] = "global_player_4"
    if guard == "transferred_opposite_track":
        registry.historical_bindings[("cam_1", "100")] = "global_player_1"
        registry.historical_bindings[("cam_2", "200")] = "global_player_1"
    associator = GlobalPlayerAssociator(registry)
    recovered = []
    for tick in range(1, 5):
        ts = 10 + tick / 30
        registry.age_bindings(ts * 1000)
        registry.update_stale_eligibility(ts)
        donor = [] if guard == "two_missing" else [
            JointObservation(v, tick, ts * 1000, 17, 36, track_id=40 + i, confidence=.9)
            for i, v in enumerate(("cam_1", "cam_2"))
        ]
        if guard == "transferred_opposite_track":
            donor.extend(JointObservation(v, tick, ts * 1000, 5, 8,
                track_id=10 + i, confidence=.9)
                for i, v in enumerate(("cam_1", "cam_2")))
        x, y = (17, 36) if guard == "near_teammate" else (4, 45)
        candidates = [JointObservation(
            v, tick, ts * 1000 + (500 if guard == "bad_clock" and i == 1 else 0),
            x + i * .2, y, track_id=100 + i * 100,
            confidence=.3 if guard == "low_confidence" or (guard == "weak_distant_view" and i == 1) else .9,
            tracking_status="candidate", roster_admission_eligible=guard != "outside",
        ) for i, v in enumerate(("cam_1", "cam_2")) if guard != "single_view" or i == 0]
        if guard == "ambiguous":
            candidates.extend(JointObservation(v, tick, ts * 1000, 9, 45,
                track_id=101 + i * 100, confidence=.9, tracking_status="candidate")
                for i, v in enumerate(("cam_1", "cam_2")))
        available = {"cam_1"} if guard == "unavailable_view" else {"cam_1", "cam_2"}
        updates = associator.process_tick(
            donor, ts, {v: CourtOrientation.identity for v in ("cam_1", "cam_2")},
            tick=tick, candidate_observations=candidates, available_views=available,
        )
        recovered.extend(u for u in updates if u.global_id == "global_player_3")
        predictions = registry.predict_all(ts)
        for gid, (fx, fy, _) in associator.fuse_assignments(updates, predictions=predictions).items():
            if any(u.reanchor for u in updates if u.global_id == gid):
                registry.reseed(gid, fx, fy, ts, tick=tick)
            else:
                registry.absorb_measurement(gid, fx, fy, ts, tick=tick)
    return registry, associator, recovered


@pytest.mark.parametrize("guard", [None, "weak_distant_view", "transferred_opposite_track"])
def test_returning_frozen_player_can_reacquire_new_raw_tracks_with_unique_current_dual_evidence(guard):
    registry, associator, recovered = run_reentry(guard)
    assert {u.view_id for u in recovered if u.reanchor} == {"cam_1", "cam_2"}
    assert recovered and all(not u.tentative and not u.quarantined for u in recovered)
    assert len(registry.players) == 4
    state = registry.players["global_player_3"]
    assert state.frozen_player_id == "Player_3" and state.frozen_identity_confirmed_from_ms == 1000
    assert state.last_seen_s > 10 and state.association_eligible
    assert associator.diagnostics["frozen_dual_reacquired"] == 1


@pytest.mark.parametrize("guard", ["single_view", "low_confidence", "outside", "two_missing",
    "near_teammate", "ambiguous", "foreign_history", "bad_clock", "unavailable_view"])
def test_frozen_reentry_does_not_guess_without_unique_trusted_dual_evidence(guard):
    _, _, recovered = run_reentry(guard)
    assert not recovered
