# analysis-task-management Specification

## Purpose
TBD - created by archiving change rework-video-analysis-task-flow. Update Purpose after archive.
## Requirements
### Requirement: Analysis task list retrieval
The system SHALL provide a way to retrieve all known durable analysis job summaries from current and previous analysis sessions.

#### Scenario: Backend lists persisted jobs
- **WHEN** the frontend requests the analysis task list
- **THEN** the backend returns all readable persisted job summaries plus active job summaries, sorted by most recent update or creation time first

#### Scenario: No analysis jobs exist
- **WHEN** the frontend requests the analysis task list and no jobs have been created
- **THEN** the backend returns an empty list rather than an error

#### Scenario: Persisted job record is unreadable
- **WHEN** one persisted job summary cannot be parsed
- **THEN** the backend skips or isolates that record without preventing the remaining valid jobs from being listed

#### Scenario: Interrupted running job is listed after restart
- **WHEN** the backend restarts after a job was running and no worker can confirm continued execution
- **THEN** the task list exposes a stable queued, failed/interrupted, or recoverable state rather than leaving the job indefinitely active

### Requirement: Analysis task management page
The system SHALL provide an analysis task management page that shows all historical and current video analysis tasks with clear orchestration-aware status labels.

#### Scenario: User opens task management page
- **WHEN** the user navigates to the analysis task management route
- **THEN** the page lists analysis tasks with match title, uploaded file label, creation or update time, progress, current stage, and a status label such as queued, running, succeeded, failed, canceled, or compatible display labels

#### Scenario: User has no tasks
- **WHEN** the user opens the task management page before any analysis task exists
- **THEN** the page shows an empty state with a clear action to upload a match video

#### Scenario: Task list cannot load
- **WHEN** the backend task list request fails
- **THEN** the page shows a stable recoverable error state and keeps upload access available

#### Scenario: Task has stage telemetry
- **WHEN** a task includes stage timing, error code, retry count, or cancellation context
- **THEN** the page exposes the most useful user-facing fields without showing internal stack traces or sensitive local paths

### Requirement: Task status actions
The system SHALL expose task actions according to each analysis task's current status, including cancellation for active tasks and delete actions for eligible historical tasks.

#### Scenario: Completed task is visible
- **WHEN** a task has status `succeeded` or compatible completed status
- **THEN** the task row or card provides a primary action to view the video analysis result, secondary access to the analysis details page, and a delete action

#### Scenario: Processing task is visible
- **WHEN** a task has status `queued`, `uploaded`, `running`, or compatible processing status
- **THEN** the task row or card shows progress, links to the job status detail, and offers cancellation when the backend allows it instead of enabling completed-result or delete actions

#### Scenario: Failed task is visible
- **WHEN** a task has status `failed`
- **THEN** the task row or card shows failure context when available and provides actions to inspect the task detail, start a new upload, retry when available, or delete the failed task

#### Scenario: Canceled task is visible
- **WHEN** a task has status `canceled`
- **THEN** the task row or card shows cancellation context and provides actions to inspect the task detail, start a new upload, or delete the canceled task

### Requirement: Task list refresh
The system SHALL keep active analysis tasks reasonably current while the user is viewing task management.

#### Scenario: Active task is listed
- **WHEN** the task management page contains a queued, uploaded, running, or compatible processing task
- **THEN** the frontend refreshes the task list or affected task summaries until no active tasks remain

#### Scenario: User manually refreshes tasks
- **WHEN** the user activates a refresh control on the task management page
- **THEN** the frontend reloads task summaries and preserves stable navigation and scroll behavior

#### Scenario: Cancellation is pending
- **WHEN** a cancellation request has been made but the job has not reached terminal canceled state
- **THEN** the frontend continues refreshing the affected task until the latest durable status is visible

### Requirement: Analysis task deletion
The system SHALL allow users to delete eligible historical analysis tasks and their persisted local artifacts.

#### Scenario: Completed task is deleted
- **WHEN** the user confirms deletion for a completed or succeeded analysis task
- **THEN** the backend removes the persisted job summary, generated report, raw pipeline result, per-job output directory, and active records for that job

#### Scenario: Failed task is deleted
- **WHEN** the user confirms deletion for a failed analysis task
- **THEN** the backend removes available persisted job artifacts for that job without requiring a completed report or result to exist

#### Scenario: Canceled task is deleted
- **WHEN** the user confirms deletion for a canceled analysis task
- **THEN** the backend removes available persisted job artifacts for that job without requiring a completed report or result to exist

#### Scenario: Active task deletion is blocked
- **WHEN** the user attempts to delete a task whose status is `uploaded`, `queued`, `running`, or compatible processing status
- **THEN** the backend rejects or marks that deletion as blocked and leaves all local files intact

