## 1. Dataset and Training Setup

- [x] 1.1 Add root-level dataset and training-run ignore rules for local court-line data and generated model artifacts.
- [x] 1.2 Document the expected `datasets/court-line-coco/` layout, external-path option, and model weight placement under `models/`.
- [x] 1.3 Add a dataset validation workflow for COCO segmentation JSON, image references, categories, segmentation types, and split readiness.
- [x] 1.4 Add a training configuration or script for court-line segmentation using the validated COCO dataset.
- [x] 1.5 Document training, validation, export, and recommended image-size settings for thin court-line masks.

## 2. Backend Schemas and Configuration

- [x] 2.1 Add automatic calibration request/response schemas for status, selected frame, mask diagnostics, keypoints, confidence, quality, preview artifacts, and stored calibration ID.
- [x] 2.2 Add backend settings for court-line model path, inference device, confidence threshold, geometry threshold, and representative-frame selection.
- [x] 2.3 Ensure missing or invalid model configuration produces a stable unavailable result rather than crashing the API.

## 3. Court-Line Inference and Geometry

- [x] 3.1 Add a court-line segmentation adapter that loads the configured model lazily and returns masks with confidence diagnostics.
- [x] 3.2 Add representative-frame extraction for uploaded videos with deterministic fallback behavior.
- [x] 3.3 Implement mask cleanup and line candidate extraction for predicted court-line masks.
- [x] 3.4 Implement line intersection, outer-corner ordering, and standard pickleball geometry validation.
- [x] 3.5 Convert accepted automatic keypoints into existing-compatible calibration keypoint correspondences and homography quality diagnostics.
- [x] 3.6 Generate preview artifacts showing mask evidence, fitted keypoints, and projected court overlay where available.

## 4. API and Calibration Service Integration

- [x] 4.1 Add an endpoint for requesting an automatic calibration suggestion for an uploaded video or frame.
- [x] 4.2 Add a service method that creates a semi-automatic calibration record from accepted automatic or corrected keypoints.
- [x] 4.3 Preserve manual calibration API behavior and ensure rejected automatic suggestions do not create misleading calibration records.
- [x] 4.4 Expose preview artifact URLs or paths through the automatic calibration response.

## 5. Frontend Calibration Handoff

- [x] 5.1 Add client API helpers for requesting automatic calibration and submitting accepted or corrected semi-automatic calibration.
- [x] 5.2 Update the upload/calibration workflow with an automatic calibration action, loading state, unavailable state, rejected state, and accepted state.
- [x] 5.3 Render the selected frame preview with detected keypoints and allow manual point correction before job creation.
- [x] 5.4 Create real analysis jobs with the accepted semi-automatic calibration ID while preserving manual and limited-analysis fallbacks.

## 6. Verification

- [x] 6.1 Add unit tests for COCO dataset validation using small fixture annotations.
- [x] 6.2 Add backend tests for unavailable model behavior, accepted geometry, rejected geometry, and semi-automatic calibration persistence.
- [x] 6.3 Add tests for mask-to-corners post-processing with synthetic masks or lightweight fixtures.
- [x] 6.4 Add frontend tests or focused checks for automatic calibration workflow states.
- [x] 6.5 Run relevant backend and frontend test suites and document any model-training steps that require local data or optional dependencies.
