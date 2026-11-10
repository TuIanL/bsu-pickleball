"""Audit persisted joint people/pose/2D-ball contracts without running inference.

Usage: python scripts/audit_joint_basic_delivery.py --job-root <analysis/job-ID>
       --output <report.json> [--start 30 --end 587.15]
Physical identity still requires reviewing the source video; coverage is not ID accuracy.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path


def read(path):
    with path.open(encoding='utf-8') as handle:
        return json.load(handle)


def trajectory_samples(path):
    """Read the known trajectory samples array with bounded memory."""
    decoder=json.JSONDecoder()
    with path.open(encoding='utf-8') as handle:
        buffer=''
        while True:
            chunk=handle.read(65536)
            if not chunk:
                raise ValueError('Trajectory samples array missing')
            buffer+=chunk
            match=re.search(r'"samples"\s*:\s*\[',buffer)
            if match:
                buffer=buffer[match.end():]
                break
            if len(buffer)>1024*1024:
                raise ValueError('Unexpected trajectory header')
        while True:
            buffer=buffer.lstrip(' \r\n\t,')
            if buffer.startswith(']'):
                return
            try:
                row,offset=decoder.raw_decode(buffer)
            except json.JSONDecodeError:
                chunk=handle.read(65536)
                if not chunk:
                    raise ValueError('Truncated trajectory samples')
                buffer+=chunk
                continue
            yield row
            buffer=buffer[offset:]


def audit(root: Path, start: float, end: float):
    report = {'job_id': root.name, 'requested_window_seconds': [start, end],
              'physical_identity_verdict': 'requires_source_video_review',
              'notice': 'Contract checks do not prove physical identity or ball detection precision.',
              'tracking_reused': (root/'tracking_recovery_lineage.json').exists(), 'errors': Counter()}
    quality = read(root/'four_player_identification_quality.json')
    report['original_four_player_verdict'] = quality['verdict']
    report['original_failure_reasons'] = quality.get('failure_reasons')
    report['players'] = {pid: {k: row.get(k) for k in (
        'detection_coverage','canonical_coverage','longest_gap_seconds','cross_side_count')}
        for pid,row in quality['players'].items()}
    roster = read(root/'roster.json')
    observed_by_global = {p['global_player_id']:set() for p in roster['players']}
    for row in trajectory_samples(root/'fused_player_trajectory.json'):
        if (row['global_player_id'] in observed_by_global and start<=row['timestamp_seconds']<=end
                and row.get('metric_eligible') and row.get('identity_status') in {'confirmed_observed','confirmed_recovered'}):
            observed_by_global[row['global_player_id']].add(float(row['timestamp_seconds']))
    for person in roster['players']:
        gid,pid = person['global_player_id'],person['player_id']
        observed = sorted(observed_by_global[gid])
        spans = zip([start,*observed],[*observed,end])
        report['players'][pid]['missing_spans_over_half_second'] = [
            {'start':a,'end':b,'seconds':round(b-a,6)} for a,b in spans if b-a>.5]
    people_manifest = read(root/'fused_player_overlay.playback/manifest.json')
    pose_manifest = read(root/'pose_overlay.playback/manifest.json')
    ball = read(root/'ball_trajectory.json')
    errors = report['errors']
    expected_views = set(people_manifest['metadata']['views'])
    if len(expected_views) != 2 or set(pose_manifest['chunks']) != expected_views or set(ball['views']) != expected_views:
        errors['missing_joint_camera'] += 1
    for layer, manifest in (('fused_player_overlay', people_manifest), ('pose_overlay', pose_manifest)):
        stat = (root/(layer+'.json')).stat()
        if manifest['source_signature'] != f'{stat.st_size}-{stat.st_mtime_ns}':
            errors['stale_playback_index'] += 1
    stride = int(pose_manifest['metadata']['timing_provenance']['sample_stride'])
    pose_times_by_player = {pid:set() for pid in report['players']}
    all_pose_times = set()
    views = {}
    for view in people_manifest['chunks']:
        counts = Counter()
        per_player = Counter()
        keypoints = {pid:Counter() for pid in report['players']}
        pose_times = set()
        people_times = set()
        for bucket,filename in people_manifest['chunks'][view].items():
            rows = read(root/'fused_player_overlay.playback'/people_manifest['source_signature']/filename)['frames']
            lookup = {round(row['timestamp_seconds'],6):row for row in rows}
            people_times.update(t for t in lookup if start<=t<end)
            poses_filename = pose_manifest['chunks'].get(view,{}).get(bucket)
            poses = read(root/'pose_overlay.playback'/pose_manifest['source_signature']/poses_filename)['frames'] if poses_filename else []
            for frame in poses:
                if not start<=frame['timestamp_seconds']<end:
                    continue
                counts['pose_frames'] += 1
                timestamp = round(frame['timestamp_seconds'],6)
                if timestamp in pose_times:
                    errors['duplicate_pose_timestamp'] += 1
                pose_times.add(timestamp)
                all_pose_times.add(timestamp)
                source = lookup.get(round(frame['timestamp_seconds'],6))
                if source is None or source.get('source_frame_index') != frame['frame_index']:
                    errors['pose_source_frame_mismatch'] += 1
                authoritative = {p['player_id']:p for p in source.get('players',[]) if p.get('evidence_type')
                    in {'base_observed','guided_observed','refined_observed'}} if source else {}
                ids = [s['track_id'] for s in frame['subjects']]
                errors['duplicate_pose_identity'] += len(ids)-len(set(ids))
                for subject in frame['subjects']:
                    counts['pose_subjects'] += 1
                    per_player[subject['track_id']] += 1
                    if subject['track_id'] in pose_times_by_player:
                        pose_times_by_player[subject['track_id']].add(timestamp)
                        for point in subject.get('keypoints',[]):
                            keypoints[subject['track_id']]['count'] += 1
                            keypoints[subject['track_id']]['confidence_sum'] += point['confidence']
                            keypoints[subject['track_id']]['visible_count'] += bool(point['visible'])
                    original = authoritative.get(subject['track_id'])
                    if original is None:
                        errors['pose_without_same_view_observed_box'] += 1
                    else:
                        size=people_manifest['metadata']['views'][view]['source']
                        x1,y1,x2,y2=original['bbox']
                        clipped=[max(0.,x1),max(0.,y1),min(size['width'],x2),min(size['height'],y2)]
                        if any(abs(float(a)-float(b))>1. for a,b in zip(subject['bbox'],clipped)):
                            errors['pose_identity_box_mismatch'] += 1
            ball_rows = [row for row in ball['views'][view]['samples']
                if math.floor(row['timestamp_sec']/20)==int(bucket) and start<=row['timestamp_sec']<end]
            for sample in ball_rows:
                counts['ball_frames'] += 1
                source = lookup.get(round(sample['timestamp_sec'],6))
                if source is None or source.get('source_frame_index') != sample['frame_index']:
                    errors['ball_source_frame_mismatch'] += 1
                if sample.get('accepted'):
                    counts['accepted_ball_frames'] += 1
                    point = sample.get('image_xy')
                    if (not isinstance(point,list) or len(point)!=2 or not all(math.isfinite(v) for v in point)
                            or sample.get('interpolated') or sample.get('source') in {'prediction','predicted','missing_frame'}):
                        errors['ball_prediction_or_invalid_observation_published'] += 1
        if not people_times or not counts['pose_subjects'] or not counts['accepted_ball_frames']:
            errors['empty_joint_visual_layer'] += 1
        if not pose_times or abs(len(pose_times)*stride-len(people_times)) > stride:
            errors['incomplete_pose_timeline'] += 1
        if counts['ball_frames'] != len(people_times):
            errors['incomplete_ball_timeline'] += 1
        views[view] = {**dict(counts), 'people_frames':len(people_times),
            'pose_subjects_by_player': dict(per_player),
            'keypoints_by_player': {pid:{'count':k['count'], 'visible_count':k['visible_count'],
                'mean_confidence':round(k['confidence_sum']/k['count'],6) if k['count'] else None}
                for pid,k in keypoints.items()}}
    report['views'] = views
    report['pose_sampling_stride'] = stride
    report['pose_presence_any_camera'] = {pid:{'sampled_timestamps':len(times),
        'timeline_timestamps':len(all_pose_times),
        'fraction':len(times)/len(all_pose_times) if all_pose_times else 0.}
        for pid,times in pose_times_by_player.items()}
    report['errors'] = {k:v for k,v in errors.items() if v}
    report['basic_contract_verdict'] = 'fail' if report['errors'] else 'pass'
    return report


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--start',type=float,default=30.)
    parser.add_argument('--end',type=float,default=587.15)
    args=parser.parse_args()
    report=audit(args.job_root,args.start,args.end)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
