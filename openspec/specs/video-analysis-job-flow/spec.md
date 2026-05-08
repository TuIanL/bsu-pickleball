# video-analysis-job-flow Specification

## Purpose
TBD - created by archiving change add-analysis-workflow-backend-foundation. Update Purpose after archive.
## Requirements
### Requirement: New video analysis entry
The system SHALL provide a user-facing entry point for starting a new pickleball video analysis.

#### Scenario: User opens the new analysis page
- **WHEN** the user navigates to the new analysis or upload route
- **THEN** the system displays a video upload workflow with match metadata fields and a clear action to start analysis

#### Scenario: User accesses upload from primary navigation
- **WHEN** the user selects the primary analysis or upload action from the app shell
- **THEN** the system opens the new analysis workflow instead of only showing a static demo report

### Requirement: Video upload form states
The system SHALL guide users through valid video selection and required match context before creating an analysis job.

#### Scenario: User selects a supported video
- **WHEN** the user chooses a supported local video file
- **THEN** the system shows the selected file name, size or duration placeholder, and enables analysis submission when required metadata is complete

#### Scenario: User has incomplete upload input
- **WHEN** no video file is selected or required metadata is missing
- **THEN** the system keeps the start-analysis action disabled or presents a clear validation message

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

#### Scenario: Pipeline reports tracking progress
- **WHEN** the backend processes a video with player tracking enabled
- **THEN** the reported pipeline stages can include detection, tracking, projection, and progress details derived from processed frame counts

### Requirement: Analysis job result routing
The system SHALL route users from a completed job to job-specific visual analysis and report views.

#### Scenario: User opens completed visual analysis
- **WHEN** the user selects the visual analysis action for a completed job
- **THEN** the system opens a visual analysis route associated with that job identifier

#### Scenario: User opens completed report type
- **WHEN** the user selects landing, movement, rally, or diagnosis report actions for a completed job
- **THEN** the system opens the matching report detail route associated with that job identifier and report type

### Requirement: Demo fallback for analysis flow
The system SHALL preserve a demo path when no backend job is available.

#### Scenario: User views demo analysis without a job
- **WHEN** the user opens the existing demo visual analysis or sample report route
- **THEN** the system continues to render the structured local demo data without requiring a backend

#### Scenario: Job result cannot be loaded
- **WHEN** a job-specific result route cannot load report data
- **THEN** the system shows a stable error or fallback state rather than rendering a broken visualization

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

