## Hybrid segmented ball trajectory acceptance

Date: 2026-08-24

### Real 60-second source

- Recording: `sync_20260720_122645_317228`
- Capture take: `ct_6949bef776a5`
- Window: `0.00-60.00s`
- Source FPS / stride: `60 / 2`
- Historical completed job: `job-36ce8da485`
- New immutable v4 acceptance job: `job-71166f62f7` (`completed`, 2026-08-24 08:12:40 CST)

### Historical canonical v3 versus hybrid target

| Measure | Historical v3 | Hybrid acceptance target |
| --- | ---: | ---: |
| Schema | `reconstructed_ball_trajectory.v3` | `reconstructed_ball_trajectory.v4` |
| Full-window curves | 1 | 0 (event-separated only) |
| Stereo measurements / anchors | 26 | Same evidence retained; only qualified anchors constrain a segment |
| Accepted single-view observations | 1,572 | Reused per flight and per source view |
| Stereo coverage | 3.3% | Segment-specific; does not gate all display delivery |
| Reprojection error | 197.502 px | Bad pairings remain audit-only |
| Prediction ratio | 96.7% | Per-segment provenance; predicted intervals are dashed and metric-ineligible |
| Events | 0 | Hit/bounce/loss/serve reset/EOS boundaries when resolved |
| 3D overall status | `UNAVAILABLE` | May remain `UNAVAILABLE` |
| Display trajectory | Not published | Must be `degraded` or `available` when a 2.5D segment passes |

### Real v4 acceptance result

- Schema / overall / display: `reconstructed_ball_trajectory.v4` / `PARTIAL_3D` / `available`.
- 90 event-separated segments: 86 `single_view_event_anchored_2_5d`, 1 `stereo_anchored_2_5d`, 1 `stereo_estimated_3d`, and 2 unavailable short segments.
- 88 displayable segments; 72 formal report arcs after excluding unavailable and environment-outlier evidence.
- Dynamic primary view selection: 37 `cam_1` segments and 53 `cam_2` segments.
- 85 merged boundary events; segment endpoints comprise 73 hits, 10 bounces, 6 losses, and 1 end-of-stream boundary.
- Endpoint outcomes: 40 in-court, 18 `legal_out_candidate`, 16 `calibration_uncertain`, and 16 `environment_outlier`.
- Stereo evidence retained: 26 measurements, 30.8% segment coverage, 0.021 px accepted-pair reprojection error. Average speed remains unavailable because the applicable segments are visualization-only.

### Fixed regression coverage

`backend/fixtures/ball_trajectory/hybrid-regression-cases.json` freezes the current 60-second source summary plus real-out, calibration-margin, environment-static, short-occlusion, stride-1, and stride-2 cases. The earlier immutable `job-96a28d6ff0-stride2-contact.json` remains the contact-direction-change fixture.

### Endpoint acceptance

- A continuous bounce outside the standard sideline but inside the play environment is retained at its estimated coordinates as `legal_out_candidate` with “可能界外落点，非自动判罚”.
- A point just outside the play environment but within calibration uncertainty is retained and degraded as `calibration_uncertain`.
- A far spectator/sign point with static, low-continuity, high-reprojection, and no-cross-view evidence is `environment_outlier`; it is visible only in diagnostics and excluded from formal curves.

### Presentation inspection

- Video adapter uses only the selected view's `image_paths_by_view`, clips to playback time, keeps a completed segment for 0.8 seconds, and does not project court coordinates into pixels.
- Detected, interpolated, and predicted runs use solid, transition-dash, and dashed/faded encodings.
- Every flight is a separate WebGL line; contact is a diamond, bounce is a ring, and loss/unknown is faded.
- The report card consumes the same artifact and displays one simplified arc per formal segment. `environment_outlier` is absent; real-out coordinates are not clamped.
- The historical selected job was reloaded in the local application and correctly remained unavailable, confirming old immutable artifacts are not silently rewritten.
- The v4 job was selected explicitly in the local application. The analysis video reported “球可见” and “图像空间球路 · 视觉估算”; the trajectory page exposed all 90 segments with real source-video times and endpoint encodings; the report rendered the same version as 72 formal simplified arcs.
- Manual boundary audit found no overlapping adjacent segment windows. It also exposed two cross-view duplicate bounce IDs (`bounce-1/2`) whose endpoint lookup could resolve to a later event. The merge now deterministically disambiguates duplicate IDs while preserving timestamps, with a regression test; future artifacts therefore keep each bounce endpoint on its own segment boundary.

### Automated acceptance gates

- Backend full suite: 1,297 passed (13 existing warnings).
- Frontend full suite: 78 files / 576 tests passed.
- TypeScript project build (`tsc -b`): passed.
- Vite production build: passed (2,578 modules transformed); existing chunk-size and mixed dynamic/static import warnings remain.
- `git diff --check`: passed.
