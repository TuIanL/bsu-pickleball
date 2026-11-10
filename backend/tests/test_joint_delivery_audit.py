"""Delivery audit must fail for missing evidence, not merely parse valid JSON."""
import importlib.util
import json
from pathlib import Path

from app.services.overlay_playback import publish_overlay_playback

spec = importlib.util.spec_from_file_location(
    'delivery_audit', Path(__file__).resolve().parents[2]/'scripts/audit_joint_basic_delivery.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def evidence(root):
    def write(name, data):
        (root/name).write_text(json.dumps(data), encoding='utf-8')
    write('four_player_identification_quality.json', {'verdict':'fail',
        'failure_reasons':['existing_failure'], 'players':{'Player_1':{}}})
    write('fused_player_trajectory.json', {'samples':[]})
    write('roster.json', {'players':[{'global_player_id':'g1','player_id':'Player_1'}]})
    source = {'width':100,'height':100}
    people = {'job_id':'test', 'views':{v:{'source':source,'frames':[
        {'timestamp_seconds':t, 'source_frame_index':index, 'players':[
            {'player_id':'Player_1','bbox':[10,10,30,50],'evidence_type':'base_observed'}]}
        for t,index in ((0.,0),(.033333,2))]} for v in ('cam_1','cam_2')}}
    pose = {'job_id':'test', 'timing_provenance':{'sample_stride':2},
        'views':{v:{'frames':[{'timestamp_seconds':0.,'frame_index':0,'subjects':[
            {'track_id':'Player_1','bbox':[10,10,30,50], 'keypoints':[
                {'confidence':.8,'visible':True}]}]}]} for v in people['views']}}
    for name,payload in (('fused_player_overlay',people),('pose_overlay',pose)):
        write(name+'.json',payload)
        publish_overlay_playback(root/(name+'.json'),payload,artifact_name=name)
    ball={'views':{v:{'samples':[{'timestamp_sec':t,'frame_index':i,'accepted':True,
        'image_xy':[40,40],'source':'detected'} for t,i in ((0.,0),(.033333,2))]}
        for v in people['views']}}
    write('ball_trajectory.json',ball)
    return pose,ball,write


def test_contract_pass_keeps_failed_identity_verdict(tmp_path):
    evidence(tmp_path)
    report=module.audit(tmp_path,0.,.066666)
    assert report['basic_contract_verdict']=='pass'
    assert report['original_four_player_verdict']=='fail'
    assert report['physical_identity_verdict']=='requires_source_video_review'


def test_audit_detects_wrong_camera_source_frame_and_prediction(tmp_path):
    pose,ball,write=evidence(tmp_path)
    pose['views']['cam_2']['frames'][0]['frame_index']=2
    write('pose_overlay.json',pose)
    publish_overlay_playback(tmp_path/'pose_overlay.json',pose,artifact_name='pose-overlay')
    ball['views']['cam_1']['samples'][0]['source']='prediction'
    write('ball_trajectory.json',ball)
    report=module.audit(tmp_path,0.,.066666)
    assert report['basic_contract_verdict']=='fail'
    assert report['errors']['pose_source_frame_mismatch']==1
    assert report['errors']['ball_prediction_or_invalid_observation_published']==1


def test_empty_pose_layer_and_partial_ball_timeline_fail(tmp_path):
    pose,ball,write=evidence(tmp_path)
    pose['views']['cam_2']['frames']=[]
    write('pose_overlay.json',pose)
    publish_overlay_playback(tmp_path/'pose_overlay.json',pose,artifact_name='pose-overlay')
    ball['views']['cam_1']['samples'].pop()
    write('ball_trajectory.json',ball)
    report=module.audit(tmp_path,0.,.066666)
    assert report['errors']['empty_joint_visual_layer']==1
    assert report['errors']['incomplete_pose_timeline']==1
    assert report['errors']['incomplete_ball_timeline']==1
