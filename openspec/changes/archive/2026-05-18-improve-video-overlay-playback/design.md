## Context

The real-job video workspace currently renders an uploaded video element with an SVG overlay as sibling DOM. Browser-native fullscreen is entered from the video element, so the SVG person boxes, RTMPose skeletons, layer toggles, and status labels stay outside fullscreen.

The backend already projects tracked footpoints through court calibration and excludes invalid projected positions from movement metrics, but the overlay artifact is built from unfiltered tracked detections. Pose estimation also receives those unfiltered frame detections, which means spectators or people outside the playable court can still be rendered as boxes and skeleton subjects.

For 60fps source footage, the default `overlay_frame_stride` of 30 produces only 2 overlay samples per second. Combined with React updates driven by native `timeupdate`, the overlay visibly jumps even when the source video itself is smooth.

## Goals / Non-Goals

**Goals:**

- Make fullscreen playback include the uploaded video, boxes, skeletons, overlay controls, and status labels as one visual surface.
- Ensure renderable detection boxes and pose subjects represent court-relevant match participants, not spectators outside the calibrated court area.
- Improve 60fps presentation smoothness by using denser default overlay sampling and frame-aligned frontend synchronization.
- Smooth visual transitions between processed overlay frames without changing the underlying analysis artifact contract more than necessary.
- Keep existing fallback states for missing calibration, missing detections, disabled model inference, and unavailable RTMPose assets.

**Non-Goals:**

- Replace the current tracker with ByteTrack, BoT-SORT, or another tracking algorithm.
- Solve all identity-switching issues across long rallies.
- Generate burned-in overlay video files.
- Run RTMPose on every 60fps frame by default.
- Add manual player selection or spectator masking UI in this change.

## Decisions

### Use container fullscreen instead of native video fullscreen

The player will expose a custom fullscreen button that calls `requestFullscreen()` on the real-video overlay container. The browser `controls` fullscreen affordance should no longer be the primary fullscreen path because it can fullscreen only the `<video>` element and drop sibling overlay DOM.

Alternatives considered:

- Keep native controls only: simplest, but it cannot keep the SVG overlay in fullscreen.
- Draw overlays onto a canvas inside the video: can work, but would require more rendering changes and still needs container-level controls.

### Filter overlay subjects after tracking and projection

The pipeline should first run detection and tracking, project each active track's footpoint through the existing homography, then derive the set of court-relevant track IDs for that frame. The tracking overlay frame and pose-estimation input should be built from that filtered set.

This keeps the existing detector broad enough to find all people while making the presentation layer court-aware. The projector's tolerated court bounds should remain configurable so valid players stepping just outside a line are not removed too aggressively.

Alternatives considered:

- Crop the image to the court before YOLO: faster in some scenes, but calibration perspective and player bodies outside the court polygon make it easy to clip valid athletes.
- Filter only in the frontend: hides boxes but still wastes pose work on spectators and leaves persisted artifacts misleading.

### Default to a denser 60fps-friendly overlay stride

The default overlay stride should move from 30 toward a presentation setting such as 2 or 3 for real jobs. At 60fps this yields 30fps or 20fps overlay samples instead of 2fps. The environment variable should continue to override this for slower machines.

Alternatives considered:

- Always process every frame: best visual fidelity, but expensive for YOLO and especially RTMPose.
- Leave default stride unchanged and rely only on interpolation: better than current behavior, but 2fps source overlay data is too sparse for believable body motion.

### Drive overlay rendering from video-frame timing

The frontend should use `requestVideoFrameCallback` when available, with `requestAnimationFrame` fallback, to update overlay time while playback is active. Scrubbing and pause states should still update immediately from video events.

The renderer should choose surrounding overlay frames by timestamp or frame index and interpolate boxes and matched keypoints with the same `track_id` when both adjacent frames exist. If interpolation cannot be done safely, it should fall back to the nearest processed frame.

Alternatives considered:

- Continue using `onTimeUpdate`: less code, but browser timeupdate cadence is not suitable for smooth overlay animation.
- Interpolate by array position only: fragile when frames are dropped or sparse; timestamps/frame indexes are safer.

## Risks / Trade-offs

- Filtering by projected footpoint can remove a valid player if calibration is inaccurate or the footpoint estimate is poor. Mitigation: use tolerant court bounds and retain clear no-overlay or limited-overlay states when calibration is missing.
- Denser default sampling increases backend processing time. Mitigation: keep `PICKLEBALL_OVERLAY_FRAME_STRIDE` configurable and document recommended values for demo versus low-resource runs.
- Interpolation can briefly show inaccurate limbs during fast motion or identity switches. Mitigation: interpolate only between matching `track_id` subjects and fall back to nearest-frame rendering when confidence or matching is unclear.
- Custom fullscreen controls may require cross-browser handling. Mitigation: use the standard Fullscreen API with `fullscreenchange` listeners and keep normal inline playback usable if fullscreen is unavailable.
