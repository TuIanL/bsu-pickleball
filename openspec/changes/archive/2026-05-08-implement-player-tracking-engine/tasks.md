## 1. Tracking Schemas

- [x] 1.1 Replace or extend `backend/app/schemas/tracking.py` with JSON-serializable `Detection`, `Track`, `FootpointEstimate`, `PlayerFramePosition`, and `TrackingResult` models while preserving compatibility aliases needed by existing metrics tests.
- [x] 1.2 Add validation/defaults for bbox coordinate lists, confidence ranges, integer track IDs, frame index, timestamp, FPS, frame stride, valid/invalid position state, and method names.
- [x] 1.3 Update any schema imports in pipeline and metrics modules so existing projected-track consumers keep working.

## 2. Person Detection

- [x] 2.1 Implement `PersonDetector` as a concrete class using lazy Ultralytics YOLO loading with default model `yolov8n.pt` and configurable `model_path`, `conf_threshold`, and `device`.
- [x] 2.2 Filter YOLO output to person class only and normalize detections to `{"bbox": [x1, y1, x2, y2], "confidence": float, "class_name": "person"}`.
- [x] 2.3 Add defensive CPU/GPU auto-selection and a clear runtime error when optional YOLO dependencies are unavailable during model-backed execution.
- [x] 2.4 Preserve a lightweight empty or injected detector path for tests and mock/fallback runs.

## 3. Multi-Object Tracker

- [x] 3.1 Implement `MultiObjectTracker` as a concrete IOU tracker with configurable IOU threshold, `max_lost`, and monotonically increasing integer track IDs.
- [x] 3.2 Associate current detections to active tracks by highest IOU, update matched tracks, create IDs for unmatched detections, and retain unmatched tracks internally until the lost limit is exceeded.
- [x] 3.3 Return active `Track` records with `track_id`, `bbox`, `confidence`, and `lost=false` for the current frame.
- [x] 3.4 Keep the tracker interface narrow enough for future ByteTrack or BoT-SORT adapters to replace the IOU implementation.

## 4. Footpoint and Projection

- [x] 4.1 Implement `FootpointEstimator` class with default `bbox_bottom_center` strategy and compatibility wrapper for existing `estimate_footpoint` imports.
- [x] 4.2 Implement `PlayerProjector` class that accepts tracks, footpoint estimates, frame index, timestamp, and homography, then calls CourtVision `image_to_court`.
- [x] 4.3 Apply configurable tolerant court bounds, defaulting to x `[-2, 22]` and y `[-2, 46]`, and consistently exclude or mark invalid out-of-range positions.
- [x] 4.4 Preserve `project_track_points` compatibility where existing tests or metrics still use image track point inputs.

## 5. AnalysisPipeline Integration

- [x] 5.1 Add dependency-injected detector, tracker, footpoint estimator, projector, and frame-stride configuration to `AnalysisPipeline`.
- [x] 5.2 Open uploaded videos with OpenCV, read FPS/frame-count metadata, iterate decoded frames, skip according to `frame_stride`, and compute timestamps from FPS.
- [x] 5.3 Run detection, tracking, footpoint estimation, projection, and accumulation of `TrackingResult` positions for jobs with readable video and valid calibration.
- [x] 5.4 Persist a dedicated `tracking_result.json` artifact and expose its path through pipeline artifacts or result metadata.
- [x] 5.5 Convert valid projected player positions into the existing projected track format used by distance, speed, kitchen dwell, doubles spacing, and heatmap metrics.
- [x] 5.6 Keep the current deterministic mock or empty-result behavior when no video or no calibration is supplied, and produce clear failed pipeline results when a requested real tracking run cannot read video or load required detector dependencies.
- [x] 5.7 Add progress logging during video processing using processed-frame counts and total frame count when available.

## 6. Tests and Verification

- [x] 6.1 Update `backend/tests/test_footpoint_projection.py` to cover `FootpointEstimator` bottom-center output and method metadata.
- [x] 6.2 Add projector tests proving image footpoints project to expected court coordinates through a known homography.
- [x] 6.3 Add projector tests for out-of-bounds court coordinates being filtered or marked invalid.
- [x] 6.4 Add JSON serialization tests for `Detection`, `Track`, `PlayerFramePosition`, and `TrackingResult`.
- [x] 6.5 Add focused IOU tracker unit tests for stable ID reuse, new ID creation, and lost-track retention where practical.
- [x] 6.6 Run the backend pytest suite from `backend/` and resolve regressions.
