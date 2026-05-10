## Why

The current web experience still behaves like a polished demo: users can choose a local video, but the frontend only sends filename metadata and the report remains demo-shaped. We need the upload flow to become a real analysis path where a selected video is persisted by the backend, linked to an analysis job, processed by the MVP pipeline, and surfaced back as meaningful feedback.

## What Changes

- Add a frontend-to-backend upload step that sends the selected video file to `/api/videos/upload` before creating an analysis job.
- Create analysis jobs with the returned `videoId`, optional calibration data, and metadata so the backend can run the MVP pipeline instead of only producing a metadata-only mock job.
- Expose job status, pipeline stages, failures, and raw algorithm results in a way the frontend can render without pretending incomplete results are final.
- Transform available pipeline outputs, including tracking, court projection, movement metrics, heatmap data, and artifact paths, into user-facing feedback in the job workspace.
- Preserve the existing demo route as a deliberate sample mode, while making real uploads fail recoverably when the backend cannot process the selected file.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `video-analysis-job-flow`: Require selected videos to be uploaded to the backend and linked to pipeline-backed jobs before job navigation.
- `visual-analysis-workspace`: Require completed job workspaces to reflect available backend algorithm output, not only static demo report data.
- `interactive-performance-report`: Require report/detail surfaces to distinguish algorithm-derived metrics from demo placeholders and show real movement feedback when available.

## Impact

- Frontend upload and analysis client code in `src/App.tsx`, `src/services/analysisClient.ts`, and related report types.
- Backend analysis job and pipeline APIs under `backend/app/api`, `backend/app/services`, and `backend/app/schemas`.
- Runtime storage under `backend/data/uploads`, `backend/data/outputs`, and optional calibration artifacts.
- Validation and tests for video upload, job creation with `videoId`, pipeline result retrieval, and frontend fallback/error states.
