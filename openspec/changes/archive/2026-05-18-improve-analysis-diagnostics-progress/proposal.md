## Why

The real-video analysis workflow currently hides too much diagnostic context when backend calls or model stages fail, leaving the frontend with generic messages such as "failed" or "unable to recognize". The analysis job progress also jumps from a coarse early value to completion, so users cannot tell which stage is running or where a problem occurred.

## What Changes

- Preserve structured backend error details in frontend-facing API failures, including status code, endpoint, backend detail, and operation context where available.
- Improve the analysis job status page so progress is derived from real stage state and shows current stage, failed stage, and actionable diagnostics.
- Update the backend job runner to persist intermediate progress as pipeline stages advance instead of reporting only an initial processing percentage and final completion.
- Expand automatic court-line calibration feedback so unavailable, rejected, and failed states show model configuration, selected frame, confidence, mask, geometry, and preview diagnostics when returned by the backend.
- Keep manual four-corner calibration available when automatic calibration is unavailable or rejected, without losing the uploaded video or match metadata.

## Capabilities

### New Capabilities

- None

### Modified Capabilities

- `video-analysis-job-flow`: Require user-facing analysis errors and progress indicators to expose structured stage-level diagnostics and real intermediate progress.
- `automatic-court-line-calibration`: Require automatic calibration unavailable/rejected/failure states to expose actionable model, frame, mask, confidence, geometry, and preview diagnostics to the upload workflow.

## Impact

- Frontend services: `src/services/analysisClient.ts` should parse backend error payloads and expose structured error metadata.
- Upload and job status UI: `src/App.tsx` should render detailed API, analysis, and automatic calibration diagnostics without breaking existing demo routes.
- Backend job orchestration: `backend/app/services/mock_analysis.py` and the pipeline integration may need a progress callback or staged updates while `AnalysisPipeline.run()` executes.
- Backend schemas and API payloads should remain backward compatible; existing optional diagnostic fields can be reused where possible.
- Tests should cover failed API parsing, automatic calibration diagnostic rendering/state handling, and monotonic progress/stage updates.
