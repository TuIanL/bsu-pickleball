# Real Video Regression Summary

## Input and Jobs

- Input: `/Users/tuian/Downloads/测试视频25s.mp4`
- Video metadata: 24.736003 seconds, 1920x1080, H.264, 60 FPS
- Registered video: `video-4fd96ae339`
- Calibration: `calib-9b34b2a687`
- Match format: `doubles`
- Source FPS: `60`
- Frame stride: `5`
- Final job: `job-3a91cd44ed`
- Original baseline job: `job-5c706a00ad`
- Pre one-to-one comparison job: `job-65ed2ccfe6`

The final job was created with `requestNewVersion=true`. Historical jobs were not refreshed, overwritten, or deleted.

## Final Acceptance

Final artifacts were read from `job-3a91cd44ed`:

- `tracking-overlay`: 297 sampled frames, 1060 overlay detections
- `player-trajectories`: canonical identities are exactly `Player_1` through `Player_4`
- `player-render-trajectories`: 5031 render samples, 31 segments, schema `player-render-trajectory.v2`
- Overlay labels: `P1=285`, `P2=199`, `P3=283`, `P4=235`, `person=58`
- Same-frame track assigned to multiple players: `0`
- Same-frame player slot assigned to multiple tracks: `0`
- Trajectory coverage ratio: `0.9966329966`
- Reconnect diagnostics: `12` (`player_reconnected_after_track_change=7`, `player_reconnected_from_lost=5`)
- Identity diagnostics: `unmatched=68`, `filtered=208`, `lost=20`, `inactive=3`
- Duplicate-slot guard diagnostics: `4`, at source frames `620`, `1400`, `1405`, `1425`; each is explicitly recorded as `player slot already assigned by higher-priority track in this frame`

The final player track histories are:

| Player | Source track history |
| --- | --- |
| Player_1 | 1 |
| Player_2 | 4, 14, 17, 19, 32, 34 |
| Player_3 | 2 |
| Player_4 | 6, 12, 13, 18, 25, 26, 27, 31, 33 |

Observed recovery frames in the final diagnostics include `345`, `620`, `690`, `730`, `740`, `880`, `1140`, `1150`, `1300`, `1320`, `1350`, and `1430`; all retain the original canonical identity, primarily `Player_2` in this clip.

The longest continuous `person` interval is frames `0-55` across 12 sampled frames, about `0.917` seconds. Remaining person detections are short bootstrap, non-target, or explicitly diagnosed duplicate-candidate intervals; there is no long undiagnosed person interval.

## Baseline Comparison

| Job | P identities | person detections | duplicate track frames | duplicate slot frames | coverage |
| --- | --- | ---: | ---: | ---: | ---: |
| `job-5c706a00ad` | P1-P3 only | 609 | 0 | 0 | 0.996633 |
| `job-65ed2ccfe6` | P1-P4 | 323 | 0 | 4 | 0.996633 |
| `job-3a91cd44ed` | P1-P4 | 58 | 0 | 0 | 0.996633 |

The final run confirms that the identity recovery improvement survives a fresh analysis job. The residual risk is that this 25-second clip does not cover every possible multi-player crossing or long occlusion pattern; no appearance ReID was introduced.

