## 1. Backend Schema Contracts

- [x] 1.1 Add normalized multi-target detection schemas for `player`, `ball`, and `paddle` with frame timing, bbox, confidence, class name, source dimensions, and validation.
- [x] 1.2 Add ball detection and ball trajectory artifact schemas with status, detail, source frame metadata, frame stride, processed frame count, and per-point source labels.
- [x] 1.3 Extend pipeline artifact/result schemas with optional ball overlay JSON path, URL, status, and detail fields while preserving backward compatibility for older results.
- [x] 1.4 Add fixture JSON examples for available, partial, no-detections, and unavailable ball overlay states.
- [x] 1.5 Add schema serialization tests for multi-target detections and ball trajectory artifacts.

## 2. Multi-target Detector Boundary

- [x] 2.1 Define a backend detector interface or adapter module that can emit normalized multi-target detections without importing heavy model dependencies at module import time.
- [x] 2.2 Implement a disabled or empty multi-target detector that reports skipped/unavailable behavior for lightweight runs.
- [x] 2.3 Implement a fixture-backed multi-target detector for tests that can emit player, ball, and paddle detections by frame.
- [x] 2.4 Add class-map and confidence-threshold configuration for ball and paddle detection without changing the current person detector defaults.
- [x] 2.5 Add tests showing unsupported classes and low-confidence targets are excluded from normalized artifacts.

## 3. Player Compatibility

- [x] 3.1 Add an adapter that converts normalized `player` detections into the existing Player Tracking Engine detection input shape.
- [x] 3.2 Ensure the current person-only detector path still produces player tracks, projected positions, detection overlays, and pose inputs unchanged.
- [x] 3.3 Ensure `ball` and `paddle` detections are ignored by player projection and movement metrics.
- [x] 3.4 Add regression tests for existing person overlay artifact generation when no multi-target detector is configured.

## 4. Ball Detection Artifact Pipeline

- [x] 4.1 Add a ball detection stage to the analysis pipeline that can run after frame decode using the configured multi-target detector or injected test detector.
- [x] 4.2 Filter ball detections by confidence, bbox validity, source frame bounds, and configurable ball size limits.
- [x] 4.3 Persist a ball detection artifact for jobs with usable ball detections.
- [x] 4.4 Report no-detections and unavailable ball states without failing the overall analysis job.
- [x] 4.5 Add pipeline tests for available, skipped, and no-detections ball detection outcomes.

## 5. Ball Trajectory Continuity

- [x] 5.1 Implement a ball trajectory continuity module that orders ball detections by frame and selects plausible primary ball candidates.
- [x] 5.2 Add configurable short-gap repair with source `repaired` or `predicted` and reduced confidence.
- [x] 5.3 Add speed, direction, frame-bound, and gap-length guards that prevent implausible long repairs.
- [x] 5.4 Segment the trajectory when continuity cannot be safely repaired.
- [x] 5.5 Add tests for consecutive observed points, short repaired gaps, long unresolved gaps, and implausible candidate rejection.

## 6. Pipeline Result and API Exposure

- [x] 6.1 Persist ball trajectory artifacts to backend output storage alongside existing tracking and pose artifacts.
- [x] 6.2 Add a browser-loadable endpoint or artifact route for retrieving ball overlay JSON by analysis job.
- [x] 6.3 Include ball-tracking stage status and artifact metadata in completed raw pipeline results.
- [x] 6.4 Preserve player, pose, projection, and metric outputs when ball tracking fails or is skipped.
- [x] 6.5 Add API smoke tests for retrieving available and unavailable ball overlay artifact states.

## 7. Frontend Types and Data Loading

- [x] 7.1 Add TypeScript types for ball overlay artifacts, trajectory points, source labels, and ball overlay status fields.
- [x] 7.2 Add an analysis client helper for fetching ball overlay artifacts from completed pipeline results.
- [x] 7.3 Update pipeline-to-report adaptation so real jobs can surface ball overlay availability without generating shot, rally, or tactical claims.
- [x] 7.4 Ensure older completed results without ball metadata still render with ball overlays marked unavailable.
- [x] 7.5 Add focused frontend tests or helper checks for artifact parsing and unavailable-state handling.

## 8. Visual Analysis Ball Overlay

- [x] 8.1 Add a real ball overlay layer to the video analysis workspace that draws source-aligned ball points and trajectory segments.
- [x] 8.2 Transform ball source-frame coordinates into rendered video coordinates using the same letterbox-aware logic as player overlays.
- [x] 8.3 Render observed and repaired/predicted trajectory points with distinguishable visual treatment.
- [x] 8.4 Add a ball overlay toggle that is independent from player boxes and skeleton overlays.
- [x] 8.5 Show skipped, unavailable, no-detections, and partial ball states without rendering demo shot paths as real uploaded-video ball data.

## 9. Documentation and Verification

- [x] 9.1 Document multi-target detector configuration, optional model assets, and lightweight disabled behavior.
- [x] 9.2 Document ball tracking artifact fields and the meaning of observed, repaired, predicted, partial, and unavailable states.
- [x] 9.3 Run backend tests covering schemas, detector adapter behavior, pipeline artifact persistence, and trajectory continuity.
- [x] 9.4 Run frontend type checks/tests covering ball overlay artifact loading and workspace rendering helpers.
- [x] 9.5 Manually verify a real or fixture-backed completed job in the visual analysis workspace, confirming player overlays still work and ball overlays only appear from backend artifact data.
