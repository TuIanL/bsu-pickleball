from dataclasses import replace

import pytest

from app.vision.multiview.frozen_appearance_guard import FrozenAppearanceGuard
from app.vision.multiview.association_global import GlobalPlayerAssociator, JointObservation
from app.vision.multiview.court_frame import CourtOrientation
from app.vision.multiview.global_state import GlobalPlayerRegistry
from app.vision.player_tracking_engine.player_appearance import (
    AppearanceQuality, AppearanceRegionFeature, PlayerAppearanceDescriptor,
)


def descriptor(value):
    feature = AppearanceRegionFeature((value,) * 36, (value,) * 6)
    return PlayerAppearanceDescriptor(feature, feature,
        AppearanceQuality(0, 1000, 100, 100, 100, 0, 1), "available", "clothing-central-hsv-lab.v2")


def trained(same=False):
    guard = FrozenAppearanceGuard()
    for gid, value in [("g1", .1), ("g2", .1 if same else .8)]:
        for ms in [0, 1000, 2000]:
            assert guard.enroll(global_id=gid, view_id="cam_2", descriptor=descriptor(value), timestamp_ms=ms, anchor_ms=0)
    return guard


def observation(value=.8, view="cam_2"):
    return JointObservation(view, 1, 20000, 5, 8, canonical_x_ft=5, canonical_y_ft=8,
                            track_id=10, confidence=.9, appearance_descriptor=descriptor(value))


def test_frozen_templates_do_not_learn_a_later_identity_swap():
    guard = trained()
    assert not guard.enroll(global_id="g1", view_id="cam_2", descriptor=descriptor(.8), timestamp_ms=11000, anchor_ms=0)
    assert guard.galleries['g1']['cam_2'].distance_to(descriptor(.1)) == pytest.approx(0, abs=1e-6)


def test_owner_requires_three_consecutive_discriminative_real_observations():
    guard = trained(); obs = observation()
    assert guard.owner(obs, ['g1', 'g2'], 1) is None
    assert guard.owner(obs, ['g1', 'g2'], 2) is None
    assert guard.owner(obs, ['g1', 'g2'], 3) == 'g2'
    assert guard.owner(obs, ['g1', 'g2'], 5) is None


@pytest.mark.parametrize("reason", ['same_clothes', 'other_view', 'low_quality', 'one_template'])
def test_ambiguous_or_untrusted_clothing_is_not_an_identity(reason):
    guard = trained(same=reason == 'same_clothes'); obs = observation()
    if reason == 'same_clothes': obs = observation(.1)
    if reason == 'other_view': obs = observation(view='cam_1')
    if reason == 'low_quality': obs.appearance_descriptor = replace(obs.appearance_descriptor, status='low_quality')
    gids = ['g1'] if reason == 'one_template' else ['g1', 'g2']
    assert all(guard.owner(obs, gids, tick) is None for tick in range(1, 5))


def test_strong_frozen_clothing_blocks_a_transferred_raw_track_history():
    registry = GlobalPlayerRegistry(frozen_player_end_by_id={'Player_1':'end_a','Player_2':'end_a','Player_3':'end_b','Player_4':'end_b'})
    for index, x in [(1, 5), (2, 6)]:
        st = registry.ensure('g'+str(index));st.roster_status='confirmed';st.lifecycle='confirmed'
        st.roster_end='end_a';st.frozen_player_id='Player_'+str(index);st.frozen_identity_confirmed=True
        st.frozen_identity_confirmed_from_ms=0;st.last_seen_s=20;st.x_ft=x;st.y_ft=8
        registry.estimator.update(st.global_player_id,x,8,20)
    assoc = GlobalPlayerAssociator(registry, appearance_mode='enabled')
    assoc._frozen_appearance_guard = trained()
    for tick in range(1, 4):
        obs = observation();obs.take_timestamp_ms = (20+tick/30)*1000
        assoc.mapping[assoc.mapping_key(obs)] = 'g1'
        registry.historical_bindings[('cam_2','10')] = 'g1'
        updates = assoc.process_tick([obs],20+tick/30,{'cam_2':CourtOrientation.identity},tick=tick)
    assert [u.global_id for u in updates if not u.quarantined] == ['g2']
    assert assoc.mapping[assoc.mapping_key(obs)] == 'g2'


