import pytest

from app.vision.multiview.association_global import GlobalPlayerAssociator, JointObservation
from app.vision.multiview.court_frame import CourtOrientation
from app.vision.multiview.global_state import GlobalPlayerRegistry


def setup():
    registry=GlobalPlayerRegistry(frozen_player_end_by_id={
        f'Player_{i}':'end_a' if i<=2 else 'end_b' for i in range(1,5)})
    for i in range(1,5):
        state=registry.ensure(f'g{i}')
        state.frozen_player_id=f'Player_{i}'
        state.frozen_identity_confirmed=True
    return registry,GlobalPlayerAssociator(registry)


def test_merged_net_track_with_opponents_feet_cannot_transfer_to_opposing_slot():
    registry,associator=setup()
    # Actual merged white/gray box at 586s: track was bound to far-side P3,
    # but bbox feet are on near-side P1. Abstain for this view rather than rename.
    obs=JointObservation('cam_2',35158,586000.,12.1144,24.0968,
        track_id=27,confidence=.761,bbox=[951.,126.,1055.,364.])
    associator.mapping[associator.mapping_key(obs)]='g3'
    registry.historical_bindings['cam_2','27']='g3'
    updates=associator.process_tick([obs],586.,{'cam_2':CourtOrientation.rotate_180},tick=525)
    assert not updates
    assert associator.mapping[associator.mapping_key(obs)]=='g3'
    assert any(d.reason=='frozen_net_end_conflict' for d in associator.last_tick_decisions)


@pytest.mark.parametrize('y,expected',[(19.9,False),(22.,True),(23.,True),(24.,True),(45.,True)])
def test_fixed_end_pair_gate_keeps_existing_net_tolerance_and_baseline_buffer(y,expected):
    _,associator=setup()
    obs=JointObservation('cam_1',1,1000.,10.,y,canonical_x_ft=10.,canonical_y_ft=y)
    assert associator._identity_allowed(obs,'g3') is expected


def test_end_gate_does_not_assign_unknown_identities_by_court_side():
    registry,associator=setup()
    registry.players['g3'].frozen_identity_confirmed=False
    obs=JointObservation('cam_1',1,1000.,10.,8.,canonical_x_ft=10.,canonical_y_ft=8.)
    assert associator._identity_allowed(obs,'g3')
    assert associator._identity_allowed(obs,None)
