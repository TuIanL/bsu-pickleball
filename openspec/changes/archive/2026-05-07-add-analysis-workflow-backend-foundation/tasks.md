## 1. Shared Analysis Types And Frontend Data Contract

- [x] 1.1 Add TypeScript types for analysis job status, upload metadata, processing stages, job summary, backend errors, and analysis report payloads.
- [x] 1.2 Map the existing local demo data into the new analysis report shape while preserving current visual and report rendering behavior.
- [x] 1.3 Add a frontend API client abstraction for creating jobs, reading job status, and reading job reports, with a demo or mock fallback path.

## 2. Frontend Routing And Navigation

- [x] 2.1 Extend route parsing and app state for new analysis/upload, analysis job status, job-specific visual analysis, and job-specific report routes.
- [x] 2.2 Update primary navigation and overview CTAs so starting a new analysis opens the upload workflow.
- [x] 2.3 Preserve existing demo routes for `/vision` and `/reports/:type` when no job identifier is present.
- [x] 2.4 Add stable fallback behavior for unknown job routes, unsupported report types, and unavailable backend responses.

## 3. Upload And Job Status Experience

- [x] 3.1 Build the new analysis/upload page with video file selection, required match metadata fields, validation, and start-analysis action.
- [x] 3.2 Implement upload form states for empty input, selected video, incomplete metadata, submitting, submission error, and successful job creation.
- [x] 3.3 Build the analysis job status page with queued, processing, failed, and completed states.
- [x] 3.4 Add completed-job actions that route to job-specific visual analysis and landing, movement, rally, and diagnosis report pages.

## 4. Job-Aware Visual Analysis And Reports

- [x] 4.1 Update the visual analysis page to load and render job-specific analysis reports when a job identifier is present.
- [x] 4.2 Add visual analysis states for queued/processing jobs, failed jobs, unknown jobs, and unloaded reports.
- [x] 4.3 Update report detail pages to load and render job-specific report data when a job identifier is present.
- [x] 4.4 Add report page states for queued/processing jobs, failed jobs, unknown jobs, unavailable reports, and demo/sample context.
- [x] 4.5 Show subtle source metadata that distinguishes local demo data from uploaded-video analysis results.

## 5. Python Backend Foundation

- [x] 5.1 Create the `backend/` project structure with API entrypoint, route modules, schema modules, service modules, and reserved `vision/` algorithm modules.
- [x] 5.2 Add lightweight Python environment metadata and setup documentation for the API layer.
- [x] 5.3 Implement backend schemas for analysis jobs, upload metadata, job status responses, report payloads, and API errors.
- [x] 5.4 Implement mock API endpoints for job creation, job status retrieval, and completed report retrieval.
- [x] 5.5 Implement a mock analysis service that returns report payloads compatible with the frontend analysis report contract.

## 6. Vision Algorithm Extension Boundaries

- [x] 6.1 Add placeholder modules or interfaces for detector, pose estimator, tracker, court calibration, and event analysis.
- [x] 6.2 Document how a future YOLO11 detector adapter should normalize detections for the report pipeline.
- [x] 6.3 Document how a future RTMPose26 pose adapter should normalize keypoints or pose-derived features for the report pipeline.
- [x] 6.4 Ensure the lightweight backend smoke path does not require YOLO11, RTMPose26, CUDA, model weights, or uploaded sample videos.

## 7. Storage And Repository Hygiene

- [x] 7.1 Add local storage conventions for uploads, generated reports, temporary processing files, and model weights.
- [x] 7.2 Update ignore rules or documentation so uploaded videos, generated artifacts, model checkpoints, temporary frames, and training datasets are not committed.
- [x] 7.3 Add a small committed fixture or mock response only if needed for backend/frontend smoke verification.

## 8. Integration And Verification

- [x] 8.1 Wire the frontend upload and job pages to the mock backend API or documented mock fallback.
- [x] 8.2 Verify the end-to-end mock flow: start analysis, view job status, complete job, open visual analysis, and open each report type.
- [x] 8.3 Run frontend lint and build checks, then fix any TypeScript, ESLint, or Vite issues.
- [x] 8.4 Run backend smoke verification, then fix any Python import, schema, or route errors.
- [x] 8.5 Check desktop and mobile layouts for upload, job status, job-specific vision, and job-specific reports.