def test_frozen_owner_uses_canonical_end_after_rotated_camera_mapping():
    registry=GlobalPlayerRegistry(frozen_player_end_by_id={'Player_3':'end_b','Player_4':'end_b'})
    for index,x in [(3,5),(4,6)]:
        st=registry.ensure('g'+str(index));st.frozen_player_id='Player_'+str(index)
        st.frozen_identity_confirmed=True;st.roster_end='end_b'
        st.last_seen_s=20;st.x_ft=x;st.y_ft=36
        registry.estimator.update(st.global_player_id,x,36,20)
    assoc=GlobalPlayerAssociator(registry,appearance_mode='enabled')
    guard=trained()
    guard.galleries['g3']=guard.galleries.pop('g1');guard.galleries['g4']=guard.galleries.pop('g2')
    assoc._frozen_appearance_guard=guard
    for tick in range(1,4):
        obs=observation();obs.canonical_x_ft=None;obs.canonical_y_ft=None
        obs.local_x_ft=15;obs.local_y_ft=8;obs.take_timestamp_ms=(20+tick/30)*1000
        assoc.process_tick([obs],20+tick/30,{'cam_2':CourtOrientation.rotate_180},tick=tick)
    assert obs.canonical_y_ft==36
    assert assoc._frozen_appearance_owners[id(obs)]=='g4'


@pytest.mark.parametrize('failure', [None, 'ambiguous', 'already_visible', 'no_teammate',
    'near_teammate', 'bad_clock', 'weak_detection', 'far_relocation', 'unavailable', 'guided'])
def test_unique_real_clothing_can_restore_one_missing_player_without_bad_far_view_projection(failure):
    from app.vision.multiview.association_global import AssociationUpdate
    registry = GlobalPlayerRegistry(frozen_player_end_by_id={
        'Player_1':'end_a','Player_2':'end_a','Player_3':'end_b','Player_4':'end_b'})
    for index in range(1, 5):
        st = registry.ensure('g'+str(index))
        st.frozen_player_id='Player_'+str(index);st.frozen_identity_confirmed=True
        st.frozen_identity_confirmed_from_ms=0;st.last_seen_s=19
        st.x_ft,st.y_ft=(15,8) if index==2 else (0,8)
    assoc=GlobalPlayerAssociator(registry,appearance_mode='enabled')
    assoc._frozen_appearance_guard=trained()
    obs=observation();obs.canonical_x_ft=5
    for tick in range(1,4):owner=assoc._frozen_appearance_guard.owner(obs,['g1','g2'],tick)
    assoc._frozen_appearance_owners[id(obs)]=owner
    teammate=observation(.1);teammate.canonical_x_ft=0;teammate.track_id=1
    updates=[AssociationUpdate('g1','cam_2',teammate,.9)]
    if failure=='no_teammate':updates=[]
    if failure=='already_visible':updates.append(AssociationUpdate('g2','cam_1',observation(),.9))
    if failure=='near_teammate':obs.canonical_x_ft=1
    if failure=='bad_clock':obs.take_timestamp_ms+=100
    if failure=='weak_detection':obs.confidence=.4
    if failure=='far_relocation':registry.players['g2'].x_ft=30
    if failure=='guided':obs.detection_origin='guided_roi'
    entries=[('a',{'observation':obs})]
    if failure=='ambiguous':
        duplicate=replace(obs,track_id=11)
        assoc._frozen_appearance_owners[id(duplicate)]=owner
        entries.append(('b',{'observation':duplicate}))
    claimed=assoc._recover_missing_frozen_appearance(entries,updates=updates,timestamp_s=20,
        available_views=set() if failure=='unavailable' else {'cam_2'})
    assert bool(claimed)==(failure is None)
    if failure is None:
        assert updates[-1].global_id=='g2' and updates[-1].reanchor
        assert updates[-1].observation is obs
        assert registry.players['g2'].frozen_player_id=='Player_2'
