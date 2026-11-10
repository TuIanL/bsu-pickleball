import json

from app.services.overlay_playback import publish_overlay_playback, read_playback_manifest, playback_chunk_path


def test_playback_slices_camera_and_time_without_changing_evidence(tmp_path):
    payload={'job_id':'j', 'reference_view_id':'cam_1', 'source':{'width':100,'height':100},
             'frames':[], 'views':{
                 v:{'status':'available','frames':[{'timestamp_seconds':s,'subjects':[{'track_id':v}]} for s in (19.9,20.,39.9,40.)]}
                 for v in ('cam_1','cam_2')}}
    source=tmp_path/'pose_overlay.json';source.write_text(json.dumps(payload),encoding='utf-8')
    original=source.read_bytes()
    publish_overlay_playback(source,payload,artifact_name='pose-overlay')
    manifest=read_playback_manifest(source)
    assert source.read_bytes()==original
    assert manifest['metadata']['frames']==[]
    assert manifest['metadata']['views']['cam_2']['frames']==[]
    assert manifest['metadata']['playback']['chunks']['cam_2']==[0,1,2]
    part=playback_chunk_path(source,manifest,view_id='cam_2',chunk=1)
    frames=json.loads(part.read_text(encoding='utf-8'))['frames']
    assert [f['timestamp_seconds'] for f in frames]==[20.,39.9]
    assert all(f['subjects'][0]['track_id']=='cam_2' for f in frames)
    assert playback_chunk_path(source,manifest,view_id='../cam_1',chunk=1) is None
    assert playback_chunk_path(source,manifest,view_id='cam_1',chunk=99) is None
    source.write_text('{}',encoding='utf-8')
    assert read_playback_manifest(source) is None


def test_route_returns_shard_without_reading_large_source(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from fastapi.responses import FileResponse
    import app.api.routes_analysis as routes
    payload={'job_id':'j','frames':[], 'views':{'cam_2':{'frames':[{'timestamp_seconds':30.}]}}}
    source=tmp_path/'pose.json';source.write_text(json.dumps(payload),encoding='utf-8')
    publish_overlay_playback(source,payload,artifact_name='pose-overlay')
    def forbidden(*args):raise AssertionError('full evidence was parsed for playback')
    monkeypatch.setattr(routes,'get_mock_job',lambda _:SimpleNamespace(metadata=SimpleNamespace(capture_take_id=None)))
    monkeypatch.setattr(routes,'_STORAGE',SimpleNamespace(resolve_capture_job_root=lambda *a:tmp_path,
        pose_overlay_json_path=lambda _:source,read_json=forbidden))
    response=routes.read_analysis_artifact('j','pose-overlay',playback=True)
    metadata=json.loads(response.body)
    assert metadata['frames']==[]
    response=routes.read_analysis_artifact('j','pose-overlay',chunk=1,view_id='cam_2',generation=metadata['playback']['generation'])
    assert isinstance(response,FileResponse)
