## MODIFIED Requirements

### Requirement: Task status actions

The system SHALL expose task actions according to each analysis task's current status, including cancellation for active tasks, recovery actions for interrupted tasks, and delete actions for eligible historical tasks.

#### Scenario: Completed task is visible

- **WHEN** a task has status `succeeded` or compatible completed status
- **THEN** the task row or card provides a primary action to view the video analysis result, secondary access to the analysis details page, and a delete action

#### Scenario: Processing task is visible

- **WHEN** a task has status `queued`, `uploaded`, `running`, or compatible processing status with fresh Worker liveness
- **THEN** the task row or card shows progress, links to the job status detail, and offers cancellation when the backend allows it instead of enabling completed-result or delete actions

#### Scenario: Interrupted task is visible

- **WHEN** a task has status `interrupted` or Worker liveness is durably marked lost
- **THEN** the task row or card shows the user-facing label “任务失联” and the last known stage/progress
- **AND** SHALL stop treating the task as an active processing task
- **AND** SHALL offer task detail, explicit re-analysis/retry and delete actions instead of ordinary cancellation

#### Scenario: Failed task is visible

- **WHEN** a task has status `failed`
- **THEN** the task row or card shows failure context when available and provides actions to inspect the task detail, start a new upload, retry when available, or delete the failed task

#### Scenario: Canceled task is visible

- **WHEN** a task has status `canceled`
- **THEN** the task row or card shows cancellation context and provides actions to inspect the task detail, start a new upload, or delete the canceled task

### Requirement: Task list refresh

The system SHALL keep queued and genuinely running analysis tasks reasonably current while the user is viewing task management. An interrupted task SHALL stop active polling after its durable state is received.

#### Scenario: Active task is listed

- **WHEN** the task management page contains a queued, uploaded, or running task with fresh Worker liveness
- **THEN** the frontend refreshes the task list or affected task summaries until no active tasks remain

#### Scenario: Interrupted task is listed

- **WHEN** the task management page receives an interrupted task
- **THEN** the frontend SHALL render “任务失联” with the last heartbeat/interruption context when available
- **AND** SHALL remove the task from the active polling set

#### Scenario: User manually refreshes tasks

- **WHEN** the user activates a refresh control on the task management page
- **THEN** the frontend reloads task summaries and preserves stable navigation and scroll behavior

#### Scenario: Cancellation is pending

- **WHEN** a cancellation request has been made but the job has not reached terminal canceled state
- **THEN** the frontend continues refreshing the affected task until the latest durable status is visible

### Requirement: Analysis task deletion

The system SHALL allow users to delete eligible historical analysis tasks and their persisted local artifacts, including tasks durably marked interrupted.

#### Scenario: Completed task is deleted

- **WHEN** the user confirms deletion for a completed or succeeded analysis task
- **THEN** the backend removes the persisted job summary, generated report, raw pipeline result, per-job output directory, and active records for that job

#### Scenario: Failed task is deleted

- **WHEN** the user confirms deletion for a failed analysis task
- **THEN** the backend removes available persisted job artifacts for that job without requiring a completed report or result to exist

#### Scenario: Interrupted task is deleted

- **WHEN** the user confirms deletion for an interrupted analysis task and no Worker lease remains active
- **THEN** the backend removes the task record and available persisted artifacts
- **AND** SHALL preserve shared source video, calibration and recording assets according to existing reference rules

#### Scenario: Active task deletion is blocked

- **WHEN** the user attempts to delete a task whose status is `uploaded`, `queued`, or running processing with fresh Worker liveness
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
