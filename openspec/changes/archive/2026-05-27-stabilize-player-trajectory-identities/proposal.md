## Why

Real doubles matches only have four on-court players, but the current player tracking output can fragment one player into many `track_id` trajectories when YOLO detections are lost, players overlap, or players briefly leave the camera view. This makes downstream movement distance, speed, heatmap, and doubles positioning metrics unreliable because they consume temporary tracker identities instead of stable real-player identities.

## What Changes

- Add a player identity management layer that maps temporary tracker `track_id` values into at most four stable `player_id` trajectories for doubles analysis.
- Introduce canonical metric court coordinates for identity matching, trajectory export, speed filtering, and interpolation thresholds, while documenting imperial pickleball dimensions as reference values.
- Preserve the existing detection, tracking, footpoint, and homography projection flow, but feed projected observations into identity assignment before final player trajectory export.
- Support short lost intervals with player state management, trajectory interpolation, and explicit `is_interpolated` / `tracking_status` markers.
- Add diagnostics for `track_id` to `player_id` assignment decisions, including source track history and reconnect events.
- Export final player-level JSON and CSV artifacts suitable for metrics, debug visualization, and manual QA.

## Capabilities

### New Capabilities
- `player-trajectory-identity`: Stable match-level player identities, player-state management, metric-unit trajectory repair, and final four-player trajectory artifacts.

### Modified Capabilities
- `player-tracking-engine`: Tracking output must distinguish detector observations, temporary tracker IDs, and stable player IDs, and must expose enough projected observations for identity assignment without breaking existing overlay consumers.

## Impact

- Backend vision pipeline: `backend/app/services/analysis_pipeline.py` and `backend/app/vision/player_tracking_engine/*`.
- Schemas and artifacts: `backend/app/schemas/tracking.py`, analysis artifacts, JSON/CSV export paths, and browser-facing overlay data.
- Configuration: tracker choice and buffer settings, player identity thresholds, metric court bounds, speed sanity limits, and interpolation window.
- Tests: tracker compatibility tests, player identity assignment tests, interpolation/smoothing tests, artifact serialization tests, and pipeline integration tests.
- Optional dependency path: BoT-SORT / ByteTrack can be introduced through Ultralytics tracking while preserving the current test-friendly tracker contract.
