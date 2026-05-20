## ADDED Requirements

### Requirement: Analysis task deletion
The system SHALL allow users to delete eligible historical analysis tasks and their persisted local artifacts.

#### Scenario: Completed task is deleted
- **WHEN** the user confirms deletion for a completed analysis task
- **THEN** the backend removes the persisted job summary, generated report, raw pipeline result, per-job output directory, and in-memory records for that job

#### Scenario: Failed task is deleted
- **WHEN** the user confirms deletion for a failed analysis task
- **THEN** the backend removes available persisted job artifacts for that job without requiring a completed report or result to exist

#### Scenario: Active task deletion is blocked
- **WHEN** the user attempts to delete a task whose status is `uploaded`, `queued`, or `processing`
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

## MODIFIED Requirements

### Requirement: Task status actions
The system SHALL expose task actions according to each analysis task's current status, including delete actions for eligible historical tasks.

#### Scenario: Completed task is visible
- **WHEN** a task has status `completed`
- **THEN** the task row or card provides a primary action to view the video analysis result, secondary access to the analysis details page, and a delete action

#### Scenario: Processing task is visible
- **WHEN** a task has status `queued`, `uploaded`, or `processing`
- **THEN** the task row or card shows progress and links to the job status detail instead of enabling completed-result or delete actions

#### Scenario: Failed task is visible
- **WHEN** a task has status `failed`
- **THEN** the task row or card shows failure context when available and provides actions to inspect the task detail, start a new upload, or delete the failed task
