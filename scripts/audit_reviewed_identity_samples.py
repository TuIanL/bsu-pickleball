"""Compare formal real boxes with sparse source-frame identity samples.

These samples are assistant-reviewed, not independent exhaustive ground truth.
Passing this check only certifies the reviewed source frames and IDs.
"""
import argparse
import json
import math
from pathlib import Path


def read(path):
    with path.open(encoding='utf-8') as handle:
        return json.load(handle)


def iou(one,two):
    if not one or not two:
        return 0.
    a,b,c,d=one; x,y,z,w=two
    overlap=max(0.,min(c,z)-max(a,x))*max(0.,min(d,w)-max(b,y))
    union=max(0.,c-a)*max(0.,d-b)+max(0.,z-x)*max(0.,w-y)-overlap
    return overlap/union if union else 0.


def audit(job_root,samples):
    folder=job_root/'fused_player_overlay.playback'
    manifest=read(folder/'manifest.json'); cache={};results=[]
    for sample in samples['samples']:
        view=sample['view_id'];bucket=str(math.floor(sample['timestamp_seconds']/20))
        key=view,bucket
        if key not in cache:
            filename=manifest['chunks'].get(view,{}).get(bucket)
            cache[key]=read(folder/manifest['source_signature']/filename)['frames'] if filename else []
        frames=[f for f in cache[key] if f.get('source_frame_index')==sample['source_frame_index']]
        reason='source_frame_missing';overlap=0.;found=None
        if len(frames)==1:
            players=[p for p in frames[0]['players'] if p['evidence_type'] in
                {'base_observed','guided_observed','refined_observed'} and p.get('bbox')]
            same=next((p for p in players if p['player_id']==sample['player_id']),None)
            overlap=iou(sample['bbox'],same['bbox']) if same else 0.
            wrong=[p for p in players if p['player_id']!=sample['player_id']
                and iou(sample['bbox'],p['bbox'])>=.5]
            found=wrong[0]['player_id'] if wrong else None
            reason='duplicate_identity_on_body' if wrong and overlap>=.5 else (
                'pass' if overlap>=.5 else 'wrong_identity' if wrong else 'real_box_missing_or_misaligned')
        results.append({**sample,'verdict':reason,'iou':round(overlap,4),'conflicting_player_id':found})
    failures=[r for r in results if r['verdict']!='pass']
    return {'job_id':job_root.name,'sample_count':len(results),'passed_samples':len(results)-len(failures),
        'verdict':'pass' if results and not failures else 'fail',
        'scope':'Sparse assistant-reviewed source boxes; not full-video ID accuracy.',
        'source_review':samples.get('reviewer'),'failures':failures,'results':results}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job-root',required=True,type=Path)
    parser.add_argument('--samples',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();result=audit(args.job_root,read(args.samples))
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='results'},ensure_ascii=False,indent=2))
