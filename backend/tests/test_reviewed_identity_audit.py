import importlib.util
import json
from pathlib import Path

import pytest

spec=importlib.util.spec_from_file_location('reviewed_identity_audit',
    Path(__file__).resolve().parents[2]/'scripts/audit_reviewed_identity_samples.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


@pytest.mark.parametrize('case,verdict', [('correct','pass'),('swapped','wrong_identity'),
    ('projected','real_box_missing_or_misaligned'),('wrong_frame','source_frame_missing'),
    ('duplicate','duplicate_identity_on_body')])
def test_sparse_audit_requires_correct_identity_and_real_box_at_actual_source_frame(tmp_path,case,verdict):
    folder=tmp_path/'fused_player_overlay.playback';(folder/'generation').mkdir(parents=True)
    (folder/'manifest.json').write_text(json.dumps({'source_signature':'generation',
        'chunks':{'cam_2':{'19':'frame.json'}}}))
    person={'player_id':'Player_2','bbox':[100.,100.,150.,300.],'evidence_type':'base_observed'}
    if case=='swapped':person['player_id']='Player_1'
    if case=='projected':person['evidence_type']='cross_view_projected'
    people=[person]
    if case=='duplicate':people.append({**person,'player_id':'Player_1'})
    (folder/'generation/frame.json').write_text(json.dumps({'frames':[{
        'source_frame_index':23342 if case=='wrong_frame' else 23340,'players':people}]}))
    sample={'timestamp_seconds':389.033333,'view_id':'cam_2','source_frame_index':23340,
        'player_id':'Player_2','bbox':[100.,100.,150.,300.]}
    result=module.audit(tmp_path,{'samples':[sample]})
    assert result['results'][0]['verdict']==verdict
    assert result['verdict']==('pass' if case=='correct' else 'fail')
