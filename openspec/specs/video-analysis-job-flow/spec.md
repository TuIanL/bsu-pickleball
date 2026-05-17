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

### Requirement: True-model pose artifact reporting
The system SHALL distinguish true RTMPose model output from unavailable, skipped, injected-test, or placeholder pose states in completed real analysis results.

#### Scenario: True RTMPose pose artifact is available
- **WHEN** a completed calibrated real analysis job runs with RTMPose inference enabled, supported model assets configured, and at least one frame producing valid skeleton keypoints
- **THEN** the raw pipeline result includes a done pose stage, `pose_overlay_status` of `available`, a retrievable `pose_overlay_url`, and detail text derived from generated subject/keypoint counts

#### Scenario: RTMPose runtime or assets are unavailable
- **WHEN** a completed real analysis job cannot run RTMPose because dependencies, config, checkpoint, or device setup is unavailable
- **THEN** the raw pipeline result exposes a skipped or unavailable pose stage with a clear diagnostic and omits any available pose overlay URL

#### Scenario: Detection exists without usable pose
- **WHEN** a completed real analysis job produces player boxes but RTMPose returns no usable skeleton keypoints
- **THEN** the raw pipeline result keeps tracking artifacts available and labels the pose overlay as no-pose or unavailable without failing the entire analysis

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

### Requirement: Automatic calibration suggestion handoff
The system SHALL allow the video upload calibration step to request and review an automatic court calibration suggestion before creating a real analysis job.

#### Scenario: User requests automatic calibration after upload
- **WHEN** the user has uploaded a readable video and selects automatic court calibration
- **THEN** the frontend requests an automatic calibration suggestion for the uploaded video and presents the returned status, confidence, keypoints, and preview when available

#### Scenario: User accepts automatic calibration
- **WHEN** an automatic calibration suggestion passes backend validation and the user accepts it
- **THEN** the frontend stores the returned calibration identifier and creates the real analysis job with that calibration identifier

#### Scenario: User corrects automatic keypoints
- **WHEN** an automatic calibration suggestion is visible but one or more points need adjustment
- **THEN** the frontend lets the user submit corrected keypoints through the calibration handoff before creating the real analysis job

#### Scenario: Automatic calibration is unavailable or rejected
- **WHEN** the automatic calibration request fails, the model is unavailable, or the backend rejects the detected geometry
- **THEN** the workflow keeps manual calibration and limited-analysis fallback choices available without losing the uploaded video or match metadata
