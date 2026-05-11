## Why

The current real-video flow uploads and analyzes a match, but the visual workspace still cannot show the uploaded video with visible player detections or human skeleton keypoints. To make the showcase credible, completed real jobs need to render observable YOLO person boxes and RTMPose skeleton overlays directly on the source video instead of only showing derived movement metrics.

## What Changes

- Enable configured YOLO person detection for real uploaded-video jobs and persist frame-indexed detection/tracking data that can be rendered over video.
- Introduce an RTMPose-based pose estimation capability that runs on tracked player boxes and stores per-frame human keypoints.
- Extend the pipeline result/artifact contract to expose detection, tracking, and pose overlay JSON, plus the uploaded video stream/reference needed by the frontend.
- Replace the job-specific visual workspace's simulated video card with a real video player overlay that draws player boxes, track labels, and skeleton joints when those artifacts are available.
- Preserve demo/sample routes as simulated visuals, and show clear degraded states when model inference, RTMPose assets, or overlay artifacts are unavailable.

## Capabilities

### New Capabilities

- `pose-estimation-engine`: RTMPose model configuration, keypoint normalization, per-frame pose result serialization, and failure/degraded behavior for skeleton overlays.

### Modified Capabilities

- `player-tracking-engine`: Require configured YOLO-backed real jobs to produce frame-indexed player detections/tracks suitable for video overlay rendering.
- `video-analysis-job-flow`: Require real analysis jobs to report detection/pose stages and expose video/overlay artifacts for completed jobs.
- `visual-analysis-workspace`: Require completed real jobs to show the uploaded video with synchronized person-box and skeleton overlays instead of only simulated visuals.

## Impact

- Backend pipeline, schemas, and artifacts under `backend/app/services`, `backend/app/schemas`, and `backend/app/vision`.
- Optional vision dependencies and model assets for YOLO and RTMPose configuration.
- Video serving or streaming API for uploaded source videos under `backend/app/api`.
- Frontend analysis client/types and the visual workspace components under `src/services`, `src/types`, `src/components/platform`, and `src/App.tsx`.
- Tests and local smoke verification for model-unavailable, no-detection, detection-only, and pose-overlay states.
