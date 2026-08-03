## MODIFIED Requirements

### Requirement: Analysis task list retrieval
The system SHALL provide a way to retrieve all known durable analysis job summaries from current and previous analysis sessions, and SHALL support filtering by recording session ID.

#### Scenario: Backend lists persisted jobs
- **WHEN** the frontend requests the analysis task list
- **THEN** the backend returns all readable persisted job summaries plus active job summaries, sorted by most recent update or creation time first

#### Scenario: Backend filters by recording session
- **WHEN** the frontend requests `GET /api/analysis/jobs?recording_session_id=<sid>`
- **THEN** the backend SHALL return only jobs whose `metadata.recording_session_id` matches `<sid>`
- **AND** if no matching jobs exist, SHALL return an empty list

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
The system SHALL provide an analysis task management page that shows all historical and current video analysis tasks with clear orchestration-aware status labels, and SHALL expose recording session origin where applicable.

#### Scenario: User opens task management page
- **WHEN** the user navigates to the analysis task management route
- **THEN** the page lists analysis tasks with match title, uploaded file label, creation or update time, progress, current stage, and a status label such as queued, running, succeeded, failed, canceled, or compatible display labels
- **AND** tasks created from a recording SHALL display a "来源录制" label linking to the recording session

#### Scenario: User has no tasks
- **WHEN** the user opens the task management page before any analysis task exists
- **THEN** the page shows an empty state with a clear action to upload a match video

#### Scenario: Task list cannot load
- **WHEN** the backend task list request fails
- **THEN** the page shows a stable recoverable error state and keeps upload access available

#### Scenario: Task has stage telemetry
- **WHEN** a task includes stage timing, error code, retry count, or cancellation context
- **THEN** the page exposes the most useful user-facing fields without showing internal stack traces or sensitive local paths

## ADDED Requirements

### Requirement: Analysis task creation supports recording origin
The system SHALL allow analysis tasks to be created with recording session origin metadata, preserving the contract that fields inherited from the recording are immutable through the analysis lifecycle.

#### Scenario: Task created from recording session
- **WHEN** `POST /api/analysis/jobs` receives `{ recording_session_id: "<sid>", camera_slot: "cam_1" }`
- **THEN** the resulting `AnalysisJobSummary` SHALL include `recordingSessionId` and `cameraSlot` fields
- **AND** `AnalysisUploadMetadata` SHALL snapshot the recording's court name, match date, fps, match format, and camera angle as immutable values

#### Scenario: Task created without recording origin
- **WHEN** `POST /api/analysis/jobs` does not include `recording_session_id`
- **THEN** the task SHALL be treated as a standalone upload—behavior unchanged from current version
