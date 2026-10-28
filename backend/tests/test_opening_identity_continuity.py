"""Opening recovery must not wait for all four roster slots to fill."""
import pytest

from app.vision.multiview.association_global import GlobalPlayerAssociator, JointObservation
from app.vision.multiview.court_frame import CourtOrientation
from app.vision.multiview.global_state import GlobalPlayerRegistry, ViewBinding


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
