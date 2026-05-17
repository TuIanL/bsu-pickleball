## Why

The current real-video pipeline can render player boxes, RTMPose skeletons, and court-projected movement, but it cannot yet represent pickleball-specific targets such as the ball or paddle. This blocks the next stage of tactical analysis because rally events, shot paths, contact candidates, and doubles decisions all require a reliable ball trajectory contract before higher-level logic is credible.

## What Changes

- Add a first-phase multi-target perception contract for `player`, `ball`, and `paddle` detections while preserving the current person-only player tracking path.
- Add backend artifacts for ball detections and repaired ball trajectory points, including explicit observed, predicted, repaired, unavailable, and partial states.
- Introduce a configurable multi-class detector adapter boundary so future pickleball-optimized YOLO models can emit ball and paddle detections without changing analysis APIs.
- Add an MVP ball trajectory continuity stage that can filter implausible detections and repair short gaps with clear confidence and source labeling.
- Expose ball overlay artifacts to completed real jobs and render ball points/trajectory in the visual analysis workspace only when true artifact data is available.
- Keep shot events, rally segmentation, tactical decision rules, motion blur preprocessing, and realtime streaming latency guarantees out of this first phase.

## Capabilities

### New Capabilities
- `multitarget-perception`: Covers normalized multi-class detection for players, balls, and paddles, detector adapter behavior, configuration, and unavailable states.
- `ball-tracking`: Covers ball detection artifacts, ball trajectory continuity, gap repair semantics, and ball overlay artifact retrieval.

### Modified Capabilities
- `player-tracking-engine`: Existing person/player detection and tracking behavior must continue to work while sharing normalized multi-target detection contracts where appropriate.
- `video-analysis-job-flow`: Completed real analysis results must expose ball-tracking stage status and artifact metadata when ball tracking is configured or skipped.
- `visual-analysis-workspace`: The workspace must render true ball overlays from backend artifacts and preserve clear unavailable states instead of using demo shot paths for real jobs.

## Impact

- Backend schemas: multi-target detection records, ball trajectory points, ball overlay artifacts, pipeline artifact references, and stage statuses.
- Backend vision modules: detector adapter boundary, optional multi-class detector implementation, ball trajectory continuity module, and tests with fixture outputs.
- Backend pipeline: persist ball detection/trajectory artifacts alongside existing tracking and pose artifacts without breaking person overlay generation.
- Frontend types/services: raw pipeline result metadata, ball overlay artifact fetcher, and source-aware report adaptation.
- Frontend workspace: optional ball point/trajectory layer controls, synchronized rendering, and unavailable/partial states.
- Tests and fixtures: backend serialization and trajectory repair tests, frontend artifact parsing/rendering checks, and regression coverage that current person overlays still work.
