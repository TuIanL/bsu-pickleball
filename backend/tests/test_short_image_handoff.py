from dataclasses import replace

import pytest

from app.vision.multiview.association_global import AssociationUpdate, GlobalPlayerAssociator, JointObservation
from app.vision.multiview.global_state import GlobalPlayerRegistry
from app.vision.multiview.image_track_handoff import continuous_image_box


def setup():
    registry = GlobalPlayerRegistry(frozen_player_end_by_id={
        f"Player_{i}": "end_a" if i <= 2 else "end_b" for i in range(1, 5)})
    for i, xy in enumerate(((11., 12.), (23.7, 26.2), (10., 31.), (16., 31.)), 1):
        state = registry.ensure(f"global_player_{i}")
        state.frozen_player_id = f"Player_{i}"
        state.frozen_identity_confirmed = True
        state.roster_status = state.lifecycle = "confirmed"
        state.roster_end = "end_a" if i <= 2 else "end_b"
        state.x_ft, state.y_ft = xy
        state.last_seen_s = 388.3
    associator = GlobalPlayerAssociator(registry)
    old = JointObservation("cam_2", 23296, 388300., 17., 19., track_id=960,
        confidence=.596, bbox=[454.41, 208.81, 584.92, 387.42])
    associator._image_handoff_observations["global_player_2", "cam_2"] = old
    peers = [AssociationUpdate(f"global_player_{i}", "cam_2",
        JointObservation("cam_2", 23304, 388433.333, x, y, track_id=i,
            confidence=.8, bbox=box), .8)
        for i, x, y, box in ((1, 11., 12., [815., 207., 896., 457.]),
            (3, 10., 31., [885., 77., 949., 241.]),
            (4, 16., 31., [717., 90., 791., 238.]))]
    candidate = JointObservation("cam_2", 23302, 388400., 17.5, 19.15,
        canonical_x_ft=17.5, canonical_y_ft=19.15, track_id=964,
        confidence=.77, bbox=[477., 194., 588., 385.])
    return registry, associator, peers, candidate


def recover(associator, peers, candidate, tick):
    updates = list(peers)
    associator._recover_short_image_handoffs([candidate], updates=updates,
        timestamp_s=candidate.take_timestamp_ms/1000, tick=tick, available_views={"cam_2"})
    return [u for u in updates if u.global_id == "global_player_2"]


def test_bending_player_can_bridge_new_track_using_actual_continuous_image_evidence():
    registry, associator, peers, candidate = setup()
    assert not recover(associator, peers, candidate, 1)
    second = replace(candidate, source_frame_index=23304, take_timestamp_ms=388433.333,
        bbox=[482., 192., 590., 386.])
    updates = recover(associator, peers, second, 2)
    assert len(updates) == 1 and updates[0].observation is second
    assert updates[0].reanchor and not updates[0].tentative
    assert registry.players['global_player_2'].view_bindings['cam_2'].track_id == 964
    assert registry.historical_bindings['cam_2', '964'] == 'global_player_2'
    assert associator.last_tick_decisions[-1].reason == 'short_image_handoff'


@pytest.mark.parametrize('case', ['stale', 'same_frame', 'clock', 'other_view', 'weak',
    'jump', 'guided', 'foreign_history', 'near_peer', 'two_missing', 'wrong_end',
    'outside', 'unavailable', 'clothing_conflict', 'unconfirmed'])
def test_handoff_abstains_on_unsafe_or_ambiguous_evidence(case):
    registry, associator, peers, candidate = setup()
    available = {'cam_2'}
    if case == 'stale': candidate.take_timestamp_ms += 1000
    if case == 'same_frame': candidate.source_frame_index = 23296
    if case == 'other_view': candidate.view_id = 'cam_1'
    if case == 'weak': candidate.confidence = .6
    if case == 'jump': candidate.bbox = [100., 100., 200., 300.]
    if case == 'guided': candidate.detection_origin = 'guided_roi'
    if case == 'foreign_history': registry.historical_bindings['cam_2', '964'] = 'global_player_1'
    if case == 'near_peer': peers[0].observation.bbox = list(candidate.bbox)
    if case == 'two_missing': peers.pop()
    if case == 'wrong_end': candidate.canonical_y_ft = 30.
    if case == 'outside': candidate.roster_admission_eligible = False
    if case == 'unavailable': available = {'cam_1'}
    if case == 'clothing_conflict': associator._frozen_appearance_owners[id(candidate)] = 'global_player_1'
    if case == 'unconfirmed': registry.players['global_player_4'].frozen_identity_confirmed = False
    for tick in (1, 2):
        updates = list(peers)
        associator._recover_short_image_handoffs([candidate], updates=updates,
            timestamp_s=candidate.take_timestamp_ms/1000 + (.1 if case == 'clock' else 0),
            tick=tick, available_views=available)
        assert len(updates) == len(peers)
    assert 'short_image_handoff' not in associator.diagnostics


def test_two_overlapping_candidates_and_nonconsecutive_hits_cannot_bridge():
    _, associator, peers, candidate = setup()
    updates = list(peers)
    associator._recover_short_image_handoffs([candidate, replace(candidate, track_id=965)],
        updates=updates, timestamp_s=388.4, tick=1, available_views={'cam_2'})
    assert len(updates) == 3 and not associator._image_handoff_pending
    assert not recover(associator, peers, candidate, 2)
    assert not recover(associator, peers, replace(candidate,
        source_frame_index=23304, take_timestamp_ms=388433.333), 4)


def test_invalid_body_geometry_is_rejected():
    _, associator, _, candidate = setup()
    old = associator._image_handoff_observations['global_player_2', 'cam_2']
    assert not continuous_image_box(old, replace(candidate, bbox=[1., 2., float('nan'), 4.]))
    assert not continuous_image_box(old, replace(candidate, bbox=[1., 2., 1., 4.]))


def test_repeated_source_frame_is_not_two_independent_handoff_witnesses():
    _, associator, peers, candidate = setup()
    assert not recover(associator, peers, candidate, 1)
    assert not recover(associator, peers, candidate, 2)
