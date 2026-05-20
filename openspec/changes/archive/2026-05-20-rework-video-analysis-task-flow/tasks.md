## 1. Backend Task Listing

- [x] 1.1 Add a backend service function that loads all persisted analysis job summaries from storage and merges them with active in-memory jobs by job id.
- [x] 1.2 Add `GET /api/analysis/jobs` returning sorted analysis job summaries with graceful handling for empty or unreadable persisted records.
- [x] 1.3 Add or update backend tests covering empty task lists, persisted completed jobs, active processing jobs, and malformed persisted records.

## 2. Frontend Task Data

- [x] 2.1 Add an analysis client function for retrieving the analysis task list with typed `AnalysisJobSummary[]` output.
- [x] 2.2 Add a frontend fallback strategy for demo/local stored jobs only when the backend list is unavailable or explicitly returning no persisted tasks.
- [x] 2.3 Ensure recent-job remembering remains compatible with task-list refresh and does not replace the full task history.

## 3. Routing And Navigation

- [x] 3.1 Add `/analysis/tasks` route parsing and rendering in `src/App.tsx`.
- [x] 3.2 Simplify `platformNavigation` to main page, video analysis, and training.
- [x] 3.3 Update `AppShell` active-state logic and header actions so video analysis points to upload/task workflow instead of the old completed-result workspace.
- [x] 3.4 Update overview and upload-adjacent actions so users can reach both upload and task management cleanly.

## 4. Task Management Page

- [x] 4.1 Implement an analysis task management page showing all tasks with match title, file label, timestamps, progress, status, and analysis mode.
- [x] 4.2 Add status-specific actions: completed tasks open video results and reports; active tasks open job detail; failed tasks expose diagnostics and retry/upload actions.
- [x] 4.3 Add loading, empty, recoverable error, manual refresh, and active-task polling states.
- [x] 4.4 Adjust upload completion routing so newly created tasks navigate to task management with the new task visible.

## 5. Clean Visual Result Workspace

- [x] 5.1 Refactor job-specific `VisionPage` so the first screen is primarily the video viewport plus a right-side status rail.
- [x] 5.2 Move report actions into compact tab-like controls in the status rail or adjacent secondary navigation.
- [x] 5.3 Remove full dashboard-style metric cards, coach notes, highlights, drill recommendations, and progress charts from the primary job-specific video workspace.
- [x] 5.4 Preserve demo `/vision` behavior with clear sample context and without breaking existing demo visual playback.
- [x] 5.5 Ensure limited, unavailable, skipped, and failed overlay states appear in the status rail without implying demo data is real output.

## 6. Report Flow

- [x] 6.1 Ensure completed-job report tabs/actions route to `/analysis/:jobId/reports/:type`.
- [x] 6.2 Ensure report detail pages return to the associated job-specific video result when a job id is present.
- [x] 6.3 Preserve direct sample report routes and sample context for demo use.

## 7. Verification

- [x] 7.1 Run frontend typecheck/build and backend tests relevant to analysis routes.
- [x] 7.2 Manually verify navigation flow: home → video analysis/upload → task management → completed video result → report → back to video.
- [x] 7.3 Manually verify task states for empty, queued/processing, completed, failed, and backend-unavailable conditions.
- [x] 7.4 Use browser verification for desktop and narrow viewports to confirm navigation, task management, and clean video workspace have no overlap or broken layout.
