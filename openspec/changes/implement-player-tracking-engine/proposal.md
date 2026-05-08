## Why

The backend currently reserves Player Tracking Engine interfaces, but the analysis pipeline still emits deterministic mock tracks instead of extracting player positions from uploaded fixed-camera video. Downstream movement metrics need real per-frame court-coordinate footpoints so they can represent where players contact the ground, not the center of a detection box.

## What Changes

- Implement a model-backed `PersonDetector` using Ultralytics YOLO with normalized person-only detection output, configurable confidence threshold, and automatic CPU/GPU selection when available.
- Replace the detection-order tracker placeholder with a replaceable `MultiObjectTracker` MVP based on IOU association, stable integer `track_id` assignment, and lost-track retention suitable for later ByteTrack or BoT-SORT adapters.
- Promote footpoint estimation into a `FootpointEstimator` class that uses bbox bottom-center for MVP and exposes strategy naming for future pose or segmentation-derived methods.
- Expand player projection so tracked footpoints are transformed through the CourtVision Calibration Engine homography into standard pickleball court coordinates and filtered by a configurable tolerance around the 20 ft by 44 ft court.
- Add JSON-serializable tracking schemas for detections, tracks, per-frame player positions, and complete tracking results.
- Integrate real video frame reading, configurable `frame_stride`, timestamp/FPS metadata, progress logging, and `tracking_result.json` artifact generation into `AnalysisPipeline`.
- Add focused tests for bottom-center footpoints, homography projection, out-of-bounds filtering, and JSON serialization.

## Capabilities

### New Capabilities

- `player-tracking-engine`: Detects people in fixed-camera pickleball video, maintains player identities across frames, estimates image-space footpoints, projects those footpoints into standard court coordinates, and emits structured tracking results for metrics.

### Modified Capabilities

- `pickleball-algorithm-backend-mvp`: Strengthen the existing Player Tracking Engine requirement from interface placeholders into a working MVP detector/tracker/footpoint/projector pipeline with normalized schemas and tests.
- `video-analysis-job-flow`: Extend pipeline-backed analysis results to include real tracking artifacts, frame timing metadata, and persisted `tracking_result.json` output when video and calibration are available.

## Impact

- Affected backend modules:
  - `backend/app/vision/player_tracking_engine/person_detector.py`
  - `backend/app/vision/player_tracking_engine/multi_object_tracker.py`
  - `backend/app/vision/player_tracking_engine/footpoint_estimator.py`
  - `backend/app/vision/player_tracking_engine/player_projector.py`
  - `backend/app/schemas/tracking.py`
  - `backend/app/services/analysis_pipeline.py`
  - `backend/app/schemas/pipeline.py`
  - `backend/app/services/storage_service.py`
- Affected tests:
  - `backend/tests/test_footpoint_projection.py`
  - optional pipeline tests if implementation scope permits deterministic dependency injection.
- Dependencies:
  - Uses existing `opencv-python` for frame decoding.
  - Uses optional `ultralytics` for YOLO-backed detection without making lightweight imports require model weights.
  - No CUDA requirement; CPU fallback must remain supported.
- API impact:
  - Existing analysis result schema remains compatible for consumers of `tracks` and `metrics`.
  - New tracking artifact paths and metadata may be added to pipeline artifacts/results.
