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
The system SHALL provide clear feedback for deletion actions via a compact floating toast that auto-dismisses when all selected items are deleted and requires manual dismissal when some items are blocked or failed, and SHALL keep task management state current after deletion. Persistent error states such as a failed task-list load SHALL remain inline rather than being shown as a transient toast.

#### Scenario: Delete request is in progress
- **WHEN** a single or batch deletion is running
- **THEN** the affected delete controls show a pending state and prevent duplicate deletion requests for the same selected tasks

#### Scenario: Delete request cannot reach backend
- **WHEN** a delete request fails because the backend cannot be reached
- **THEN** the frontend shows a recoverable error state and does not remove tasks from the list as if deletion had succeeded

#### Scenario: Delete completes
- **WHEN** a single or batch deletion finishes
- **THEN** the frontend refreshes task summaries, clears deleted task selections, and preserves access to upload and manual refresh actions

#### Scenario: Delete result shown as a floating toast
- **WHEN** a single or batch deletion finishes with any result
- **THEN** the frontend shows a compact toast fixed to the bottom-right of the viewport with a single line of text, without displacing the task list content

#### Scenario: Fully successful delete auto-dismisses
- **WHEN** all selected tasks are deleted successfully
- **THEN** the toast is green, auto-dismisses after 3 seconds, and does not show a countdown or progress indicator

#### Scenario: Delete with blocked or failed items requires manual dismissal
- **WHEN** a deletion result includes blocked, missing, or failed items
- **THEN** the toast is amber, includes a close button, and remains until the user dismisses it manually

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

### Requirement: Terminal task bulk cleanup
The system SHALL provide a one-click action on the analysis task management page that deletes all failed and canceled analysis tasks in the upload-task list, reusing the existing batch deletion path.

#### Scenario: User clears failed and canceled tasks
- **WHEN** the upload-task list contains at least one task with status `failed` or `canceled`
- **THEN** the clear control is enabled and, after the user confirms, the frontend submits the eligible task ids to the existing batch delete endpoint
- **AND** the frontend reports per-task deletion results using the existing delete feedback summary

#### Scenario: No terminal tasks exist
- **WHEN** the upload-task list contains no tasks with status `failed` or `canceled`
- **THEN** the clear control is disabled or performs no action

#### Scenario: User cancels cleanup confirmation
- **WHEN** the user dismisses the cleanup confirmation dialog
- **THEN** no backend deletion request is made and the task list remains unchanged

#### Scenario: Cleanup has partial results
- **WHEN** a cleanup request includes tasks that are missing or blocked
- **THEN** the frontend reports which tasks were deleted and which require attention

#### Scenario: Cleanup keeps the local fallback store consistent
- **WHEN** a cleanup succeeds through the backend
- **THEN** the frontend removes the same demo tasks from the browser local fallback store so the local list stays consistent

### Requirement: Analysis task list sorting
The system SHALL allow users to sort the upload-task list by creation time or update time, in ascending or descending order, on the analysis task management page.

#### Scenario: User sorts by creation time
- **WHEN** the user selects creation-time ordering on the upload-task list
- **THEN** the list is ordered by task `createdAt`, ascending or descending as chosen

#### Scenario: User sorts by update time
- **WHEN** the user selects update-time ordering on the upload-task list
- **THEN** the list is ordered by task `updatedAt`, falling back to `createdAt` when `updatedAt` is absent, ascending or descending as chosen

#### Scenario: Default ordering matches prior behavior
- **WHEN** the task management page loads with no explicit sort selection
- **THEN** the upload-task list is ordered by update time, newest first, matching the previous list order

#### Scenario: Sorting applies to all data paths
- **WHEN** the task list is sourced either from the backend API or from the browser local fallback store
- **THEN** the same sort logic is applied in both cases so ordering is consistent

### Requirement: Analysis task batch select by analysis mode
The system SHALL provide a "select by analysis mode" entry in the upload-task tab toolbar of the analysis task management page, allowing users to batch-select all eligible (non-active) tasks of a given analysis mode — 样例任务 / 有限真实分析 / 真实视频分析 — into the existing selection set, which is shared with the existing batch deletion flow.

#### Scenario: User opens the mode select popover
- **WHEN** the upload-task tab shows at least one analysis task
- **THEN** the toolbar SHALL expose a "按类型选择" button, and activating it SHALL open a small popover listing the three analysis modes with their eligible (deletable) task counts

#### Scenario: User checks an analysis mode
- **WHEN** the user checks an analysis mode in the popover
- **THEN** all eligible (non-active) tasks of that mode SHALL be added to the selection set
- **AND** the task card checkboxes and the selected-count label SHALL update to reflect the new selection

