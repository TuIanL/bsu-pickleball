## MODIFIED Requirements

### Requirement: Algorithm result retrieval
The system SHALL allow a completed pipeline-backed analysis job to expose its raw algorithm result separately from the frontend report payload, including tracking artifacts when real video tracking was executed.

#### Scenario: Developer requests raw algorithm result
- **WHEN** a developer requests the result for a completed pipeline-backed job
- **THEN** the backend returns structured JSON containing video reference, calibration reference, projected tracks, movement metrics, heatmap data, tracking metadata, and output artifact paths where available

#### Scenario: Result is not ready
- **WHEN** a client requests the raw algorithm result before the job is completed
- **THEN** the backend returns the current job status or a clear not-ready response without pretending the result is final

#### Scenario: Tracking artifact is available
- **WHEN** a completed job processed video frames with a valid calibration
- **THEN** the raw algorithm result includes or references a persisted `tracking_result.json` artifact containing frame timing metadata and player positions

### Requirement: Calibration-assisted analysis flow
The system SHALL support manual or semi-manual court calibration data as part of a video analysis workflow and use available calibration to project tracked player footpoints into court coordinates.

#### Scenario: User submits calibration before analysis
- **WHEN** the user or developer submits court keypoint correspondences for an uploaded video before creating an analysis job
- **THEN** the backend stores the calibration and allows the analysis job to reference it

#### Scenario: Analysis starts without calibration
- **WHEN** an MVP analysis job starts without a calibration reference
- **THEN** the backend still creates the job and returns a mock, empty-tracks, or calibration-pending result instead of crashing

#### Scenario: Analysis starts with video and calibration
- **WHEN** an analysis job starts with a readable uploaded video and a valid calibration homography
- **THEN** the backend runs player detection, tracking, footpoint estimation, court projection, and metrics stages using the calibration-derived court coordinates

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

#### Scenario: Pipeline reports tracking progress
- **WHEN** the backend processes a video with player tracking enabled
- **THEN** the reported pipeline stages can include detection, tracking, projection, and progress details derived from processed frame counts
