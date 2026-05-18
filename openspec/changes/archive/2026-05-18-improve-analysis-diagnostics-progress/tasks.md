## 1. Frontend Error Diagnostics

- [x] 1.1 Add a structured analysis API error type/helper in `src/services/analysisClient.ts` that captures request path, resolved URL, HTTP status, status text, backend detail, and network failure context.
- [x] 1.2 Update `requestJson` and `requestForm` to parse FastAPI error bodies before throwing and to tolerate non-JSON error responses.
- [x] 1.3 Update upload, calibration, job creation, job loading, and result loading handlers in `src/App.tsx` to render structured error summaries without discarding existing user-friendly Chinese guidance.

## 2. Automatic Calibration Diagnostics

- [x] 2.1 Add compact diagnostic rendering for automatic calibration attempts using `status`, `detail`, `selected_frame`, `confidence`, `quality`, `mask`, and `preview_image_url`.
- [x] 2.2 Ensure unavailable, rejected, and request-failed automatic calibration states preserve the selected video, metadata, manual point controls, and existing preview frame.
- [x] 2.3 Verify older or partial automatic calibration responses do not crash the upload workflow when optional diagnostic fields are missing.

## 3. Backend Stage Progress

- [x] 3.1 Add a backend helper for deriving monotonic progress from ordered analysis stages and persisting only meaningful job updates.
- [x] 3.2 Update `run_analysis_job` and/or `AnalysisPipeline` integration to persist intermediate stage updates before long-running stage boundaries such as video read, frame sampling, detection, pose, tracking, projection, metrics, visualization, and report generation.
- [x] 3.3 Preserve final completed and failed result behavior while recording the first failed stage and detailed failure message when an intermediate stage fails.

## 4. Job Status UI

- [x] 4.1 Update the analysis job page to show the current active or failed stage beside the progress percentage.
- [x] 4.2 Improve the failed-job panel to include failed stage label, stage detail, stored error message, and retry or return-to-upload action context.
- [x] 4.3 Confirm polling continues to use backend job summaries and does not simulate progress independently of backend state.

## 5. Verification

- [x] 5.1 Add or update frontend tests for structured API error parsing and automatic calibration diagnostic rendering.
- [x] 5.2 Add or update backend tests for monotonic stage progress updates and failed-stage recording.
- [x] 5.3 Run relevant frontend build/lint checks and backend tests covering analysis job and automatic calibration flows.
