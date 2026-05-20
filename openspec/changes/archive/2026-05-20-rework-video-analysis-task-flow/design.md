## Context

The current frontend already has the technical building blocks for a job-aware analysis flow: upload and calibration at `/analysis/new`, individual job status at `/analysis/:jobId`, completed visual results at `/analysis/:jobId/vision`, and report detail routes under `/analysis/:jobId/reports/:type`. The product structure still exposes too many peer-level destinations in the top navigation and lets users jump directly into a demo visual workspace, which weakens the real task lifecycle.

The backend persists job summaries to `outputs/jobs/*.json` and reports/results to adjacent JSON files, but it currently exposes only single-job retrieval. A task management page needs a reliable list of all persisted jobs, so the frontend should not depend only on the recent-job pointer or local demo storage.

## Goals / Non-Goals

**Goals:**

- Make the product feel like a single main page with a clear video-analysis task flow.
- Add a durable task management surface that lists all historical analysis jobs and their status.
- Route video analysis navigation through upload/task management before completed users reach the result workspace.
- Keep completed video result pages visually clean: primary video area plus right-side status rail.
- Move detailed report data into lower-level tabs or report pages without removing existing report route support.
- Preserve demo/sample access for presentations and backend-unavailable development.

**Non-Goals:**

- Replace the existing upload, calibration, pipeline, overlay, or report-generation algorithms.
- Add authentication, multi-user ownership, cloud storage, or server-side pagination.
- Redesign training recommendation content beyond linking it from the simplified navigation and result reports.
- Remove existing report routes; they remain valid secondary destinations.

## Decisions

### Decision: Add a backend task-list endpoint

The backend will expose a list endpoint for analysis job summaries, backed by persisted job JSON files plus any in-memory jobs. This makes `/analysis/tasks` represent "all previous and current tasks" across browser sessions and local page reloads.

Alternative considered: use only frontend `localStorage`. That would be simpler but would miss real backend jobs created in prior sessions, after reloads in a different browser, or after backend-side persistence. It also conflicts with the product meaning of historical task management.

### Decision: Introduce `/analysis/tasks` as the video-analysis hub

The top-level "视频分析" navigation target will route to a hub-like task management page. From there users can upload a new match, monitor active tasks, or open completed results.

Alternative considered: point "视频分析" directly to `/analysis/new`. That makes first-time upload quick but hides historical tasks. A task hub can still include a prominent upload action while matching the user's request for a management page after upload.

### Decision: Keep individual job status route as a detail state

The existing `/analysis/:jobId` page remains useful for deep job status, polling, and diagnostics. The new task list will show condensed progress and link to the detail page for queued, processing, or failed jobs, while completed jobs link to `/analysis/:jobId/vision`.

Alternative considered: remove the job status page and put all stage detail inside the list. That would overload the list and make failed/processing diagnostics harder to read.

### Decision: Refactor the visual result page into primary video plus status rail

The completed visual page will retain `VideoAnalysisCard` and real overlay playback, but the surrounding page will no longer stack metrics, coach notes, highlights, report cards, drills, and progress charts under the primary area. The first screen should show the video and a right-side status rail with job metadata, current layer availability, progress/completion state, and report tab links.

Alternative considered: keep all current detail modules below the video. That preserves existing content but violates the requested "pure" video page and makes the result page feel like a dashboard rather than a visual review workspace.

### Decision: Treat report tabs as lower-level navigation over existing report routes

Report actions can be presented as tabs or compact secondary navigation within the result context, but the detailed content should continue to render through existing report definitions and job-specific routes. This avoids duplicating report rendering logic while making the hierarchy clearer.

Alternative considered: inline all report pages into the video page tabs. That would satisfy the tab metaphor but create a large, stateful page with duplicated report rendering and harder routing/back behavior.

## Risks / Trade-offs

- Backend job list may grow without pagination → Keep the MVP list simple, sorted by `updatedAt` or `createdAt`, and leave pagination/search as future work.
- Some jobs may have malformed or older persisted JSON → Skip invalid records or surface a stable load error rather than breaking the entire task list.
- Simplifying top navigation may hide hardware/demo surfaces used in presentations → Keep direct routes available and preserve demo affordances from overview or development links where appropriate.
- Moving modules out of the video page may make existing analytics feel less visible → Provide compact report tabs/actions in the status rail so users can discover detailed analysis without cluttering the video workspace.
- The new list endpoint overlaps with in-memory job state during active processing → Merge in-memory jobs and persisted jobs by job id, preferring the freshest in-memory summary before sorting.

## Migration Plan

1. Add backend task listing and frontend client support while leaving existing routes untouched.
2. Add the task management route and page.
3. Change top navigation and upload completion routing to use the task flow.
4. Refactor the completed visual result page layout.
5. Verify upload, active polling, completed result entry, report tabs, demo access, and responsive navigation.

Rollback is straightforward because existing single-job routes remain intact: restore top navigation targets and upload completion routing to the previous paths if the new hub blocks demos.

## Open Questions

- Should the task list show failed jobs permanently, or should there be a later cleanup/archive action?
- Should `/vision` remain a demo-only route, redirect to `/analysis/tasks`, or act as an alias for the video-analysis hub?
