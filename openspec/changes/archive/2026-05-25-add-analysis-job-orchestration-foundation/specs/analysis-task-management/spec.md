## MODIFIED Requirements

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

## ADDED Requirements

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
