## Context

The app already has a task-centered video workflow with upload, calibration, task list, job status, visual results, and report routes. Historical jobs are persisted in local backend storage under `data/outputs`, while uploaded videos and calibrations live under `data/uploads` and `data/calibrations`.

The current task list can show history but cannot delete it. Removing a task only in frontend state would leave backend JSON, generated overlays, uploaded videos, and calibration files on disk. The product is also in a transition: current ball/landing/shot/rally UI overstates capabilities that are not ready for the next phase, where the immediate goal is to project people movement onto a standard 2D pickleball court.

## Goals / Non-Goals

**Goals:**

- Add backend-backed single and batch deletion for analysis tasks and local artifacts.
- Keep deletion deterministic and safe by preventing deletion of running jobs until cancellation exists.
- Keep task management responsive after deletes, including partial batch-delete failures.
- Add a neutral analysis details page that can become the future player movement projection surface.
- Render a standard 20 ft by 44 ft pickleball court plan with net, kitchen lines, service boxes, and stable labels.
- Remove current user-facing ball capture, landing, shot, and rally analysis from real-job flows.

**Non-Goals:**

- Add job cancellation for queued or processing tasks.
- Add cloud storage, multi-user ownership, auth, server pagination, or restore/undo.
- Complete coordinate conversion, player displacement visualization, or heatmap projection on the new details page.
- Reintroduce ball capture, bounce detection, shot classification, rally segmentation, or landing analysis in this change.
- Delete demo source data, archived OpenSpec artifacts, fixtures needed by tests unless those tests are intentionally removed or rewritten.

## Decisions

### Decision: Delete through backend APIs, not frontend hiding

The frontend will call a backend delete endpoint for single deletes and a batch delete endpoint for multiple jobs. The backend performs artifact deletion and updates in-memory stores before the frontend refreshes the list.

Alternative considered: remove items from frontend task state or `localStorage`. That would satisfy visibility but violate the requirement that local files are actually deleted.

### Decision: Block deletion for active jobs

Jobs with `uploaded`, `queued`, or `processing` status will not be deleted by this change. The API returns a clear conflict result for those jobs and leaves all files intact.

Alternative considered: delete active jobs and let the background task fail if it later writes artifacts. That creates race conditions and could leave partial files. Cancellation should be a separate capability.

### Decision: Use per-job deletion results for batch operations

Batch deletion will return one result per requested job id with statuses such as `deleted`, `not_found`, `blocked`, or `failed`. The frontend can then remove successfully deleted jobs while explaining failures.

Alternative considered: fail the whole batch if any item cannot be deleted. That makes bulk cleanup frustrating and prevents successful cleanup of unrelated completed/failed jobs.

### Decision: Clean linked video and calibration only when unreferenced

Deleting a job should remove that job's summary, report, result JSON, and output directory. Linked uploaded video files, video metadata, calibration JSON, and calibration preview files should be removed only when no remaining job references the same `videoId` or `calibrationId`.

Alternative considered: always delete linked video/calibration files. That is simpler but can break another job created from the same upload or calibration.

### Decision: Add `/analysis/:jobId/details` as a neutral details route

The completed task card's secondary action will open an analysis details page instead of a landing report. The details page will load job/report/result context and render the standard court plan, current processing metadata, and a future-data placeholder for projected movement.

Alternative considered: reuse `/analysis/:jobId/reports/movement`. That would be quicker but keeps the mental model tied to report categories while the user asked for an analysis details page.

### Decision: Remove ball-specific real-job contracts now

The active pipeline, result schemas, API client, visual status rail, video overlay card, and real-job report generation should no longer expose ball overlay status, ball overlay artifact URLs, landing analysis, shot explorer data, or rally claims. Demo/sample visuals may remain only when they are clearly local demo content and do not masquerade as real analysis.

Alternative considered: leave ball code in place but hide buttons. That would keep dead contracts in the backend and make it easy for stale output to leak into the UI.

## Risks / Trade-offs

- Deleted files cannot be restored -> show confirmation and include counts/labels before deletion.
- Active job deletion is not supported -> return blocked results and explain that active jobs must finish or fail before cleanup.
- Shared upload/calibration cleanup can accidentally remove dependencies if reference checks are incomplete -> compute references from all remaining persisted and in-memory jobs before deleting linked files.
- Older persisted results may still contain ball fields -> readers should ignore unknown ball fields without rendering them.
- Removing ball-related tests may reduce coverage of old behavior -> replace with tests for deletion, details routing, and player/person overlay continuity.
- Demo content may still contain sample shot language -> keep demo-only labels explicit and remove real-job pathways to those claims.

## Migration Plan

1. Add backend delete services and tests while keeping list/read APIs unchanged.
2. Add frontend delete client methods and task-list selection state.
3. Add `/analysis/:jobId/details` route and standard court plan component.
4. Update completed task actions and status rail navigation to use the details page and movement/person-focused report actions.
5. Remove ball overlay types, fetches, artifact references, stages, controls, and real-job report copy.
6. Verify existing stored jobs still list, can be deleted, and older ball fields do not crash result loading.

Rollback is possible by restoring the previous report action routing and ball artifact fields, but deleted local files cannot be recovered without external backups.

## Open Questions

- Should active jobs eventually support a separate "cancel and delete" action?
- Should batch deletion allow deleting only failed/completed tasks by default, or also selected demo jobs?
- Should the analysis details page eventually replace all job-specific report routes, or remain a high-level bridge into movement/diagnosis details?
