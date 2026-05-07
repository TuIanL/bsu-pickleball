## 1. Backend Setup And Configuration

- [x] 1.1 Add backend configuration and logging modules for app name, CORS, upload paths, output paths, calibration paths, and optional model settings.
- [x] 1.2 Update backend dependency metadata and requirements documentation for FastAPI, Pydantic, OpenCV, NumPy, Pandas, pytest, and optional Ultralytics/tracker extras.
- [x] 1.3 Create or document local data directories for uploads, outputs, calibrations, and temporary processing artifacts without committing generated media.
- [x] 1.4 Keep `GET /health` available and verify the FastAPI app imports without optional vision-model dependencies.

## 2. Schemas And API Routes

- [x] 2.1 Add Pydantic schemas for uploaded videos, video metadata, calibration keypoints, homography matrices, tracking detections, projected track points, metric summaries, heatmaps, and pipeline results.
- [x] 2.2 Add `StorageService` and `VideoService` for saving uploads, returning stable video identifiers, and retrieving stored video metadata.
- [x] 2.3 Add video upload routes for multipart upload and video metadata retrieval.
- [x] 2.4 Add calibration routes for submitting manual court keypoints and retrieving stored calibrations.
- [x] 2.5 Refactor or wrap existing analysis routes so metadata-only mock jobs still work and uploaded-video-backed jobs can call `AnalysisPipeline`.
- [x] 2.6 Add raw algorithm result retrieval for completed or in-progress analysis jobs.

## 3. CourtVision Calibration Engine

- [x] 3.1 Implement standard pickleball court geometry with 20 ft width, 44 ft length, net line, kitchen lines, non-volley zones, and service zones.
- [x] 3.2 Implement zone membership helpers for court bounds, kitchen zones, and service zones.
- [x] 3.3 Implement homography computation and projection helpers using manual image-to-court keypoint correspondences.
- [x] 3.4 Add validation for insufficient or degenerate calibration correspondences.
- [x] 3.5 Add court overlay interface or lightweight drawing helper for future visualized video output.

## 4. Player Tracking Engine

- [x] 4.1 Define person detector interface with normalized person detection output and an optional Ultralytics-backed adapter placeholder.
- [x] 4.2 Define multi-object tracker interface with a lightweight MVP implementation that can return deterministic mock or empty tracks.
- [x] 4.3 Implement footpoint estimation from person bounding boxes using bottom-center coordinates.
- [x] 4.4 Implement player projection from image footpoints to court coordinates through a stored homography.
- [x] 4.5 Ensure tracking modules import and run in tests without YOLO weights, CUDA, or tracker assets.

## 5. Pickleball Performance Engine And Pipeline

- [x] 5.1 Implement trajectory distance metrics from projected court-coordinate samples.
- [x] 5.2 Implement speed metrics from timestamped projected track points.
- [x] 5.3 Implement kitchen dwell metrics using standard court zones.
- [x] 5.4 Implement doubles spacing metrics for overlapping same-side player samples.
- [x] 5.5 Implement heatmap bin generation from projected player coordinates.
- [x] 5.6 Implement `AnalysisPipeline` to read video metadata, apply optional calibration, run MVP tracking/projection, compute metrics, and return structured JSON plus output artifact references.
- [x] 5.7 Preserve existing frontend report responses by mapping pipeline-backed jobs to the current report contract or falling back to the existing mock report.

## 6. Tests And Documentation

- [x] 6.1 Add pytest coverage for court geometry constants, generated zones, and zone membership.
- [x] 6.2 Add pytest coverage for homography computation, invalid calibration validation, and pixel-to-court projection.
- [x] 6.3 Add pytest coverage for footpoint estimation and projected track schemas.
- [x] 6.4 Add pytest coverage for trajectory distance, speed, kitchen dwell, doubles spacing, and heatmap metrics.
- [x] 6.5 Add lightweight API smoke tests or documented curl examples for health, video upload, calibration, and analysis job creation.
- [x] 6.6 Update backend README with installation, running the FastAPI service, upload/calibration/analysis endpoints, storage layout, optional model dependency notes, and pytest commands.
