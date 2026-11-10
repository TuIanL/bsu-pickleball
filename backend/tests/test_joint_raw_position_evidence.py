from types import SimpleNamespace

import pytest

from app.schemas.tracking import PlayerFramePosition
from app.vision.multiview.multiview_joint_run import MultiViewJointRun


def result(candidate):
    # Actual gray P1 frame: local smoothing reported 20.19ft while the current
    # measured foot projects to 24.25ft, on the opposite side of the net.
    position = PlayerFramePosition(frame_index=35182, timestamp=586.366667, track_id=67,
        bbox=[941.017,135.754,993.059,365.428], image_footpoint=[967.038,365.428],
        court_position=[11.2689,20.1904], confidence=.5595, projection_confidence=.9)
    detection = SimpleNamespace(track_id=67,player_id='Player_2',source_height=1080,confidence=.5595)
    return SimpleNamespace(frame_index=35182,mapped_take_timestamp_ms=586400.,
        frame_positions=[position],frame_detections=[] if candidate else [detection],
        candidate_positions=[position],candidate_detections=[detection] if candidate else [],
        render_raw_by_track={67:{'x_ft':11.104,'y_ft':24.2475}}), position


@pytest.mark.parametrize('candidate',[False,True])
def test_joint_associates_raw_current_feet_instead_of_lagging_local_track_position(candidate):
    frame,position = result(candidate)
    method = MultiViewJointRun._result_to_candidate_observations if candidate else MultiViewJointRun._result_to_observations
    observations = method('cam_2',frame,586400.)
    assert len(observations)==1
    obs = observations[0]
    assert (obs.local_x_ft,obs.local_y_ft)==(11.104,24.2475)
    assert obs.court_position_source=='raw_projection'
    assert obs.source_frame_index==35182 and obs.image_footpoint==(967.038,365.428)
    assert position.court_position==[11.2689,20.1904]


@pytest.mark.parametrize('candidate',[False,True])
def test_invalid_raw_projection_cannot_fall_back_to_stale_coordinates(candidate):
    frame,_ = result(candidate)
    frame.render_raw_by_track[67]['y_ft']=float('nan')
    method = MultiViewJointRun._result_to_candidate_observations if candidate else MultiViewJointRun._result_to_observations
    assert method('cam_2',frame,586400.)==[]


def test_legacy_adapter_without_raw_measurements_remains_supported():
    frame,_ = result(False)
    del frame.render_raw_by_track
    observation=MultiViewJointRun._result_to_observations('cam_2',frame,586400.)[0]
    assert observation.local_y_ft==20.1904 and observation.court_position_source=='legacy_position'
