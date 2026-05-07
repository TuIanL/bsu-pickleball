## Why

The current product is a polished front-end demonstration that renders visual analysis from local mock data, but the next development phase needs a real video analysis flow backed by Python computer-vision pipelines. Establishing the upload, analysis-task, and backend foundation now lets YOLO11, RTMPose26, and later model choices plug into a stable product and data contract instead of forcing a rewrite when the algorithms arrive.

## What Changes

- Add a front-end analysis workflow for starting a new video analysis, tracking processing status, and opening completed analysis results.
- Add a Python backend foundation using FastAPI-style API boundaries, structured schemas, local storage conventions, and mock analysis responses.
- Define an analysis job lifecycle covering upload, queued, processing, failed, and completed states.
- Define an analysis report contract that can carry video metadata, court points, routes, movement paths, rally events, pose-derived diagnosis, coach notes, highlights, and report actions.
- Reserve clear backend extension points for detector, pose, tracking, court-calibration, and event-analysis modules, including YOLO11 and RTMPose26 adapters.
- Extend the existing visual analysis workspace so it can render either the current demo session or a completed analysis job.
- Extend report detail pages so they can open report results associated with an analysis job while preserving the current sample-report fallback.

## Capabilities

### New Capabilities

- `video-analysis-job-flow`: Covers video upload entry, analysis job creation, progress/status display, failure handling, and opening completed results.
- `python-vision-backend-foundation`: Covers the backend API skeleton, data schemas, local storage boundaries, mock analysis output, and algorithm adapter extension points.

### Modified Capabilities

- `layered-product-navigation`: Add navigation and routing requirements for upload/new-analysis and job-specific result pages.
- `visual-analysis-workspace`: Allow the workspace to render job-specific analysis results while keeping the current demo experience available.
- `report-detail-pages`: Allow report detail pages to render analysis-job report data in addition to local sample data.

## Impact

- Front-end routes, navigation, and page state for upload, analysis status, job-specific vision, and job-specific report views.
- Shared TypeScript data shapes for analysis jobs, analysis status, and analysis report payloads.
- New `backend/` project area for Python service code, schemas, API routes, mock analysis, and future vision algorithms.
- Python dependencies and environment documentation for the lightweight API layer, with heavy model dependencies kept optional until real YOLO11/RTMPose26 integration begins.
- Local storage conventions for uploaded videos, generated report JSON, temporary processing files, and model weights, with large/generated assets excluded from version control.
