## MODIFIED Requirements

### Requirement: Analysis job creation
The system SHALL create a real analysis job by uploading the selected video to the backend, linking the returned backend video identifier to the job request, persisting a durable queued job record, and reserving metadata-only jobs for explicit demo or developer flows.

#### Scenario: User submits a valid real upload request
- **WHEN** the user starts analysis with a selected video and required metadata
- **THEN** the frontend uploads the video file to the backend video upload API, creates an analysis job with the returned `videoId`, and routes the user to the analysis task management page with the new task visible

#### Scenario: User submits a calibrated backend video reference
- **WHEN** the user starts analysis with a valid backend video identifier, calibration identifier, and required metadata
- **THEN** the backend creates a durable queued analysis job linked to that video and calibration and schedules the MVP analysis pipeline for worker execution

#### Scenario: Duplicate real submission is detected
- **WHEN** the user submits the same video, calibration, and analysis configuration without requesting a new analysis version
- **THEN** the backend returns or references the existing matching queued, running, or succeeded job instead of starting duplicate pipeline work

#### Scenario: Backend is unavailable during real upload submission
- **WHEN** the user submits an analysis request and the backend cannot upload the file or create the job
- **THEN** the system shows a recoverable error state without losing the selected file and metadata context and does not silently create a successful mock job

#### Scenario: Developer submits a metadata-only demo request
- **WHEN** a developer or explicit sample mode creates an analysis job without a backend video identifier
- **THEN** the backend may return a demo-compatible job response that is distinguishable from a real uploaded-video analysis

### Requirement: Analysis job status page
The system SHALL provide a job-specific page that communicates orchestration-aware analysis progress, MVP pipeline stage telemetry, model-backed detection and pose stages, cancellation state, and next actions within the task-centered workflow.

#### Scenario: User opens a queued job
- **WHEN** the user navigates to an analysis job that is queued
- **THEN** the system shows a queued status, job metadata, queue timing, a message that processing has not started yet, a cancellation action when allowed, and a way back to task management

#### Scenario: User opens a running job
- **WHEN** the user navigates to an analysis job that is running or displayed as processing
- **THEN** the system shows the current processing stage, progress indicator, stage list, stage timing when available, cancellation action when allowed, polls for updates, and keeps result actions unavailable until completion

#### Scenario: User opens a pipeline-backed processing job
- **WHEN** the user navigates to an analysis job currently running the MVP backend pipeline
- **THEN** the system displays stages for upload, calibration, video read, detection, tracking, pose estimation, projection, metrics, visualization, and report generation when those stages are reported by the backend

#### Scenario: User opens a failed job
- **WHEN** the user navigates to an analysis job that failed
- **THEN** the system shows the user-facing failure reason and stable error code when available and offers a retry, return-to-upload, or return-to-task-management action

#### Scenario: User opens a canceled job
- **WHEN** the user navigates to an analysis job that was canceled
- **THEN** the system shows a stable canceled state, cancellation timing when available, and actions to start a new upload or return to task management

#### Scenario: User opens a completed job
- **WHEN** the user navigates to an analysis job that completed successfully
- **THEN** the system shows completion status and provides actions to open the visual analysis workspace, analysis details page, and task management page

#### Scenario: Pipeline reports tracking progress
- **WHEN** the backend processes a video with player tracking enabled
- **THEN** the reported pipeline stages include progress details derived from upload state, calibration state, processed frame counts, detection counts, projected track counts, generated person or pose overlay artifacts, stage timestamps, durations, and generated result artifacts when available

#### Scenario: Pipeline reports pose progress
- **WHEN** the backend processes a video with pose inference enabled
- **THEN** the reported pipeline stages include pose-estimation status, processed subject counts, skeleton artifact availability, stage timing, retry or skip context, or a clear skipped/failed reason

## ADDED Requirements

### Requirement: Analysis job cancellation flow
The system SHALL allow users to request cancellation for queued or running real analysis jobs from job-aware status surfaces.

#### Scenario: User cancels a queued job
- **WHEN** the user requests cancellation for a queued analysis job
- **THEN** the backend accepts the cancellation, marks the job as canceled without running the pipeline, and the frontend updates the job status

#### Scenario: User cancels a running job
- **WHEN** the user requests cancellation for a running analysis job
- **THEN** the backend records the cancellation request and the frontend shows cancellation pending or canceled status based on the latest job telemetry

#### Scenario: User cannot cancel terminal job
- **WHEN** the user attempts to cancel a succeeded, failed, or already canceled job
- **THEN** the system prevents or rejects the action without deleting artifacts or altering terminal results
