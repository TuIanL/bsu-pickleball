## Why

The current frontend presents video analysis, reports, training, and hardware as peer top-level destinations, which makes the real uploaded-video workflow feel like a set of disconnected modules instead of a coherent analysis task flow. The product should preserve one main page while guiding users from video analysis entry, to match upload, to historical task management, and finally to a focused video-first result workspace.

## What Changes

- Replace the current broad top navigation model with a simpler primary navigation: main page, video analysis, and training.
- Change the video analysis entry so users start from the upload workflow or task-management flow rather than landing directly in the old full analysis workspace.
- Add an analysis task management page that lists all analysis tasks from past to present, shows status labels such as queued, processing, completed, and failed, and exposes result actions only when tasks are completed.
- Route newly created analysis jobs into the task-management/status flow after upload so users can see their task in context with other historical tasks.
- Refocus the completed-task video analysis page around a clean video viewport plus a right-side vertical status rail.
- Move detailed analysis reports, metrics, diagnostics, and training-related interpretation out of the main video viewport and into lower-level tabs or report detail pages.
- Preserve existing job-specific report routes and demo/sample paths, but make them secondary to the task-centered workflow.
- **BREAKING UI**: report and hardware pages are no longer exposed as first-class top navigation peers, though existing report routes remain reachable from completed analysis results.

## Capabilities

### New Capabilities

- `analysis-task-management`: Covers the historical task list, task status affordances, completed-result actions, and backend/frontend task listing behavior.

### Modified Capabilities

- `layered-product-navigation`: Simplify top-level navigation and make video analysis route users into the task-centered upload/results workflow.
- `video-analysis-job-flow`: Update post-upload routing and job-flow expectations so analysis jobs appear in a task management surface.
- `visual-analysis-workspace`: Refocus completed video analysis around a clean video viewport and right-side status rail, with detailed data moved below the primary video surface.
- `report-detail-pages`: Clarify that report pages are lower-level destinations reached from completed results or result tabs rather than top-level navigation peers.

## Impact

- Frontend routing in `src/App.tsx`, including route parsing, navigation targets, upload completion behavior, and new task-management rendering.
- App shell/navigation data in `src/components/platform/AppShell.tsx` and `src/data/demoData.ts`.
- Analysis API client in `src/services/analysisClient.ts` for retrieving all known tasks.
- Backend analysis API in `backend/app/api/routes_analysis.py` and storage/mock analysis services for listing persisted job summaries.
- Existing report and visual analysis components may need layout adjustments to separate the primary video workspace from detailed report modules.
