## MODIFIED Requirements

### Requirement: New video analysis entry
The system SHALL provide a user-facing entry point for starting a new pickleball video analysis.

#### Scenario: User opens the new analysis page
- **WHEN** the user navigates to the new analysis or upload route
- **THEN** the system displays a video upload workflow with match metadata fields, calibration guidance, a clear action to start analysis, and access to analysis task history

#### Scenario: User accesses upload from primary navigation
- **WHEN** the user selects the video analysis action from the app shell
- **THEN** the system opens the new analysis workflow instead of showing the completed-result workspace or a static demo report

### Requirement: Analysis job creation
The system SHALL create a real analysis job by uploading the selected video to the backend, linking the returned backend video identifier to the job request, and reserving metadata-only jobs for explicit demo or developer flows.

#### Scenario: User submits a valid real upload request
- **WHEN** the user starts analysis with a selected video and required metadata
- **THEN** the frontend uploads the video file to the backend video upload API, creates an analysis job with the returned `videoId`, and routes the user to the analysis task management page with the new task visible

#### Scenario: User submits a calibrated backend video reference
- **WHEN** the user starts analysis with a valid backend video identifier, calibration identifier, and required metadata
- **THEN** the backend creates an analysis job linked to that video and calibration and starts or schedules the MVP analysis pipeline

#### Scenario: Backend is unavailable during real upload submission
- **WHEN** the user submits an analysis request and the backend cannot upload the file or create the job
- **THEN** the system shows a recoverable error state without losing the selected file and metadata context and does not silently create a successful mock job

#### Scenario: Developer submits a metadata-only demo request
- **WHEN** a developer or explicit sample mode creates an analysis job without a backend video identifier
- **THEN** the backend may return a demo-compatible job response that is distinguishable from a real uploaded-video analysis

### Requirement: Analysis job status page
The system SHALL provide a job-specific page that communicates analysis progress, MVP pipeline stage, model-backed detection and pose stages, and next actions within the task-centered workflow.

#### Scenario: User opens a queued job
- **WHEN** the user navigates to an analysis job that is queued
- **THEN** the system shows a queued status, job metadata, a message that processing has not started yet, and a way back to task management

#### Scenario: User opens a processing job
- **WHEN** the user navigates to an analysis job that is processing
- **THEN** the system shows the current processing stage, progress indicator or stage list, polls for updates, and keeps result actions unavailable until completion

#### Scenario: User opens a pipeline-backed processing job
- **WHEN** the user navigates to an analysis job currently running the MVP backend pipeline
- **THEN** the system displays stages for upload, calibration, video read, detection, tracking, pose estimation, projection, metrics, visualization, and report generation when those stages are reported by the backend

#### Scenario: User opens a failed job
- **WHEN** the user navigates to an analysis job that failed
- **THEN** the system shows the failure reason if available and offers a retry, return-to-upload, or return-to-task-management action

#### Scenario: User opens a completed job
- **WHEN** the user navigates to an analysis job that completed successfully
- **THEN** the system shows completion status and provides actions to open the visual analysis workspace, report pages for that job, and the task management page

#### Scenario: Pipeline reports tracking progress
- **WHEN** the backend processes a video with player tracking enabled
- **THEN** the reported pipeline stages include progress details derived from upload state, calibration state, processed frame counts, detection counts, projected track counts, generated overlay artifacts, and generated result artifacts when available

#### Scenario: Pipeline reports pose progress
- **WHEN** the backend processes a video with pose inference enabled
- **THEN** the reported pipeline stages include pose-estimation status, processed subject counts, skeleton artifact availability, or a clear skipped/failed reason

### Requirement: Analysis job result routing
The system SHALL route users from completed tasks and completed job details to job-specific visual analysis and report views.

#### Scenario: User opens completed visual analysis
- **WHEN** the user selects the visual analysis action for a completed job from task management or the job status detail
- **THEN** the system opens a visual analysis route associated with that job identifier

#### Scenario: User opens completed report type
- **WHEN** the user selects landing, movement, rally, or diagnosis report actions for a completed job
- **THEN** the system opens the matching report detail route associated with that job identifier and report type
