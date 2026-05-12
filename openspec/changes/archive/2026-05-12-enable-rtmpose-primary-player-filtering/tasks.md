## 1. RTMPose Activation and Diagnostics

- [x] 1.1 Review current RTMPose environment settings, model path resolution, and default pose inference behavior.
- [x] 1.2 Update configuration or startup documentation so configured RTMPose assets can be enabled for real calibrated jobs without ambiguity.
- [x] 1.3 Preserve explicit disabled, missing dependency, missing asset, unsupported schema, and runtime failure details in pose stage and artifact metadata.
- [x] 1.4 Add tests proving tracking overlays remain available when RTMPose is disabled or unavailable, and pose overlays become available when a working pose estimator is configured.

## 2. Primary-Player Selection

- [x] 2.1 Add a primary-player selector that scores active tracks using current confidence, rolling confidence, recent persistence, frame rank, and bbox sanity checks.
- [x] 2.2 Add configurable thresholds for primary-player minimum confidence, selected participant count, and optional broad scene-distance sanity filtering.
- [x] 2.3 Keep raw detections/tracks for diagnostics while producing renderable overlay frames only from selected primary-player tracks.
- [x] 2.4 Ensure players stepping outside standard court lines remain eligible when they satisfy primary-player confidence and track-quality rules.
- [x] 2.5 Add regression tests for high-confidence players, low-confidence incidental detections, too-many-person frames, and line-out player retention.

## 3. Pipeline Integration

- [x] 3.1 Replace court-relevant track ID filtering for overlay and pose inputs with the primary-player selector output.
- [x] 3.2 Keep court projection and stricter in-court filtering available for movement metrics and heatmap computations.
- [x] 3.3 Pass the same selected primary-player frame detections to RTMPose estimation and tracking overlay artifacts.
- [x] 3.4 Update artifact detail strings to report raw detection counts, selected primary-player overlay counts, dropped detections, and RTMPose status.

## 4. Frontend Status Clarity

- [x] 4.1 Update real-video overlay copy so RTMPose-disabled, RTMPose-unavailable, no-primary-player, and no-detection states are distinguishable.
- [x] 4.2 Ensure the video workspace continues to show person boxes when skeletons are unavailable.
- [x] 4.3 Ensure the skeleton layer toggle remains available only as a display control and does not mask backend RTMPose availability details.

## 5. Verification

- [x] 5.1 Run backend tests covering tracking, pose, config, and API smoke behavior.
- [x] 5.2 Run frontend typecheck or test suite for report/workspace rendering changes.
- [x] 5.3 Manually verify a real calibrated video job with RTMPose enabled, confirming primary players keep boxes and skeletons when stepping outside court lines.
- [x] 5.4 Manually verify a scene with extra people or low-confidence detections, confirming overlays prioritize the main match participants.
