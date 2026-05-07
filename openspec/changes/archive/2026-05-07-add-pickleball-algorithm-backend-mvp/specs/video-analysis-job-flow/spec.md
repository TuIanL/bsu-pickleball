## MODIFIED Requirements

### Requirement: Analysis job creation
The system SHALL create an analysis job when the user submits a valid video-analysis request, including either the existing metadata-only demo flow or an uploaded backend video reference.

#### Scenario: User submits a valid request
- **WHEN** the user starts analysis with a selected video and required metadata
- **THEN** the system creates an analysis job with a stable job identifier and routes the user to the job status page

#### Scenario: User submits a backend uploaded video reference
- **WHEN** the user starts analysis with a valid backend video identifier and required metadata
- **THEN** the backend creates an analysis job linked to that video and starts or schedules the MVP analysis pipeline

#### Scenario: Backend is unavailable during submission
- **WHEN** the user submits an analysis request and the backend cannot be reached
- **THEN** the system shows a recoverable error state without losing the selected file and metadata context

### Requirement: Analysis job status page
The system SHALL provide a job-specific page that communicates analysis progress, MVP pipeline stage, and next actions.

#### Scenario: User opens a queued job
- **WHEN** the user navigates to an analysis job that is queued
- **THEN** the system shows a queued status, job metadata, and a message that processing has not started yet

#### Scenario: User opens a processing job
- **WHEN** the user navigates to an analysis job that is processing
- **THEN** the system shows the current processing stage, progress indicator or stage list, and keeps result actions unavailable until completion

#### Scenario: User opens a pipeline-backed processing job
- **WHEN** the user navigates to an analysis job currently running the MVP backend pipeline
- **THEN** the system can display stages for upload, calibration, video read, detection, tracking, projection, metrics, visualization, and report generation when those stages are reported by the backend

#### Scenario: User opens a failed job
- **WHEN** the user navigates to an analysis job that failed
- **THEN** the system shows the failure reason if available and offers a retry or return-to-upload action

#### Scenario: User opens a completed job
- **WHEN** the user navigates to an analysis job that completed successfully
- **THEN** the system shows completion status and provides actions to open the visual analysis workspace and report pages for that job

## ADDED Requirements

### Requirement: Calibration-assisted analysis flow
The system SHALL support manual or semi-manual court calibration data as part of a video analysis workflow.

#### Scenario: User submits calibration before analysis
- **WHEN** the user or developer submits court keypoint correspondences for an uploaded video before creating an analysis job
- **THEN** the backend stores the calibration and allows the analysis job to reference it

#### Scenario: Analysis starts without calibration
- **WHEN** an MVP analysis job starts without a calibration reference
- **THEN** the backend still creates the job and returns a mock or calibration-pending result instead of crashing

### Requirement: Algorithm result retrieval
The system SHALL allow a completed pipeline-backed analysis job to expose its raw algorithm result separately from the frontend report payload.

#### Scenario: Developer requests raw algorithm result
- **WHEN** a developer requests the result for a completed pipeline-backed job
- **THEN** the backend returns structured JSON containing video reference, calibration reference, projected tracks, movement metrics, heatmap data, and output artifact paths where available

#### Scenario: Result is not ready
- **WHEN** a client requests the raw algorithm result before the job is completed
- **THEN** the backend returns the current job status or a clear not-ready response without pretending the result is final
