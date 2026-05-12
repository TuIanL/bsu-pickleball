## Why

The current real-video overlay experience is not reliable enough for full-screen presentation: native video fullscreen drops the person boxes and skeleton layer, detected spectators outside the court are still rendered as match participants, and 60fps footage appears jerky because overlay samples are too sparse and playback synchronization is tied to low-frequency time updates.

This change improves the demo-critical review experience so uploaded match videos can show smooth, court-relevant YOLO boxes and RTMPose skeletons in normal and fullscreen playback.

## What Changes

- Keep video, person boxes, skeletons, layer toggles, and status labels together when the user enters fullscreen playback.
- Filter real overlay subjects to match-relevant players by using court-calibrated footpoint projection before exposing detection boxes or running pose estimation for visible skeletons.
- Tune overlay sampling for 60fps source videos so the default output is presentation-smooth while still allowing heavier full-frame processing when explicitly configured.
- Refresh overlay rendering with frame-aligned playback timing instead of relying only on native `timeupdate` events.
- Add interpolation or equivalent smoothing between processed overlay frames so boxes and skeletons do not visibly jump when sparse inference is used.
- Preserve degraded states when calibration, detections, or pose artifacts are missing.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `visual-analysis-workspace`: fullscreen playback and real-video overlay synchronization behavior changes for person boxes and skeletons.
- `player-tracking-engine`: detection overlay artifacts must exclude spectators and other non-match persons by applying court-relevance filtering before exposing renderable boxes.
- `pose-estimation-engine`: pose estimation and pose overlay artifacts must use the same court-relevant subject set as detection overlays.

## Impact

- Frontend: `src/components/platform/VideoAnalysisCard.tsx` real-video player, fullscreen controls, overlay timing loop, and overlay frame selection/smoothing.
- Backend: `backend/app/services/analysis_pipeline.py` tracking-to-overlay flow, pose input selection, artifact details, and default overlay stride.
- Backend configuration: `PICKLEBALL_OVERLAY_FRAME_STRIDE` default and documentation for 60fps presentation settings.
- Tests: frontend overlay synchronization/fullscreen behavior where practical, backend filtering of overlay boxes and pose subjects, and regression tests for no-calibration or no-detection degraded states.
