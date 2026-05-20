## MODIFIED Requirements

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
- **THEN** the system shows completion status and provides actions to open the visual analysis workspace, analysis details page, and task management page

#### Scenario: Pipeline reports tracking progress
- **WHEN** the backend processes a video with player tracking enabled
- **THEN** the reported pipeline stages include progress details derived from upload state, calibration state, processed frame counts, detection counts, projected track counts, generated person or pose overlay artifacts, and generated result artifacts when available

#### Scenario: Pipeline reports pose progress
- **WHEN** the backend processes a video with pose inference enabled
- **THEN** the reported pipeline stages include pose-estimation status, processed subject counts, skeleton artifact availability, or a clear skipped/failed reason

### Requirement: Analysis job result routing
The system SHALL route users from completed tasks and completed job details to job-specific visual analysis, analysis details, and currently supported report views.

#### Scenario: User opens completed visual analysis
- **WHEN** the user selects the visual analysis action for a completed job from task management or the job status detail
- **THEN** the system opens a visual analysis route associated with that job identifier

#### Scenario: User opens completed analysis details
- **WHEN** the user selects the analysis details action for a completed job from task management, job status detail, or visual analysis
- **THEN** the system opens `/analysis/:jobId/details` for that job identifier

#### Scenario: User opens supported completed report type
- **WHEN** the user selects a currently supported report action for a completed job
- **THEN** the system opens the matching report detail route associated with that job identifier and report type

### Requirement: Raw pipeline result consumption
The system SHALL make completed real analysis jobs expose raw MVP pipeline results that the frontend can use to generate user-facing movement, status, and standard-court feedback.

#### Scenario: Frontend requests a completed pipeline result
- **WHEN** the frontend requests the raw result for a completed real analysis job
- **THEN** the backend returns structured JSON containing video reference, calibration reference, stage results, projected tracks, movement metrics, heatmap data, person/pose artifact paths, and a completion message where available

#### Scenario: Frontend requests a result before completion
- **WHEN** the frontend requests raw algorithm output for a queued or processing job
- **THEN** the backend returns the current job status or a clear not-ready response without pretending final algorithm output exists

#### Scenario: Pipeline result is unavailable for a completed job
- **WHEN** a completed job has no raw algorithm result due to storage or processing failure
- **THEN** the frontend shows a stable unavailable-result state or demo/sample distinction instead of broken report modules

### Requirement: Video and overlay artifact retrieval
The system SHALL allow completed real jobs to expose browser-loadable source video and supported overlay artifact references for visual playback.

#### Scenario: Source video is available
- **WHEN** a completed real job references an uploaded `videoId`
- **THEN** the backend exposes a browser-loadable source video URL or stream endpoint for that video

#### Scenario: Overlay artifacts are available
- **WHEN** a completed real job produced detection, tracking, or pose overlay artifacts
- **THEN** the raw pipeline result references those artifacts with browser-loadable URLs or API paths

#### Scenario: Overlay artifacts are unavailable
- **WHEN** model inference was disabled, failed, or produced no supported overlay artifacts
- **THEN** the job result distinguishes no-overlay availability from demo data and keeps result navigation stable

## REMOVED Requirements

### Requirement: Ball tracking pipeline reporting
**Reason**: Ball tracking is intentionally removed from the current real-analysis job flow until a later ball-capture capability is designed and implemented.
**Migration**: The pipeline SHALL omit ball-tracking stages and ball-specific failure/details from active job summaries. Existing player tracking, pose, projection, metrics, visualization, and report stages remain the supported flow.

### Requirement: Raw pipeline result includes ball artifact metadata
**Reason**: Completed raw results should no longer expose ball overlay metadata while ball capture analysis is out of scope.
**Migration**: Clients SHALL ignore any legacy ball artifact metadata in older results and SHALL not fetch or render ball overlay artifacts for current jobs.
