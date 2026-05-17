## Context

The current backend pipeline processes uploaded, calibrated videos through person detection, simple multi-object player tracking, footpoint projection, movement metrics, optional RTMPose skeletons, and browser-loadable overlay artifacts. Real-job report adaptation intentionally avoids claiming shot, rally, or tactical conclusions because the MVP does not yet produce ball trajectories or hit events.

This change is the first perception-layer expansion toward pickleball-specific analysis. It introduces normalized multi-target detection and ball trajectory continuity while keeping the existing upload-video pipeline, player overlay behavior, and pose path intact. The target runtime remains offline or presentation-oriented uploaded-video analysis; realtime streaming and sub-100ms closed-loop decision support are deferred.

## Goals / Non-Goals

**Goals:**

- Add a normalized contract for `player`, `ball`, and `paddle` detections that can be serialized, tested, and consumed by future detector adapters.
- Preserve the existing person/player detection, tracking, projection, and pose overlay behavior.
- Add ball detection and ball trajectory artifacts with explicit observed, predicted, repaired, partial, and unavailable states.
- Add an MVP trajectory continuity stage that can reject implausible ball detections and repair short gaps with confidence metadata.
- Expose ball overlay artifact metadata through completed pipeline results and render true ball overlays in the visual analysis workspace when available.
- Keep all generated real-job copy source-aware so demo shot paths are not mistaken for uploaded-video ball analysis.

**Non-Goals:**

- Training a pickleball-specific YOLO model.
- Replacing the current player tracker with ByteTrack, BoT-SORT, DeepSORT, or another tracker.
- Implementing paddle-to-player association beyond normalized detection records.
- Detecting hits, bounces, shot type, rally boundaries, or tactical decisions.
- Implementing dynamic adaptive sampling, motion blur preprocessing, or realtime streaming latency guarantees.
- Running ball detection when no configured model or fixture-backed detector is available.

## Decisions

### Add multi-target schemas without forcing the existing person path to migrate at once

The backend will introduce shared multi-target detection records that can represent `player`, `ball`, and `paddle`. The existing person detection path may adapt its person boxes into `player` records where useful, but it does not need to rewrite the player tracking engine in the same step.

Alternatives considered:

- Replace all current tracking schemas immediately: cleaner long term, but risky because player overlays, RTMPose inputs, projection, and tests already depend on the person-specific contract.
- Keep ball data entirely separate: lower short-term risk, but it would make future ball-player-paddle event association harder.

### Treat ball tracking as a separate artifact from player tracking

Ball detections and trajectory points will be persisted as their own artifact and referenced from the raw pipeline result. This keeps ball status, confidence, and repaired-point semantics clear without overloading the existing `TrackingResult`, which is currently centered on player positions.

Alternatives considered:

- Store ball points in `TrackingResult.tracks`: this would blur player court-projection semantics and risk confusing existing movement metrics.
- Only render ball points client-side from raw detections: this would skip backend validation and make reports less reproducible.

### Start with trajectory continuity before hit or rally events

The first implementation should output observed ball points and short-gap repairs. Hit candidates and rally segmentation depend on a stable trajectory and should be proposed as a later change.

Alternatives considered:

- Add contact candidates immediately: attractive for demos, but false positives will be hard to explain without reliable ball continuity.
- Add tactical rules immediately: too dependent on unimplemented shot events and would risk fabricated coaching conclusions.

### Use source-labeled trajectory points

Each ball trajectory point will include a source such as `observed`, `predicted`, or `repaired` plus confidence and frame timing. The frontend must be able to render or label these differently.

Alternatives considered:

- Emit only a smoothed polyline: visually simple, but hides uncertainty and makes debugging impossible.
- Keep repaired points out of artifacts: safer but less useful for occlusion-heavy videos where short gaps are expected.

### Keep detector configuration optional and explicit

If no multi-class detector is configured, the pipeline should complete with a skipped or unavailable ball-tracking stage and should not mark ball overlays as available. Tests may inject fixture detectors to validate artifact flow without requiring model weights.

Alternatives considered:

- Make a detector dependency mandatory: would break lightweight development and current smoke tests.
- Reuse the current person detector for ball detection: not credible because the configured model and class filtering are person-only.

## Risks / Trade-offs

- [Risk] Ball detection will be unreliable without a pickleball-specific model. -> Mitigation: expose skipped, partial, and confidence-qualified states; tests may use fixtures, but user-facing UI must not claim unavailable detections are real.
- [Risk] Repaired trajectory points can look more certain than they are. -> Mitigation: preserve point source and confidence, and render repaired segments distinctly.
- [Risk] Multi-target schemas could drift from existing person overlay schemas. -> Mitigation: keep adapters at the pipeline boundary and add regression tests for existing player overlay artifacts.
- [Risk] Additional per-frame detection increases processing time. -> Mitigation: keep ball tracking independently configurable and preserve existing frame stride controls.
- [Risk] Frontend users may confuse demo shot paths with real ball trajectories. -> Mitigation: real-job ball overlays must only use backend artifacts and must show unavailable states when artifacts are absent.

## Migration Plan

- Add new schemas and artifact references while keeping all existing result fields optional and backward compatible.
- Implement fixture-backed and disabled-state tests first so lightweight runs continue without model assets.
- Add ball artifact generation behind configuration or injected detector support.
- Add frontend fetch/render paths that tolerate missing artifact URLs.
- Rollback can disable ball tracking configuration; existing player, pose, projection, and report paths should continue to operate.

## Open Questions

- Which pickleball-specific detector checkpoint and class map will be used for real ball and paddle detections?
- What maximum repair gap should be the first default for 60fps video: 3, 5, or 8 frames?
- Should ball coordinates be projected to court coordinates in this phase, or remain image-space until bounce/contact events are introduced?
