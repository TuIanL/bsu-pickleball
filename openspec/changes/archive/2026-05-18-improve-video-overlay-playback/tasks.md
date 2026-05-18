## 1. Backend Overlay Subject Filtering

- [x] 1.1 Add a pipeline helper that derives per-frame court-relevant active track IDs from projected `PlayerFramePosition` output.
- [x] 1.2 Build detection overlay frames from court-relevant active tracks instead of all active tracker outputs.
- [x] 1.3 Pass only court-relevant frame detections into RTMPose estimation.
- [x] 1.4 Keep raw detection/tracking diagnostic data available while ensuring browser-facing overlay artifacts exclude out-of-bounds spectators.
- [x] 1.5 Update artifact detail strings to explain court-relevant filtering when overlay counts are reported.

## 2. Backend Sampling Configuration

- [x] 2.1 Change the default overlay frame stride to a 60fps-friendly value while preserving `PICKLEBALL_OVERLAY_FRAME_STRIDE` override behavior.
- [x] 2.2 Document recommended stride values for presentation quality and lower-resource processing.
- [x] 2.3 Add or update backend tests covering default stride configuration and explicit stride override behavior.

## 3. Frontend Fullscreen Playback

- [x] 3.1 Replace native-video fullscreen reliance with a custom fullscreen control that targets the real-video overlay container.
- [x] 3.2 Track fullscreen state with `fullscreenchange` and keep video, SVG overlays, layer toggles, and status labels inside the fullscreen surface.
- [x] 3.3 Preserve inline playback behavior when fullscreen is unavailable or exits.

## 4. Frontend Overlay Synchronization

- [x] 4.1 Replace overlay time updates that rely only on `onTimeUpdate` with `requestVideoFrameCallback` where available and `requestAnimationFrame` fallback while playing.
- [x] 4.2 Implement timestamp or frame-index based lookup for previous, current, and next overlay frames.
- [x] 4.3 Interpolate person boxes between matching track IDs when adjacent overlay frames are available.
- [x] 4.4 Interpolate skeleton keypoints between matching track IDs and keypoint names when adjacent pose frames are available.
- [x] 4.5 Fall back to nearest-frame rendering when interpolation inputs are missing or unsafe.

## 5. Verification

- [x] 5.1 Add backend regression tests showing out-of-bounds spectators are excluded from tracking overlay artifacts and pose inputs.
- [x] 5.2 Add frontend tests or focused component checks for fullscreen container behavior and overlay frame smoothing helpers.
- [x] 5.3 Run the relevant backend and frontend test suites.
- [x] 5.4 Manually verify a 60fps real-video job in normal and fullscreen playback, confirming overlays remain visible, spectators are hidden, and motion is visibly smoother.
