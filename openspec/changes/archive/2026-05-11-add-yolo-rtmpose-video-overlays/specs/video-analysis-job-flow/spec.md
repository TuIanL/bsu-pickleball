## MODIFIED Requirements

### Requirement: Analysis job status page
The system SHALL provide a job-specific page that communicates analysis progress, MVP pipeline stage, model-backed detection and pose stages, and next actions.

#### Scenario: User opens a queued job
- **WHEN** the user navigates to an analysis job that is queued
- **THEN** the system shows a queued status, job metadata, and a message that processing has not started yet

#### Scenario: User opens a processing job
- **WHEN** the user navigates to an analysis job that is processing
- **THEN** the system shows the current processing stage, progress indicator or stage list, polls for updates, and keeps result actions unavailable until completion

#### Scenario: User opens a pipeline-backed processing job
- **WHEN** the user navigates to an analysis job currently running the MVP backend pipeline
- **THEN** the system displays stages for upload, calibration, video read, detection, tracking, pose estimation, projection, metrics, visualization, and report generation when those stages are reported by the backend

#### Scenario: User opens a failed job
- **WHEN** the user navigates to an analysis job that failed
- **THEN** the system shows the failure reason if available and offers a retry or return-to-upload action

#### Scenario: User opens a completed job
- **WHEN** the user navigates to an analysis job that completed successfully
- **THEN** the system shows completion status and provides actions to open the visual analysis workspace and report pages for that job

#### Scenario: Pipeline reports tracking progress
- **WHEN** the backend processes a video with player tracking enabled
- **THEN** the reported pipeline stages include progress details derived from upload state, calibration state, processed frame counts, detection counts, projected track counts, generated overlay artifacts, and generated result artifacts when available

#### Scenario: Pipeline reports pose progress
- **WHEN** the backend processes a video with pose inference enabled
- **THEN** the reported pipeline stages include pose-estimation status, processed subject counts, skeleton artifact availability, or a clear skipped/failed reason

## ADDED Requirements

### Requirement: Video and overlay artifact retrieval
The system SHALL allow completed real jobs to expose browser-loadable source video and overlay artifact references for visual playback.

#### Scenario: Source video is available
- **WHEN** a completed real job references an uploaded `videoId`
- **THEN** the backend exposes a browser-loadable source video URL or stream endpoint for that video

#### Scenario: Overlay artifacts are available
- **WHEN** a completed real job produced detection, tracking, or pose overlay artifacts
- **THEN** the raw pipeline result references those artifacts with browser-loadable URLs or API paths

#### Scenario: Overlay artifacts are unavailable
- **WHEN** model inference was disabled, failed, or produced no overlay artifacts
- **THEN** the job result distinguishes no-overlay availability from demo data and keeps report navigation stable

### Requirement: Pose-aware raw pipeline result
The system SHALL include pose overlay availability in completed real analysis results.

#### Scenario: Pose artifact exists
- **WHEN** the frontend requests raw output for a completed job with RTMPose results
- **THEN** the result includes pose artifact metadata, stage status, and enough source video metadata to align keypoints to the video frame

#### Scenario: Detection exists without pose
- **WHEN** a completed job has YOLO detections but no RTMPose skeletons
- **THEN** the result allows the frontend to render person boxes and label skeleton overlay as unavailable
