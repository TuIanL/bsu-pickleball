## 1. Unit Model and Schemas

- [x] 1.1 Add explicit court unit metadata and metric court dimension constants, including imperial reference dimensions and feet-to-meter conversion helpers
- [x] 1.2 Extend tracking schemas or add player-trajectory schemas for `player_id`, source `track_id`, bbox, image footpoint, metric court coordinates, confidence, `tracking_status`, and `is_interpolated`
- [x] 1.3 Add artifact metadata fields for `court_unit: "m"`, canonical 13.41 m by 6.10 m dimensions, and 44 ft by 20 ft reference dimensions
- [x] 1.4 Add serialization tests covering metric coordinates, imperial reference metadata, and source track history

## 2. Tracker and Projection Handoff

- [x] 2.1 Preserve the existing detection-in and tracks-out tracker contract while allowing configured BoT-SORT or ByteTrack integration for production runs
- [x] 2.2 Add or adapt tracker configuration for pickleball doubles, including a 90-frame initial lost buffer at 30 fps equivalent
- [x] 2.3 Ensure projected observations expose source `track_id`, bbox, image footpoint, court position, confidence, frame index, timestamp, and coordinate unit before identity assignment
- [x] 2.4 Convert upstream foot-based projection coordinates to meters before identity thresholds are applied when legacy projection output remains imperial

## 3. Player Identity Manager

- [x] 3.1 Implement `PlayerState` with stable `player_id`, active and historical source track IDs, last frame, last metric position, velocity, confidence, status, and trajectory history
- [x] 3.2 Implement `track_id` to `player_id` binding reuse for already-known tracks
- [x] 3.3 Implement candidate scoring for unbound tracks using metric position prediction and motion continuity
- [x] 3.4 Enforce the configured doubles participant cap so final player identities do not exceed four
- [x] 3.5 Add speed and court-bound sanity checks in metric units before accepting assignments
- [x] 3.6 Add identity diagnostics for assignment, reconnect, lost, inactive, and unmatched-track events

## 4. Trajectory Repair and Export

- [x] 4.1 Implement player lifecycle updates for `active`, `lost`, and `inactive` using configurable frame buffers
- [x] 4.2 Implement short-gap interpolation in metric coordinates and mark synthetic samples with `is_interpolated=true`
- [x] 4.3 Add optional smoothing for player trajectories without overwriting raw detected positions
- [x] 4.4 Export player-level JSON artifacts with video metadata, unit metadata, player states, source track history, trajectory samples, and diagnostics
- [x] 4.5 Export player-level CSV artifacts with frame, timestamp, player ID, source track ID, bbox, image footpoint, metric court coordinates, confidence, status, and interpolation marker

## 5. Pipeline Integration and Visualization

- [x] 5.1 Integrate identity assignment after projection and primary-player filtering in the real calibrated video analysis path
- [x] 5.2 Route movement metrics to stable `player_id` trajectories when player-level artifacts are available
- [x] 5.3 Preserve existing `track_id`-only overlay compatibility when identity assignment is unavailable
- [x] 5.4 Add debug overlay labels that can render stable player ID and source track ID together, such as `P1 / T12`
- [x] 5.5 Surface generated player trajectory artifact paths and statuses in analysis results

## 6. Validation

- [x] 6.1 Add unit tests for identity reuse, reconnect scoring, four-player cap behavior, lost/inactive status transitions, and unmatched-track diagnostics
- [x] 6.2 Add tests proving thresholds are applied in meters and imperial values are only reference metadata or converted inputs
- [x] 6.3 Add interpolation tests for short gaps and no-interpolation tests for gaps beyond the configured buffer
- [x] 6.4 Add pipeline integration tests showing fragmented source tracks are collapsed into stable player trajectories
- [x] 6.5 Add manual QA guidance or diagnostics summary for ID switch count, fragmentation count, reconnect success, average lost duration, and final player count
