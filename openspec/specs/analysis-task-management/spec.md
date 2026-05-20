# analysis-task-management Specification

## Purpose
TBD - created by archiving change rework-video-analysis-task-flow. Update Purpose after archive.
## Requirements
### Requirement: Analysis task list retrieval
The system SHALL provide a way to retrieve all known analysis job summaries from current and previous analysis sessions.

#### Scenario: Backend lists persisted jobs
- **WHEN** the frontend requests the analysis task list
- **THEN** the backend returns all readable persisted job summaries plus active in-memory job summaries, sorted by most recent update or creation time first

#### Scenario: No analysis jobs exist
- **WHEN** the frontend requests the analysis task list and no jobs have been created
- **THEN** the backend returns an empty list rather than an error

#### Scenario: Persisted job record is unreadable
- **WHEN** one persisted job summary cannot be parsed
- **THEN** the backend skips or isolates that record without preventing the remaining valid jobs from being listed

### Requirement: Analysis task management page
The system SHALL provide an analysis task management page that shows all historical and current video analysis tasks with clear status labels.

#### Scenario: User opens task management page
- **WHEN** the user navigates to the analysis task management route
- **THEN** the page lists analysis tasks with match title, uploaded file label, creation or update time, progress, and a status label such as queued, processing, completed, or failed

#### Scenario: User has no tasks
- **WHEN** the user opens the task management page before any analysis task exists
- **THEN** the page shows an empty state with a clear action to upload a match video

#### Scenario: Task list cannot load
- **WHEN** the backend task list request fails
- **THEN** the page shows a stable recoverable error state and keeps upload access available

### Requirement: Task status actions
The system SHALL expose task actions according to each analysis task's current status.

#### Scenario: Completed task is visible
- **WHEN** a task has status `completed`
- **THEN** the task row or card provides a primary action to view the video analysis result and secondary access to available report types

#### Scenario: Processing task is visible
- **WHEN** a task has status `queued`, `uploaded`, or `processing`
- **THEN** the task row or card shows progress and links to the job status detail instead of enabling completed-result actions

#### Scenario: Failed task is visible
- **WHEN** a task has status `failed`
- **THEN** the task row or card shows failure context when available and provides actions to inspect the task detail or start a new upload

### Requirement: Task list refresh
The system SHALL keep active analysis tasks reasonably current while the user is viewing task management.

#### Scenario: Active task is listed
- **WHEN** the task management page contains a queued, uploaded, or processing task
- **THEN** the frontend refreshes the task list or affected task summaries until no active tasks remain

#### Scenario: User manually refreshes tasks
- **WHEN** the user activates a refresh control on the task management page
- **THEN** the frontend reloads task summaries and preserves stable navigation and scroll behavior

