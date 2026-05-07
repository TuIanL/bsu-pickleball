## ADDED Requirements

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
The system SHALL create an analysis job when the user submits a valid video-analysis request.

#### Scenario: User submits a valid request
- **WHEN** the user starts analysis with a selected video and required metadata
- **THEN** the system creates an analysis job with a stable job identifier and routes the user to the job status page

#### Scenario: Backend is unavailable during submission
- **WHEN** the user submits an analysis request and the backend cannot be reached
- **THEN** the system shows a recoverable error state without losing the selected file and metadata context

### Requirement: Analysis job status page
The system SHALL provide a job-specific page that communicates analysis progress and next actions.

#### Scenario: User opens a queued job
- **WHEN** the user navigates to an analysis job that is queued
- **THEN** the system shows a queued status, job metadata, and a message that processing has not started yet

#### Scenario: User opens a processing job
- **WHEN** the user navigates to an analysis job that is processing
- **THEN** the system shows the current processing stage, progress indicator or stage list, and keeps result actions unavailable until completion

#### Scenario: User opens a failed job
- **WHEN** the user navigates to an analysis job that failed
- **THEN** the system shows the failure reason if available and offers a retry or return-to-upload action

#### Scenario: User opens a completed job
- **WHEN** the user navigates to an analysis job that completed successfully
- **THEN** the system shows completion status and provides actions to open the visual analysis workspace and report pages for that job

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
