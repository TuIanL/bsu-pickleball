# P1-B Acceptance Summary

## Scope

- Change: `make-p1-offline-refinement-effective`
- Capture take: `ct_6949bef776a5`
- Authoritative acceptance windows: `3.4s–60s` and `3.4s–698.8s`
- F0 source run: `mvr_0fab7956f67f`
- F1 replay run: `mvr_f1replay_20260812_1539`
- Full-take job: `job-c46cd7204c`
- Full-take joint run: `mvr_2d38699038c4`
- Timing: `cam_1=source_pts`, `cam_2=source_pts`
- Sync quality: `good`

## Regression

- F1 synthetic/offline refinement, fusion, executor publication, view tracking and metric tests: `35 passed` for the focused run.
- Full backend regression: `891 passed, 13 warnings`.
- OpenSpec validation: `131 passed, 0 failed`.

## Real 60-Second Result

The F1 recovery and formal re-fusion path completed successfully from the immutable F0 snapshot. It did not publish F1 because the safety gate rejected the candidate:

```text
recovered observations: 1931
candidate F1 samples:    20744
F1 eligible coverage:   0.5957891637
F0 eligible coverage:   0.5957891637
F1 conflict count:      82
allowed conflict delta:  2
F1 residual P50/P90:    2.0455 / 2.8192 ft
F1 speed violations:    22 (F0: 26)
original strong replaced: 0
donor inconsistencies:   0
verdict:                 rejected_by_safety_gate
final_source:            first_pass_f0
reject_reason:           conflicts_increased
```

This is an F1 execution success and a safety-gate rejection, not an F1 adoption. The Candidate F1 remains available for A/B analysis; the stable product result remains F0.

## Physical Artifact Checks

The replay directory contains:

- `f0_refinement_snapshot.v1.json`
- `fused_player_trajectory.f0.v2.json`
- `recovered_view_observations.v1.json`
- `fused_player_trajectory.f1.v2.json`
- `refinement_diagnostics.json`
- `f1_acceptance_summary.v1.json`

Ten deterministic recovered observations were sampled. For every sample, target bbox footpoint -> target homography -> target orientation reproduced the recovered canonical position with maximum error `0.0 ft`. The corresponding F1 view observation preserved `observation_origin=offline_refinement` and `source_pts/good` timing provenance.

F0 immutability was verified by SHA-256:

```text
fused_player_trajectory.f0.v2.json
1b15882e2138ed37f82bc767977842e3db9645c6aeae0a88ff37c1a05e81af41

f0_refinement_snapshot.v1.json
78cd98dd01ed9c2b9950835b0a5517f180472c7eb910133707766f1b1413fbb4
```

## Real Full-Take Result (Task 7.5)

The approximately 699-second authoritative run completed successfully:

```text
job:                  job-c46cd7204c
joint run:            mvr_2d38699038c4
window:               3.4s–698.8s
execution:            joint_authoritative
timing:               source_pts / source_pts
status:               completed / succeeded
wall-clock runtime:   18,740.9 seconds (about 5h 12m 21s)
```

Full-take F0/F1 and recovery metrics:

```text
recovery windows:             295
recovered observations:       71,310
F0 samples:                   223,484
candidate F1 samples:         228,096
F0 eligible coverage:         0.2060143916
F1 eligible coverage:         0.2060143916
F0/F1 jump violations:        7 / 4
F0/F1 speed violations:       264 / 117
F0/F1 conflict count:         0 / 418
recovered residual P50/P90:   0.9674 / 2.1627 ft
original strong preserved:    262,306
original strong replaced:     0
donor inconsistencies:        0
```

The Candidate F1 was generated and retained, but the safety gate rejected publication because the conflict delta was `+418`, above the configured allowance of `+2`:

```text
status:       rejected_by_safety_gate
verdict:      rejected
reject_reason: conflicts_increased
final_source: first_pass_f0
```

This is a valid F1 execution and fallback result, not a failed run. F0 remains immutable and is the product result; Candidate F1 remains available for A/B analysis. The full-take artifacts are stored under:

```text
/Volumes/Elements/项目/匹克球/视频录制/captures/2026-07-20/take_sync_20260720_122645_317228/analysis/multiview/mvr_2d38699038c4/
```

## Final Status And Risks

P1-B implementation, the authoritative 60-second execution, and the approximately 699-second full-take validation are complete. The change demonstrates immutable F0 publication, offline recovery, formal re-fusion, Candidate F1 generation, safety-gate rejection, and correct F0 fallback. F1 adoption is not required for completion; the rejection is the expected safety outcome for this take under the frozen thresholds.

Remaining risks are experimental/product follow-ups rather than blockers for this change: full-take offline refinement currently takes about 5.2 hours on this Mac, and the full-take Candidate F1 is rejected by the conflict gate. Improving runtime and F1 acceptance rate belongs to a subsequent evaluation or optimization change.
