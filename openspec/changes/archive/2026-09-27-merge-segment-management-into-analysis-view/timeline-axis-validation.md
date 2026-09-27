# Timeline axis validation

Date: 2026-09-27

## Selected material

- Capture take: `ct_6949bef776a5`
- Published segmentation run: `seg_7c7fa5687b56f90b` (40 active algorithm rallies; `timing_authority=source_pts`)
- Matching multiview analysis job: `job-e97318f10c` (`segmentationRunId` matches the run above)
- Reference view: `cam_1`, video `rec-126e7bdd17`
- Secondary view: `cam_2`, video `rec-e5105932b0`
- Sample: rally 2, `[17750, 23750)` ms; `effective_start_ms=17750` (no corrected start)
- Both source videos and PTS sidecars are present in the take directory on `/Volumes/Elements`.

## Mapping check

The matching job reports `cam_1` mapping `(offsetMs=0, rate=1)` and `cam_2` mapping `(offsetMs=36.1960218634, rate=0.9999709622516607)`. The same equations as `canonicalTimeToSourceTimeMs` and `sourceTimeToCanonicalTimeMs` were applied to the selected rally start:

| View | Canonical start | Source time | Round-trip canonical | Error |
| --- | ---: | ---: | ---: | ---: |
| cam_1 | 17750.000 ms | 17750.000 ms | 17750.000 ms | 0.000 ms |
| cam_2 | 17750.000 ms | 17785.681 ms | 17750.000 ms | 0.000 ms |

The reference camera is an identity mapping. The matching source-to-canonical round-trip test in `src/utils/multiviewDisplay.test.ts` passed (4 tests).

## Frame inspection

Frames were extracted from the real playback videos at cam_1 `17.750 s` and `20.000 s`, and cam_2 at the corresponding mapped source times `17.786 s` and `20.036 s`. The `17.750–23.750 s` sample window shows the serve and rally sequence in both camera views; at 20 seconds both views show the ball in play. This supports the canonical-axis interpretation and shows no content-level systematic offset. The cameras' embedded wall clocks have only one-second precision, so this visual check does not claim frame-level synchronization beyond the job's reported mapping.
