"""Opening recovery must not wait for all four roster slots to fill."""
import pytest
from types import SimpleNamespace

from app.schemas.tracking import PlayerFramePosition
from app.vision.multiview.association_global import GlobalPlayerAssociator, JointObservation
from app.vision.multiview.court_frame import CourtOrientation
from app.vision.multiview.global_state import GlobalPlayerRegistry, ViewBinding
from app.vision.multiview.multiview_joint_run import MultiViewJointRun


@pytest.mark.parametrize("guard", [None, "unknown", "stale", "far", "epoch", "other_track"])
def test_partial_roster_candidate_continues_only_fresh_same_track_history(guard):
    registry=GlobalPlayerRegistry(frozen_player_end_by_id={f"Player_{i}":"end_a" if i<=2 else "end_b" for i in range(1,5)})
    for gid,x in [("global_player_3",17),("global_player_4",10)]:
        state=registry.ensure(gid);state.roster_status="provisional";state.roster_end="end_b"
        state.x_ft,state.y_ft=x,38;state.last_seen_s=.1
        registry.estimator.update(gid,x,38,.1)
    target=registry.players["global_player_4"]
    registry.historical_bindings[("cam_1","15")]='global_player_4'
    if guard in {"epoch","other_track"}:
        target.view_bindings['cam_1']=ViewBinding(track_id=15 if guard=='epoch' else 99,local_identity_epoch=1 if guard=='epoch' else 0,visibility='observed')
    associator=GlobalPlayerAssociator(registry)
    accepted=[]
    for tick in range(1,5):
        ts=(10 if guard=='stale' else .1)+tick/30
        obs=JointObservation('cam_1',tick,ts*1000,20 if guard=='far' else 10,38,
            track_id=25 if guard=='unknown' else 15,confidence=.9,tracking_status='candidate')
        updates=associator.process_tick([],ts,{'cam_1':CourtOrientation.identity},tick=tick,candidate_observations=[obs],available_views={'cam_1'})
        accepted.extend(u for u in updates if not u.tentative and not u.quarantined)
    if guard:
        assert accepted==[]
    else:
        assert accepted and {u.global_id for u in accepted}=={'global_player_4'}
        assert len(registry.players)==2
        assert associator.diagnostics['candidate_lineage_continuity']>=1


def test_recovered_candidate_does_not_promote_duplicate_into_empty_slot():
    registry=GlobalPlayerRegistry(frozen_player_end_by_id={f'Player_{i}':'end_a' if i<=2 else 'end_b' for i in range(1,5)})
    state=registry.ensure('global_player_1');state.roster_status='confirmed';state.roster_end='end_a'
    state.x_ft,state.y_ft=5,8;state.last_seen_s=0;registry.estimator.update(state.global_player_id,5,8,0)
    associator=GlobalPlayerAssociator(registry)
    associator.mapping[('cam_1','1',0)]=state.global_player_id
    for tick in range(1,9):
        ts=tick/30
        donor=JointObservation('cam_1',tick,ts*1000,5,8,track_id=1,confidence=.9)
        candidate=JointObservation('cam_2',tick,ts*1000,5.1,8,track_id=25,confidence=.9,tracking_status='candidate')
        updates=associator.process_tick([donor],ts,{'cam_1':CourtOrientation.identity,'cam_2':CourtOrientation.identity},tick=tick,candidate_observations=[candidate])
        for gid,(x,y,_) in associator.fuse_assignments(updates).items():registry.absorb_measurement(gid,x,y,ts)
    assert list(registry.players)==['global_player_1']
    assert associator.diagnostics['unmatched_recovery_accepted']>0


@pytest.mark.parametrize('point,admission',[([-1,8],False),([5,46],True)])
def test_visible_outside_candidate_is_recovery_only_and_preserves_appearance(point,admission):
    p=PlayerFramePosition(frame_index=1,timestamp=.1,track_id=26,bbox=[100,100,200,400],image_footpoint=[150,400],court_position=point,confidence=.9,projection_confidence=.9,valid=False,is_inside_court=False,projection_status='outside_court_visible')
    descriptor=object()
    result=SimpleNamespace(frame_index=1,candidate_positions=[p],candidate_detections=[SimpleNamespace(track_id=26,confidence=.9,source_height=1080)],appearance_by_track={26:descriptor})
    assert MultiViewJointRun._result_to_candidate_observations('cam_1',result,100)==[]
    observations=MultiViewJointRun._result_to_candidate_observations('cam_1',result,100,allow_visible_outside=True)
    assert len(observations)==1 and observations[0].roster_admission_eligible is admission
    assert observations[0].appearance_descriptor is descriptor
    p.projection_status='outside_tracking_area'
    assert MultiViewJointRun._result_to_candidate_observations('cam_1',result,100,allow_visible_outside=True)==[]


@pytest.mark.parametrize('known',[False,True])
def test_unknown_outside_candidate_cannot_fill_roster_slot(known):
    registry=GlobalPlayerRegistry(frozen_player_end_by_id={f'Player_{i}':'end_a' if i<=2 else 'end_b' for i in range(1,5)})
    associator=GlobalPlayerAssociator(registry)
    if known:
        state=registry.ensure('global_player_1');state.roster_status='confirmed';state.roster_end='end_a'
        state.x_ft,state.y_ft=-1,8;state.last_seen_s=0;registry.estimator.update(state.global_player_id,-1,8,0)
        registry.historical_bindings[('cam_1','26')]=state.global_player_id
    accepted=[]
    for tick in range(10):
        obs=JointObservation('cam_1',tick,tick*33,-1,8,track_id=26,confidence=.9,tracking_status='candidate',roster_admission_eligible=False)
        accepted.extend(u for u in associator.process_tick([],tick/30,{'cam_1':CourtOrientation.identity},tick=tick,candidate_observations=[obs]) if not u.tentative)
    assert len(registry.players)==int(known) and not registry.candidates
    assert bool(accepted)==known


@pytest.mark.parametrize('dual',[False,True])
def test_players_in_baseline_buffer_initialize_only_with_dual_evidence(dual):
    registry=GlobalPlayerRegistry(frozen_player_end_by_id={f'Player_{i}':'end_a' if i<=2 else 'end_b' for i in range(1,5)})
    associator=GlobalPlayerAssociator(registry)
    for tick in range(1,7):
        observations=[JointObservation(view,tick,tick*33,5,46,track_id=track,confidence=.9,tracking_status='candidate') for view,track in [('cam_1',1),*([('cam_2',2)] if dual else [])]]
        updates=associator.process_tick([],tick/30,{'cam_1':CourtOrientation.identity,'cam_2':CourtOrientation.identity},tick=tick,candidate_observations=observations)
        for gid,(x,y,_) in associator.fuse_assignments(updates).items():registry.absorb_measurement(gid,x,y,tick/30)
    assert len(registry.players)==(1 if dual else 0)
    if dual:assert registry.players['global_player_3'].roster_end=='end_b'
