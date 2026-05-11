## 1. Backend Schemas And Configuration

- [x] 1.1 Add backend settings for YOLO inference enablement, detector model path, detector confidence, pose inference enablement, RTMPose config/checkpoint paths, pose confidence, and overlay frame stride.
- [x] 1.2 Extend tracking schemas so renderable detections include `frame_index`, `timestamp_seconds`, optional `track_id`, `bbox`, `confidence`, and source frame dimensions.
- [x] 1.3 Add pose schemas for keypoints, skeleton edges, per-subject frame poses, pose artifacts, and pose availability metadata.
- [x] 1.4 Extend pipeline artifact/result schemas to reference source video URLs or IDs, detection/tracking overlay artifacts, and pose overlay artifacts.

## 2. YOLO Detection And Tracking Artifacts

- [x] 2.1 Wire real uploaded-video jobs to use `PersonDetector` when model inference is enabled, while keeping the empty detector for disabled/test paths.
- [x] 2.2 Capture frame dimensions, frame indices, timestamps, YOLO detections, tracker IDs, and confidence values during video tracking.
- [x] 2.3 Persist a browser-consumable tracking overlay JSON artifact for completed jobs that run detection/tracking.
- [x] 2.4 Report detection/tracking stage details for enabled, disabled, no-detection, and model-error states.

## 3. RTMPose Pose Estimation

- [x] 3.1 Implement or wrap an RTMPose adapter that lazily loads the configured runtime and model assets only when pose inference is enabled.
- [x] 3.2 Feed tracked player boxes from processed frames into the pose estimator and associate returned keypoints with frame timestamps and track IDs.
- [x] 3.3 Normalize RTMPose output into the backend pose schema with stable keypoint names, confidence values, and skeleton edge metadata.
- [x] 3.4 Persist pose overlay JSON artifacts and expose skipped/failed/no-pose states without fabricating skeleton data.

## 4. Backend Video And Artifact APIs

- [x] 4.1 Add a browser-loadable source video endpoint or static route for uploaded videos by `videoId`.
- [x] 4.2 Add artifact retrieval endpoints or URLs for tracking overlay JSON and pose overlay JSON without exposing local filesystem paths.
- [x] 4.3 Ensure `/api/analysis/jobs/{job_id}/result` includes video and overlay artifact metadata for completed real jobs.
- [x] 4.4 Add backend tests for video serving, artifact references, detection-only results, pose-unavailable results, and pose artifact serialization.

## 5. Frontend Types And API Client

- [x] 5.1 Add frontend types for detection overlay frames, pose keypoints, skeleton edges, pose artifacts, and overlay availability metadata.
- [x] 5.2 Extend the analysis client to build source video URLs and fetch tracking/pose overlay artifacts for a completed job.
- [x] 5.3 Update the pipeline/report adapter so job workspaces can distinguish real video overlays, detection-only overlays, and no-overlay states.

## 6. Real Video Overlay Workspace

- [x] 6.1 Replace the job-specific simulated video surface with a real `<video>` player when a completed job has a source video URL.
- [x] 6.2 Render synchronized YOLO person boxes over the video using source-frame-to-rendered-video coordinate transforms.
- [x] 6.3 Render synchronized RTMPose skeleton keypoints and joint connections over the video when pose data is available.
- [x] 6.4 Add lightweight overlay controls for showing/hiding boxes and skeletons while preserving demo route behavior.
- [x] 6.5 Show clear limited states for model inference disabled, no detections, pose assets missing, pose unavailable, and overlay fetch failures.

## 7. Verification

- [x] 7.1 Run backend unit/API tests for schema, artifact, and retrieval behavior.
- [x] 7.2 Run frontend type/build checks for the updated overlay types and workspace components.
- [x] 7.3 Manually verify a short uploaded video can complete analysis, open the job workspace, play the source video, and display person boxes.
- [x] 7.4 Manually verify RTMPose-enabled runs display skeleton joints when model assets are configured.
- [x] 7.5 Manually verify demo `/vision` still renders the simulated workspace and model-unavailable real jobs show degraded states.