#### Scenario: User unchecks an analysis mode
- **WHEN** the user unchecks an analysis mode in the popover
- **THEN** all eligible tasks of that mode SHALL be removed from the selection set
- **AND** the task card checkboxes and the selected-count label SHALL update to reflect the new selection

#### Scenario: Mode checkbox shows indeterminate state
- **WHEN** only a proper subset of a mode's eligible tasks is present in the selection set, for example after the user manually adjusted individual cards
- **THEN** the mode checkbox SHALL render an indeterminate (partial) state

#### Scenario: Active tasks are excluded from mode selection
- **WHEN** a mode contains active (queued, uploaded, or processing) tasks
- **THEN** mode-based selection SHALL apply only to eligible tasks
- **AND** active tasks SHALL remain unselected and SHALL NOT be part of any subsequent batch deletion

#### Scenario: User deletes mode-selected tasks
- **WHEN** the user selects tasks via the analysis-mode popover and then confirms the existing batch delete action
- **THEN** the deletion SHALL reuse the existing batch delete endpoint and feedback flow, and the list SHALL refresh with the same per-task result reporting as existing batch deletion

#### Scenario: No deletable tasks in a mode
- **WHEN** a mode has zero eligible (deletable) tasks
- **THEN** its checkbox SHALL be disabled or non-selectable with a zero count, and checking it SHALL have no effect on the selection set

#### Scenario: Popover closes
- **WHEN** the user clicks outside the popover or presses Escape
- **THEN** the popover SHALL close without altering the current selection set

### Requirement: Analysis task list filter by analysis mode
The system SHALL allow users to filter the upload-task list by analysis mode from the same "按类型选择" popover, in addition to batch-selecting tasks.

#### Scenario: User filters the list by a mode
- **WHEN** the user clicks an analysis mode in the popover filter section
- **THEN** the upload-task list SHALL show only tasks of that analysis mode
- **AND** the filter section SHALL mark the active mode

#### Scenario: User returns to the full list
- **WHEN** the user clicks the currently active mode again or clicks "全部"
- **THEN** the upload-task list SHALL show all upload tasks again

#### Scenario: Filter and batch select coexist
- **WHEN** the popover shows both the filter section and the batch-select section
- **THEN** the batch-select checkboxes SHALL remain independent of the active filter and still operate on all eligible tasks

#### Scenario: Select-all follows the filtered list
- **WHEN** a mode filter is active and the user toggles select-all
- **THEN** select-all SHALL apply to the visible eligible tasks of the filtered list
- **AND** the "已选 N 个可删除历史任务" count SHALL reflect the visible eligible tasks

#### Scenario: Active filter is reflected on the trigger button
- **WHEN** a mode filter other than "全部" is active
- **THEN** the trigger button SHALL display the active mode label appended to "按类型选择"
- **AND** the trigger button SHALL render with an active-state style that distinguishes it from the default state

### Requirement: Mode filter survives navigation away and back
The system SHALL keep the active mode filter when the user navigates from the upload-task tab to another page (e.g. an analysis details page) and returns, by persisting it for the duration of the browser session.

#### Scenario: User navigates away and returns
- **WHEN** the user has a non-default mode filter active and navigates to a different route (such as an analysis detail page)
- **AND** the user navigates back to the upload-task tab within the same browser session
- **THEN** the upload-task list SHALL be filtered by the same mode as before navigation
- **AND** the trigger button SHALL still display the active mode label

#### Scenario: Session boundary resets the filter
- **WHEN** the user opens the app in a new browser session
- **THEN** the mode filter SHALL default to "全部" with no persisted state shown

### Requirement: Analysis task inference toggles display
The system SHALL expose the inference toggle states used by each analysis job in its summary and SHALL display them in the task management UI and job detail page.

#### Scenario: Job summary exposes toggle states
- **WHEN** the frontend retrieves an analysis job summary
- **THEN** the summary SHALL include `enableModelInference` and `enablePoseInference` reflecting the values the job was created with

#### Scenario: Legacy jobs have fallback values
- **WHEN** an existing job record predates the toggle fields and lacks them
- **THEN** the summary SHALL fall back to the backend global configuration values rather than failing to render

#### Scenario: Task management page shows toggle states
- **WHEN** the task management page lists analysis jobs
- **THEN** each job card SHALL display the inference toggle states (e.g. a compact badge such as "检测开 / 姿态关")

#### Scenario: Job detail page shows toggle states
- **WHEN** the user opens the job detail page
- **THEN** the task information section SHALL show the human detection and pose estimation toggle states alongside the other task metadata
