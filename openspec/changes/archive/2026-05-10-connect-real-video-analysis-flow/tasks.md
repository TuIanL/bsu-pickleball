## 1. Backend Job Flow

- [x] 1.1 Add durable local metadata loading for uploaded videos so analysis jobs can resolve `videoId` after process-local cache misses.
- [x] 1.2 Add durable local metadata loading for analysis jobs and pipeline results so job status survives API restarts during local MVP usage.
- [x] 1.3 Replace synchronous completed-only job creation for `videoId` requests with queued/processing/completed/failed status transitions.
- [x] 1.4 Persist and expose pipeline stage details for upload, calibration, video read, detection, tracking, projection, metrics, visualization, and report generation.
- [x] 1.5 Ensure `/api/analysis/jobs/{job_id}/result` returns raw pipeline output for completed real jobs and a clear not-ready/status response otherwise.
- [x] 1.6 Add backend tests for video upload, job creation with `videoId`, missing video failure, completed raw result retrieval, and not-ready result behavior.

## 2. Frontend Upload And Calibration

- [x] 2.1 Add `uploadVideo(file)` to the analysis API client using `multipart/form-data` without forcing JSON headers.
- [x] 2.2 Extend `createAnalysisJob` to accept `videoId`, optional `calibrationId`, and frame stride while preserving explicit demo/developer metadata-only support.
- [x] 2.3 Update the upload page to upload the selected file before job creation and show upload, calibration, job creation, and error states.
- [x] 2.4 Add a lightweight frame/corner calibration UI or handoff that submits top-left, top-right, bottom-right, and bottom-left image points for the uploaded video.
- [x] 2.5 Prevent silent mock success for real upload failures while keeping the existing demo route available.
- [x] 2.6 Update upload-page copy so it no longer says the selected video is only local mock data.

## 3. Job Status And Result Adaptation

- [x] 3.1 Poll job status on the analysis job page while a job is queued or processing and stop polling on completion or failure.
- [x] 3.2 Render backend pipeline stages and progress details on the job status page, including failure reasons.
- [x] 3.3 Add frontend types and client methods for raw `AnalysisPipelineResult` payloads.
- [x] 3.4 Build an adapter that maps pipeline tracks, movement metrics, heatmap data, and artifact metadata into the existing visual/report data model.
- [x] 3.5 Mark unsupported MVP report sections, such as ball landing, shot tactics, rally segmentation, and motion diagnosis, as unavailable or sample-only for real jobs.
- [x] 3.6 Show source clarity for demo, limited real analysis, and algorithm-derived job analysis across workspace and report pages.

## 4. Verification

- [x] 4.1 Add focused frontend tests or type checks for real upload request construction, job creation payloads, status polling, and result adapter behavior.
- [x] 4.2 Run backend tests and add any smoke fixtures needed for the new job lifecycle behavior.
- [x] 4.3 Run frontend build/lint checks.
- [x] 4.4 Manually verify the local MVP flow: start backend, start frontend, upload a supported video, submit calibration, create job, observe status, open visual analysis, and open a report.
- [x] 4.5 Verify backend-unavailable and calibration-failure paths keep user input and show recoverable errors.
