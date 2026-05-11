## Context

The real-video analysis flow now uploads source videos, collects manual court calibration, runs the MVP pipeline, and adapts movement output into the existing report contract. The visual workspace still behaves like a polished demo because the primary video card is a simulated SVG scene and the pipeline's visualization stage is explicitly skipped.

The backend already has a lazy Ultralytics YOLO `PersonDetector`, a simple multi-object tracker, footpoint projection, and tracking artifact storage. Model inference is disabled by default, detection records are not frame-indexed for overlay playback, and the RTMPose adapter is currently a placeholder. The frontend can load job reports and raw pipeline results, but it cannot stream the uploaded video or draw synchronized detection/pose overlays.

## Goals / Non-Goals

**Goals:**

- Enable configured YOLO person detection for real uploaded-video jobs.
- Persist frame-indexed detection and track overlay data with timestamps, bounding boxes, confidence, and track labels.
- Add an RTMPose pose-estimation path that consumes tracked person boxes and emits normalized skeleton keypoints.
- Expose source video and overlay artifacts through backend APIs that the frontend can consume.
- Replace the job-specific workspace video card with a real video player plus synchronized overlays for boxes and skeletons.
- Preserve degraded states for missing model assets, no detections, no pose results, and demo/sample routes.

**Non-Goals:**

- Ball detection, ball trajectory tracking, paddle detection, hit detection, rally segmentation, or tactical shot classification.
- Pose-based action diagnosis or technical scoring beyond rendering skeleton evidence.
- Automatic court calibration.
- Production-grade GPU scheduling, distributed queues, authentication, or cloud object storage.
- Guaranteed real-time inference; local MVP processing may be sparse-frame and CPU-bound.

## Decisions

### Use sparse overlay artifacts instead of exported annotated video first

The backend will persist JSON overlay artifacts containing frame indices, timestamps, image dimensions, person boxes, track IDs, and pose keypoints. The frontend will play the source video and render an SVG or canvas overlay for the nearest processed frame.

Alternative considered: generate an annotated MP4 in the backend. That is attractive for a simple playback surface, but it adds video encoding complexity, increases processing time, and makes interactive toggles for boxes/skeletons harder. JSON overlays keep the first version inspectable and extensible.

### Keep YOLO person detection as the tracking source of truth

The existing `PersonDetector` remains the detector for player boxes. Pipeline configuration will make model-backed inference explicit, while the current empty detector remains available for tests and model-unavailable degraded states.

Alternative considered: replace YOLO detection and tracking with RTMPose-only person localization. RTMPose normally expects person boxes or a detector, so YOLO-first keeps the architecture closer to established top-down pose pipelines.

### Add a normalized pose schema independent of RTMPose internals

Pose results will be serialized as stable keypoint names, pixel coordinates, confidence, frame index, timestamp, subject/track ID, and skeleton edge metadata or a known skeleton profile. The pipeline result should not expose raw framework tensors, config internals, or model-specific object shapes.

Alternative considered: store whatever RTMPose returns directly. That is faster to wire once, but it leaks model implementation details into the frontend and makes future pose model replacement brittle.

### Treat RTMPose as optional but explicit

The pipeline should distinguish detection-only completion from detection-plus-pose completion. Missing RTMPose dependencies, config files, or checkpoints should mark the pose stage as skipped or failed with a clear reason without pretending skeleton overlays exist.

Alternative considered: fail the entire analysis when pose cannot run. That would be strict, but a visible YOLO box overlay is still useful for the current showcase and gives users evidence that real video inference is active.

### Serve source video separately from report payloads

Uploaded videos will be retrieved through a dedicated stream/static route keyed by `videoId`, while reports and pipeline results continue to return structured JSON. The frontend can combine `videoUrl` and `overlayArtifactUrl` for the job workspace.

Alternative considered: embed file paths in the report and let the browser load them directly. That does not work across browser/backend boundaries and leaks local filesystem paths.

## Risks / Trade-offs

- RTMPose framework dependencies can be heavy or fragile on local machines -> isolate the adapter, make model configuration explicit, and keep detection-only degraded mode available.
- CPU inference may be slow for long videos -> default to configurable frame stride and surface processed-frame counts in job stages.
- Sparse-frame overlays can appear slightly jumpy -> render nearest-frame overlays first and leave interpolation as a later enhancement.
- YOLO may detect spectators or background people -> keep court projection filtering where calibration exists and label detections outside court bounds as excluded from movement metrics.
- Different RTMPose checkpoints may use different keypoint sets -> store a `keypoint_schema` and reject unsupported schemas with a clear error.
- Browser overlay alignment can drift with object-fit letterboxing -> compute rendered video bounds and transform pixel coordinates into overlay coordinates using source dimensions.

## Migration Plan

1. Keep demo `/vision` behavior using the existing simulated card.
2. Add backend schema and artifact support for frame overlay data without removing current pipeline result fields.
3. Add model configuration and detection-only artifacts behind explicit backend settings.
4. Add RTMPose adapter and pose artifacts, with clear skipped/failed stage states when assets are missing.
5. Add video streaming and artifact retrieval APIs for uploaded videos and generated overlay JSON.
6. Update the job-specific visual workspace to prefer real video overlays when artifacts exist and fall back to limited/no-overlay states when they do not.
7. Verify with a short local video before broadening to long videos.

Rollback is straightforward: leave uploaded-video jobs and movement reports intact, disable model inference, and have the job workspace display the existing no-overlay/limited state while demo routes continue to render simulated visuals.

## Open Questions

- Which RTMPose package/runtime should be the first supported local adapter: full MMPose, ONNXRuntime export, or another packaged inference path?
- Which keypoint schema should the first implementation normalize to: RTMPose26 or a smaller COCO-style skeleton if model assets are easier to obtain?
- Should the first overlay artifact contain every processed frame or a capped sample for UI responsiveness?
- Should frontend overlay rendering use SVG for ease of inspection or canvas for performance on long videos?
