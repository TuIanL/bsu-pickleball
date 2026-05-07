## MODIFIED Requirements

### Requirement: Python backend project foundation
The system SHALL include a Python backend project area dedicated to video analysis APIs, MVP computer-vision algorithms, and future model-backed analysis.

#### Scenario: Developer inspects backend structure
- **WHEN** a developer opens the backend project area
- **THEN** the system provides an API entrypoint, route modules, schema modules, service modules, core configuration modules, and concrete MVP vision algorithm modules

#### Scenario: Developer inspects backend environment files
- **WHEN** a developer reviews backend setup documentation or metadata
- **THEN** the system identifies the lightweight Python API dependencies separately from optional heavy vision-model dependencies

#### Scenario: Developer inspects algorithm engine boundaries
- **WHEN** a developer opens the backend vision module structure
- **THEN** the system provides clear package boundaries for CourtVision Calibration Engine, Player Tracking Engine, and Pickleball Performance Engine

### Requirement: Analysis API endpoints
The backend SHALL expose API boundaries for video upload, manual calibration, analysis job creation, job status retrieval, algorithm result retrieval, and analysis report retrieval.

#### Scenario: Client uploads a video
- **WHEN** the client submits a valid multipart video upload to the backend API
- **THEN** the backend returns a stable video identifier and basic uploaded video metadata

#### Scenario: Client creates an analysis job
- **WHEN** the frontend submits a valid analysis request to the backend API
- **THEN** the backend returns a stable job identifier and initial job status

#### Scenario: Client requests job status
- **WHEN** the frontend requests the status for an existing analysis job
- **THEN** the backend returns job metadata, current status, current stage, and completion or error information when available

#### Scenario: Client requests algorithm result
- **WHEN** the frontend or developer requests the algorithm result for a completed analysis job
- **THEN** the backend returns a structured JSON payload with pipeline stages, calibration reference when available, projected movement tracks, metrics, and output artifact references

#### Scenario: Client requests completed report
- **WHEN** the frontend requests the report for a completed analysis job
- **THEN** the backend returns an analysis report payload matching the shared report contract

#### Scenario: Client requests missing job
- **WHEN** the frontend requests status, algorithm result, or report data for an unknown job identifier
- **THEN** the backend returns a clear not-found response that the frontend can render as a stable error state

### Requirement: Algorithm adapter boundaries
The backend SHALL reserve replaceable adapter boundaries for detector, tracker, court calibration, projection, metrics, and future event analysis modules while providing MVP implementations for geometry, homography, footpoint projection, and movement metrics.

#### Scenario: Developer inspects vision modules
- **WHEN** a developer opens the backend vision module structure
- **THEN** the system provides separate areas or interfaces for detection, tracking, footpoint estimation, court calibration, court projection, movement metrics, zone metrics, doubles spacing, heatmaps, and future event analysis

#### Scenario: Future YOLO adapter is added
- **WHEN** a YOLOv8n or YOLO11n style detector is integrated later
- **THEN** it can produce normalized person detections without changing frontend routes, analysis job schemas, or report rendering components

#### Scenario: Future tracker adapter is added
- **WHEN** a ByteTrack or BoT-SORT tracker is integrated later
- **THEN** it can produce normalized track points without changing metric computation or analysis API response schemas

#### Scenario: Future pose adapter is added
- **WHEN** an RTMPose26-style pose estimator is integrated later
- **THEN** it can produce normalized pose keypoints or pose-derived features without changing frontend routes or report rendering components

### Requirement: Local storage conventions
The backend SHALL document and use local storage conventions for uploaded videos, calibration files, generated JSON results, visualized output videos, temporary processing files, and model weights.

#### Scenario: Developer reviews storage paths
- **WHEN** a developer reviews backend storage documentation or configuration
- **THEN** the system identifies where uploads, calibrations, generated outputs, temporary files, and model weights are expected to live

#### Scenario: Large generated assets exist locally
- **WHEN** uploaded videos, generated reports, temporary frames, model checkpoints, visualized videos, or training datasets are present in local storage
- **THEN** those files are excluded from version control by documented ignore rules or storage guidance
