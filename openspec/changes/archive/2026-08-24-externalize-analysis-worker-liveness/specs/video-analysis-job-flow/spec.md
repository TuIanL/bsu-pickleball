## MODIFIED Requirements

### Requirement: Analysis job status page

The system SHALL provide a job-specific page that communicates queued, running, succeeded, failed, canceled, and interrupted analysis states. The page SHALL show current stage telemetry while a Worker lease is healthy and SHALL present an interrupted task as a recoverable “任务失联” state rather than an endlessly processing job.

#### Scenario: User opens a queued job

- **WHEN** the user navigates to an analysis job that is queued
- **THEN** the system shows queued status, job metadata, queue timing, a message that processing has not started yet, a cancellation action when allowed, and a way back to task management

#### Scenario: User opens a running job with fresh heartbeat

- **WHEN** the user navigates to a job whose status is running or compatible processing and whose Worker heartbeat is fresh
- **THEN** the system shows the current processing stage, stage stepper, progress percentage, Worker/heartbeat freshness when available, cancellation action when allowed, and polls for updates
- **AND** result actions remain unavailable until completion

#### Scenario: User opens an interrupted job

- **WHEN** the user navigates to a job whose durable status is `interrupted`
- **THEN** the page shows the prominent status “任务失联”
- **AND** shows the last known stage/progress, interruption time or last heartbeat when available, and a user-safe explanation
- **AND** stops treating the job as active processing and offers explicit re-analysis/retry, task management and deletion actions

#### Scenario: User views the horizontal stage stepper

- **WHEN** the user views a non-terminal analysis job with multiple reported stages
- **THEN** the system renders stages as a horizontally scrollable row with completed, active, failed, skipped and pending visual states
- **AND** an interrupted job preserves the last known stage state without showing a misleading active heartbeat indicator

#### Scenario: User opens a terminal job with collapsed progress

- **WHEN** the user navigates to a completed, failed, canceled, or interrupted job
- **THEN** the progress area collapses to a one-line summary or interruption summary
- **AND** result or recovery actions become the primary content of the page

#### Scenario: User opens a failed job

- **WHEN** the user navigates to an analysis job that failed
- **THEN** the system shows the user-facing failure reason and stable error code when available and offers a retry, return-to-upload, or return-to-task-management action

#### Scenario: User opens a canceled job

- **WHEN** the user navigates to an analysis job that was canceled
- **THEN** the system shows a stable canceled state, cancellation timing when available, and actions to start a new upload or return to task management

#### Scenario: User opens a completed job

- **WHEN** the user navigates to an analysis job that completed successfully
- **THEN** the system shows completion status and provides actions to open the visual analysis workspace, analysis details page, and task management page

#### Scenario: User views a multiview parent job

- **WHEN** the user navigates to a multiview job that exposes `viewRuns`
- **THEN** the page shows A/B per-view progress inside the progress area
- **AND** an interrupted child or Parent is represented by a stable lost/interrupted status rather than an indefinitely running view

### Requirement: Analysis job result routing

The system SHALL route users from successfully completed tasks to job-specific result views. Interrupted tasks SHALL NOT expose completed-result actions solely because partial artifacts exist.

#### Scenario: User opens completed visual analysis

- **WHEN** the user selects the visual analysis action for a completed job
- **THEN** the system opens a visual analysis route associated with that job identifier

#### Scenario: User opens interrupted job result

- **WHEN** the user requests a result route for an interrupted job
- **THEN** the system shows the interrupted recovery state or a clear not-ready response
- **AND** SHALL NOT present partial artifacts as a completed analysis result
