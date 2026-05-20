## Why

The new analysis task management page lets users see historical jobs, but it cannot yet remove old analysis records or their local files. At the same time, the product should temporarily step back from ball capture, landing, shot, and rally claims until player coordinate projection and movement capture are ready.

This change makes task history manageable, prevents stale local artifacts from accumulating, and replaces the completed-task "landing report" path with a neutral analysis details page centered on a standard two-dimensional pickleball court.

## What Changes

- Add real deletion for analysis jobs so removing a task deletes the persisted backend job summary, generated report/result JSON, per-job output directory, overlays, and safe-to-delete linked local video/calibration artifacts.
- Add batch deletion from the task management page with selection controls, confirmation, progress/error feedback, and partial-result handling.
- Replace completed task secondary access from "落点报告" to an analysis details page.
- Add a job-specific analysis details route that shows task metadata, analysis status, and a standard pickleball court 2D plan as the future projection surface for player movement visualization.
- Remove user-facing ball capture analysis, landing analysis, ball trajectory overlays, shot exploration, and rally/shot claims from the current real-analysis product flow.
- Keep person detection, pose availability, court calibration, player tracking, court projection, movement metrics, and demo/sample routes where they remain useful.
- **BREAKING UI**: completed real-analysis jobs no longer expose landing report or ball trajectory controls as supported result actions in the task/result workflow.

## Capabilities

### New Capabilities

- `analysis-details-page`: Covers the job-specific analysis details page, standard 2D pickleball court visualization, and future projection handoff for player movement data.

### Modified Capabilities

- `analysis-task-management`: Add single and batch task deletion that removes persisted local artifacts rather than only hiding tasks in the frontend.
- `layered-product-navigation`: Add job-specific analysis details routing and update completed task actions away from landing report entry.
- `visual-analysis-workspace`: Remove real-job ball overlay controls/status/rendering and keep the completed visual workspace focused on video, person/pose overlays, and status.
- `interactive-performance-report`: Remove current ball/landing/shot/rally claims from real-analysis report surfaces and require unavailable or omitted states until supporting algorithms are reintroduced.
- `video-analysis-job-flow`: Remove ball-tracking stages/artifacts from the active real-analysis job flow and route completed task secondary details to the analysis details page.
- `report-detail-pages`: Remove landing-analysis expectations from the current supported real-job report flow while preserving non-real demo/sample contexts where explicitly labeled.
- `ball-tracking`: Deactivate the current backend ball detection, trajectory, and overlay artifact requirements until a later ball-capture change reintroduces them.
- `multitarget-perception`: Narrow current perception requirements to player/person targets and remove ball/paddle target expectations from the active pipeline contract.

## Impact

- Backend API and services: `backend/app/api/routes_analysis.py`, `backend/app/services/mock_analysis.py`, `backend/app/services/storage_service.py`, and related video/calibration cleanup helpers.
- Backend schemas/pipeline: analysis stage definitions, pipeline artifacts, report generation, and tests that currently mention ball tracking or landing results.
- Frontend API client and types: `src/services/analysisClient.ts`, `src/types/report.ts`, and delete/batch-delete request/result types.
- Frontend routing and UI: `src/App.tsx`, task management cards, result status rail, report/detail routing, and standard court visualization components.
- Existing specs for task management, navigation, visual workspace, job flow, report pages, and interactive performance report.