#### Scenario: Deleted task is no longer listed
- **WHEN** a task deletion succeeds and the frontend refreshes task management
- **THEN** the deleted task no longer appears in the task list and direct job/result/report routes for that job show stable not-found states

#### Scenario: Linked artifacts are shared
- **WHEN** a deleted task references an uploaded video or calibration that is still referenced by another remaining job
- **THEN** the backend preserves the shared video, video metadata, calibration, and preview files

#### Scenario: Linked artifacts are unreferenced
- **WHEN** a deleted task references an uploaded video or calibration that no remaining job references
- **THEN** the backend removes the linked source video, video metadata, calibration JSON, and generated calibration preview files when those files exist

### Requirement: Batch analysis task deletion
The system SHALL support deleting multiple eligible analysis tasks from task management in one user action.

#### Scenario: User selects multiple tasks
- **WHEN** the task management page contains historical tasks
- **THEN** the user can select individual tasks, select all eligible visible tasks, and see the number of selected tasks before deleting

#### Scenario: Batch delete succeeds
- **WHEN** the user confirms batch deletion for selected completed or failed tasks
- **THEN** the backend deletes each eligible task's persisted local artifacts and the frontend removes the deleted tasks from the visible list

#### Scenario: Batch delete has partial failures
- **WHEN** a batch delete includes missing, blocked, or failed items
- **THEN** the backend returns per-job deletion results and the frontend reports which tasks were deleted and which require attention

#### Scenario: User cancels batch deletion
- **WHEN** the user opens the batch delete confirmation and cancels it
- **THEN** no backend deletion request is made and task selection remains unchanged or is safely dismissed without deleting files

### Requirement: Delete feedback and refresh
The system SHALL provide clear feedback for deletion actions and keep task management state current after deletion.

#### Scenario: Delete request is in progress
- **WHEN** a single or batch deletion is running
- **THEN** the affected delete controls show a pending state and prevent duplicate deletion requests for the same selected tasks

#### Scenario: Delete request cannot reach backend
- **WHEN** a delete request fails because the backend cannot be reached
- **THEN** the frontend shows a recoverable error state and does not remove tasks from the list as if deletion had succeeded

#### Scenario: Delete completes
- **WHEN** a single or batch deletion finishes
- **THEN** the frontend refreshes task summaries, clears deleted task selections, and preserves access to upload and manual refresh actions

### Requirement: Task cancellation feedback
The system SHALL provide clear feedback for cancellation actions from task management and job status surfaces.

#### Scenario: Cancellation request is in progress
- **WHEN** a cancellation request is being submitted
- **THEN** the affected cancellation control shows a pending state and prevents duplicate cancellation requests for the same job

#### Scenario: Cancellation request succeeds
- **WHEN** the backend accepts a cancellation request
- **THEN** the frontend refreshes the affected task and communicates that cancellation will complete at a safe checkpoint when the job is running

#### Scenario: Cancellation request fails
- **WHEN** a cancellation request cannot be accepted or cannot reach the backend
- **THEN** the frontend shows a recoverable error and does not pretend the job has been canceled

### Requirement: Analysis task list filters by recording session
The system SHALL support filtering analysis tasks by `recording_session_id` query parameter, enabling per-recording task views.

#### Scenario: Filter by recording session ID
- **WHEN** the frontend requests `GET /api/analysis/jobs?recording_session_id=<sid>`
- **THEN** the backend SHALL return only jobs whose `metadata.recording_session_id` matches `<sid>`
- **AND** if no matching jobs exist, SHALL return an empty list

### Requirement: Analysis task recording origin display
The system SHALL expose the recording session origin of analysis jobs via the `AnalysisJobSummary` and SHALL display it in the task management UI.

#### Scenario: Task has recording session origin
- **WHEN** an `AnalysisJobSummary` has `recordingSessionId` or `metadata.recording_session_id` set
- **THEN** the task card SHALL display a "来源录制" badge with the camera slot label (A/B machine position)
- **AND** the badge SHALL include a link to navigate back to the corresponding recording card

#### Scenario: Dual-camera recording cards show analysis status
- **WHEN** the dual-camera recording tab lists sync recording sessions
- **THEN** each card SHALL query analysis jobs belonging to that session
- **AND** cam analysis buttons SHALL reflect the analysis job status: "分析 X 机位" (no job), "分析中 N%" (running), "查看 X 分析报告" (completed), "重新分析" (failed/canceled)

#### Scenario: Upload tab excludes dual-camera derived tasks
- **WHEN** the upload tasks tab displays analysis jobs
- **THEN** tasks whose `recording_session_id` matches an existing sync recording session SHALL be excluded from this tab
- **AND** they SHALL appear exclusively within the corresponding dual-camera recording cards
