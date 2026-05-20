## 1. Backend task and artifact deletion

- [x] 1.1 Add backend helpers to delete a single analysis job summary, report, result JSON, per-job output directory, and in-memory cache entries.
- [x] 1.2 Add backend reference checks so linked uploaded videos and calibrations are deleted only when no remaining job references them.
- [x] 1.3 Expose single-job and batch-job deletion endpoints in the analysis API with blocked/partial/not-found responses for active or missing jobs.
- [x] 1.4 Add backend tests for completed-job deletion, active-job blocking, batch partial failure, and linked artifact cleanup.

## 2. Frontend deletion workflow

- [x] 2.1 Add analysis client methods and types for single and batch deletion requests and per-job deletion results.
- [x] 2.2 Add task-list selection state, select-all behavior, and delete confirmation UI in analysis task management.
- [x] 2.3 Wire single-delete and batch-delete actions into task cards, loading states, and recoverable error feedback.
- [x] 2.4 Refresh task history after successful deletion and preserve upload/navigation access after deletes.

## 3. Analysis details page and navigation

- [x] 3.1 Add `/analysis/:jobId/details` route parsing and rendering in the app shell/router.
- [x] 3.2 Implement the new analysis details page with job metadata, status summary, and a standard 2D pickleball court plan.
- [x] 3.3 Update completed-task actions to open analysis details instead of the landing report.
- [x] 3.4 Update navigation and fallback states so removed or unsupported report routes resolve safely.

## 4. Remove ball-analysis surfaces

- [x] 4.1 Remove ball overlay fetching, display, controls, and status rows from the visual analysis workspace.
- [x] 4.2 Remove landing-analysis, ball-trajectory, shot-explorer, and rally-specific real-job content from report/detail rendering paths.
- [x] 4.3 Update pipeline, schema, and adapter code so active real-job flow no longer exposes ball tracking or ball artifact metadata.
- [x] 4.4 Clean up demo copy and local fixtures so sample content does not masquerade as real ball analysis.

## 5. Verification

- [x] 5.1 Run backend tests covering task listing, deletion, artifact cleanup, and unsupported-ball state handling.
- [x] 5.2 Run frontend typecheck/build and verify selection, deletion, details routing, and unsupported report fallbacks.
- [x] 5.3 Manually verify delete, batch delete, and analysis details navigation on desktop and narrow viewports.
