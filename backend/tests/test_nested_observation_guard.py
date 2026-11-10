from dataclasses import replace

import pytest

from app.vision.multiview.association_global import GlobalPlayerAssociator, JointObservation
from app.vision.multiview.court_frame import CourtOrientation
from app.vision.multiview.global_state import GlobalPlayerRegistry
from app.vision.multiview.nested_observation_guard import (
    ambiguous_nested_observations, ambiguous_net_crowd_observations,
)


def body(box, track, confidence=.7, **kwargs):
    return JointObservation('cam_1', 35176, 586266.667, 11., 24.,
        bbox=list(box), track_id=track, confidence=confidence, **kwargs)


@pytest.mark.parametrize('small,large', [
    # Real source detector boxes from the failing whole-video handshake.
    ([1008.36,259.16,1038.73,331.24], [976.61,122.40,1053.75,341.18]),
    ([974.49,131.30,1023.91,321.56], [975.52,109.89,1049.53,321.64]),
    ([970.84,118.86,1046.93,321.62], [968.89,108.10,1078.52,319.31]),
])
def test_nested_partial_body_cannot_measure_an_independent_identity(small, large):
    one,two=body(small,1),body(large,2)
    assert ambiguous_nested_observations([one,two]) == {id(one)}
    assert ambiguous_nested_observations([two,one]) == {id(one)}


@pytest.mark.parametrize('case', ['different_camera','different_frame','behind','separate',
    'weak_container','guided_container','same_size','invalid'])
def test_overlap_alone_does_not_remove_separate_or_unsupported_evidence(case):
    one=body([100.,150.,150.,300.],1)
    two=body([90.,100.,160.,310.],2)
    if case=='different_camera':two.view_id='cam_2'
    if case=='different_frame':two.source_frame_index+=2
    if case=='behind':one.bbox=[100.,150.,150.,240.]
    if case=='separate':one.bbox=[40.,150.,90.,300.]
    if case=='weak_container':two.confidence=.4
    if case=='guided_container':two.detection_origin='guided_roi'
    if case=='same_size':two.bbox=list(one.bbox)
    if case=='invalid':one.bbox=[100.,150.,float('nan'),300.]
    assert not ambiguous_nested_observations([one,two])


def test_rejected_nested_track_cannot_reuse_a_wrong_global_history():
    registry=GlobalPlayerRegistry(frozen_player_end_by_id={f'Player_{i}':'end_a' if i<3 else 'end_b' for i in range(1,5)})
    for i in range(1,5):
        state=registry.ensure(f'g{i}');state.frozen_player_id=f'Player_{i}'
        state.frozen_identity_confirmed=True
    assoc=GlobalPlayerAssociator(registry,appearance_mode='enabled')
    one=body([100.,150.,150.,300.],1);two=body([90.,100.,160.,310.],2)
    one.local_y_ft=two.local_y_ft=10.
    assoc.mapping[assoc.mapping_key(one)]='g2'
    registry.historical_bindings[('cam_1','1')]='g2'
    updates=assoc.process_tick([one,two],586.266667,{'cam_1':CourtOrientation.identity},tick=1)
    assert all(u.observation is not one for u in updates)
    assert assoc.mapping_key(one) not in assoc.mapping
    assert ('cam_1','1') not in registry.historical_bindings
    assert any(d.reason=='ambiguous_nested_person_box' for d in assoc.last_tick_decisions)


def test_net_merged_body_and_partial_body_are_both_ambiguous():
    # Actual 586.166s: broad P1 box covers white P3 while a weak P3 box
    # covers gray P1. Choosing the larger box alone still exchanges identities.
    one=body([961.40,128.64,1062.88,341.69],27,confidence=.779)
    two=body([950.49,132.75,1001.10,354.50],2,confidence=.2866)
    assert ambiguous_net_crowd_observations([one,two]) == {id(one),id(two)}


def test_known_p2_fragment_must_not_be_confused_with_two_player_net_crowd():
    # Actual whole-run 388.3s: old and new raw IDs both cover the same pink body.
    one=body([454.41,208.81,584.92,387.42],943,confidence=.596)
    two=body([455.04,219.33,550.71,388.52],946,confidence=.481)
    assert not ambiguous_net_crowd_observations([one,two],{id(one):'g2'})
    assert ambiguous_nested_observations([one,two])=={id(two)}
    assert ambiguous_net_crowd_observations([one,two],{id(one):'g2',id(two):'g3'})=={id(one),id(two)}


@pytest.mark.parametrize('case', ['camera','frame','far_from_net','weak','guided',
    'separate','invalid','same_track'])
def test_net_crowd_guard_requires_current_same_view_supported_overlap(case):
    one=body([961.40,128.64,1062.88,341.69],27,confidence=.779)
    two=body([950.49,132.75,1001.10,354.50],2,confidence=.2866)
    if case=='camera':two.view_id='cam_2'
    if case=='frame':two.source_frame_index+=2
    if case=='far_from_net':one.local_y_ft=two.local_y_ft=10.
    if case=='weak':two.confidence=.24
    if case=='guided':two.detection_origin='guided_roi'
    if case=='separate':two.bbox=[800.,100.,900.,350.]
    if case=='invalid':two.bbox=[1.,2.,float('nan'),4.]
    if case=='same_track':two.track_id=one.track_id
    assert not ambiguous_net_crowd_observations([one,two])
