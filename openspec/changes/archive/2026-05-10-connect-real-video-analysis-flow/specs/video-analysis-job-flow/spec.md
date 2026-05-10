## MODIFIED Requirements

### Requirement: Analysis job creation
The system SHALL create a real analysis job by uploading the selected video to the backend, linking the returned backend video identifier to the job request, and reserving metadata-only jobs for explicit demo or developer flows.

#### Scenario: User submits a valid real upload request
- **WHEN** the user starts analysis with a selected video and required metadata
- **THEN** the frontend uploads the video file to the backend video upload API, creates an analysis job with the returned `videoId`, and routes the user to the job status page

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
The system SHALL provide a job-specific page that communicates analysis progress, MVP pipeline stage, and next actions.

#### Scenario: User opens a queued job
- **WHEN** the user navigates to an analysis job that is queued
- **THEN** the system shows a queued status, job metadata, and a message that processing has not started yet

#### Scenario: User opens a processing job
- **WHEN** the user navigates to an analysis job that is processing
- **THEN** the system shows the current processing stage, progress indicator or stage list, polls for updates, and keeps result actions unavailable until completion

#### Scenario: User opens a pipeline-backed processing job
- **WHEN** the user navigates to an analysis job currently running the MVP backend pipeline
- **THEN** the system displays stages for upload, calibration, video read, detection, tracking, projection, metrics, visualization, and report generation when those stages are reported by the backend

#### Scenario: User opens a failed job
- **WHEN** the user navigates to an analysis job that failed
- **THEN** the system shows the failure reason if available and offers a retry or return-to-upload action

#### Scenario: User opens a completed job
- **WHEN** the user navigates to an analysis job that completed successfully
- **THEN** the system shows completion status and provides actions to open the visual analysis workspace and report pages for that job

#### Scenario: Pipeline reports tracking progress
- **WHEN** the backend processes a video with player tracking enabled
- **THEN** the reported pipeline stages include progress details derived from upload state, calibration state, processed frame counts, detection counts, projected track counts, and generated result artifacts when available

## ADDED Requirements

### Requirement: User-facing calibration handoff
The system SHALL provide a lightweight calibration handoff for real uploaded video analysis so player positions can be projected into court coordinates.

#### Scenario: User marks four court corners
- **WHEN** the selected video is ready for real analysis and the user marks top-left, top-right, bottom-right, and bottom-left court corners on a representative frame
- **THEN** the frontend submits those image points with the backend video identifier and stores the returned calibration identifier for job creation

#### Scenario: Calibration cannot be created
- **WHEN** the calibration request is rejected or cannot compute a valid homography
- **THEN** the system keeps the user in the upload/calibration workflow with a clear error and does not start a full real analysis job

#### Scenario: User skips calibration
- **WHEN** the user chooses to start without calibration if that option is available
- **THEN** the resulting job is labeled as limited analysis and MUST NOT present court-projected movement metrics as if calibration was available

### Requirement: Raw pipeline result consumption
The system SHALL make completed real analysis jobs expose raw MVP pipeline results that the frontend can use to generate user-facing feedback.

#### Scenario: Frontend requests a completed pipeline result
- **WHEN** the frontend requests the raw result for a completed real analysis job
- **THEN** the backend returns structured JSON containing video reference, calibration reference, stage results, projected tracks, movement metrics, heatmap data, artifact paths, and a completion message where available

#### Scenario: Frontend requests a result before completion
- **WHEN** the frontend requests raw algorithm output for a queued or processing job
- **THEN** the backend returns the current job status or a clear not-ready response without pretending final algorithm output exists

#### Scenario: Pipeline result is unavailable for a completed job
- **WHEN** a completed job has no raw algorithm result due to storage or processing failure
- **THEN** the frontend shows a stable unavailable-result state or demo/sample distinction instead of broken report modules
