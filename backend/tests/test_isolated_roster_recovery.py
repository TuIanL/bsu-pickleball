from dataclasses import replace

import pytest

from app.vision.multiview.association_global import AssociationUpdate,GlobalPlayerAssociator,JointObservation
from app.vision.multiview.global_state import GlobalPlayerRegistry


def run(case=None):
    registry=GlobalPlayerRegistry(frozen_player_end_by_id={
        f'Player_{i}':'end_a' if i<=2 else 'end_b' for i in range(1,5)})
    for i,(x,y) in enumerate(((11.,12.),(23.7,26.2),(10.,31.),(16.,31.)),1):
        s=registry.ensure(f'g{i}');s.frozen_player_id=f'Player_{i}';s.frozen_identity_confirmed=True
        s.x_ft,s.y_ft=x,y;s.last_seen_s=386. if case=='stale' and i==2 else 388.3
    associator=GlobalPlayerAssociator(registry)
    peers=[AssociationUpdate(f'g{i}','cam_2',JointObservation('cam_2',23302,388400.,x,y,
        canonical_x_ft=x,canonical_y_ft=y,track_id=i,confidence=.8,bbox=box),.8)
        for i,x,y,box in [(1,11.,12.,[815.,207.,896.,457.]),
            (3,10.,31.,[885.,77.,949.,241.]),(4,16.,31.,[717.,90.,791.,238.])]]
    if case=='other_camera':
        peers.append(AssociationUpdate('g2','cam_1',JointObservation('cam_1',23304,388433.,17.5,19.15,
            canonical_x_ft=17.5,canonical_y_ft=19.15,confidence=.6,track_id=1621,bbox=[1243.,126.,1309.,205.]),.6))
    if case=='two_missing':peers.pop()
    if case=='weak_witness':peers[-1].observation.confidence=.45
    candidate=JointObservation('cam_2',23302,388400.,17.5,19.15,canonical_x_ft=17.5,
        canonical_y_ft=19.15,track_id=946,confidence=.82,bbox=[604.,217.,703.,365.],court_position_source='raw_projection')
    if case=='weak':candidate.confidence=.74
    if case=='outside':candidate.roster_admission_eligible=False
    if case=='wrong_end':candidate.canonical_y_ft=31.
    if case=='foreign_history':registry.historical_bindings['cam_2','946']='g1'
    if case=='overlap':peers[0].observation.bbox=list(candidate.bbox)
    if case=='near_teammate':candidate.canonical_x_ft=11.;candidate.canonical_y_ft=12.
    if case=='no_box':candidate.bbox=None
    if case=='smoothed':candidate.court_position_source='legacy_position'
    recovered=[]
    for tick in range(1,4):
        if case=='brief_witness_dip':peers[-1].observation.confidence=.8 if tick==1 else .45
        obs=replace(candidate,source_frame_index=23302 if case=='repeated_frame' else 23302+tick*2,
            take_timestamp_ms=388400.+tick*33.333,
            canonical_x_ft=17.5+tick*2 if case=='position_jump' else candidate.canonical_x_ft)
        if case=='clothing_conflict':associator._frozen_appearance_owners[id(obs)]='g1'
        observations=[obs,replace(obs,track_id=947)] if case=='ambiguous' else [obs]
        updates=list(peers)
        associator._recover_isolated_roster_measurements(observations,updates=updates,
            timestamp_s=obs.take_timestamp_ms/1000+(.1 if case=='clock' else 0),tick=tick,
            available_views={'cam_1'} if case=='unavailable' else {'cam_1','cam_2'})
        recovered.extend(u for u in updates if u not in peers)
    return registry,associator,recovered


@pytest.mark.parametrize('case',[None,'other_camera','brief_witness_dip'])
def test_isolated_real_person_can_recover_missing_camera_with_three_current_witnesses(case):
    registry,associator,recovered=run(case)
    assert len(recovered)==1
    assert recovered[0].global_id=='g2' and recovered[0].view_id=='cam_2'
    assert recovered[0].reanchor and not recovered[0].tentative
    assert registry.historical_bindings['cam_2','946']=='g2'
    assert associator.last_tick_decisions[-1].reason=='isolated_roster_reacquired'


@pytest.mark.parametrize('case',['stale','two_missing','weak','outside','wrong_end','foreign_history',
    'overlap','near_teammate','no_box','smoothed','repeated_frame','position_jump','clothing_conflict',
    'ambiguous','clock','unavailable','weak_witness'])
def test_isolated_recovery_requires_recent_unique_real_and_independent_evidence(case):
    _,_,recovered=run(case)
    assert not recovered
