# python-vision-backend-foundation Specification

## Purpose
TBD - created by archiving change add-analysis-workflow-backend-foundation. Update Purpose after archive.
## Requirements
### Requirement: Python backend project foundation
The system SHALL include a Python backend project area dedicated to video analysis APIs and future computer-vision algorithms.

#### Scenario: Developer inspects backend structure
- **WHEN** a developer opens the backend project area
- **THEN** the system provides an API entrypoint, route modules, schema modules, service modules, and reserved vision algorithm modules

#### Scenario: Developer inspects backend environment files
- **WHEN** a developer reviews backend setup documentation or metadata
- **THEN** the system identifies the lightweight Python API dependencies separately from optional heavy vision-model dependencies

### Requirement: Analysis API endpoints
The backend SHALL expose API boundaries for video upload, analysis job creation, job status retrieval, and analysis report retrieval.

#### Scenario: Client creates an analysis job
- **WHEN** the frontend submits a valid analysis request to the backend API
- **THEN** the backend returns a stable job identifier and initial job status

#### Scenario: Client requests job status
- **WHEN** the frontend requests the status for an existing analysis job
- **THEN** the backend returns job metadata, current status, current stage, and completion or error information when available

#### Scenario: Client requests completed report
- **WHEN** the frontend requests the report for a completed analysis job
- **THEN** the backend returns an analysis report payload matching the shared report contract

#### Scenario: Client requests missing job
- **WHEN** the frontend requests status or report data for an unknown job identifier
- **THEN** the backend returns a clear not-found response that the frontend can render as a stable error state

### Requirement: Analysis report schema
The backend SHALL define a structured analysis report schema that can feed the existing visual analysis workspace and report detail views.

#### Scenario: Mock report is generated
- **WHEN** the backend generates a mock report for a completed job
- **THEN** the report includes match summary, metrics, landing points, routes, movement path, rallies, timeline markers, overlay labels, highlights, coach notes, diagnoses, and report actions where available

#### Scenario: Frontend consumes report data
- **WHEN** the frontend receives an analysis report payload from the backend
- **THEN** the payload can be mapped into the same visual and report components used by the local demo data

### Requirement: Algorithm adapter boundaries
The backend SHALL reserve replaceable adapter boundaries for detector, pose estimator, tracker, court calibration, and event analysis modules.

#### Scenario: Developer inspects vision modules
- **WHEN** a developer opens the backend vision module structure
- **THEN** the system provides separate areas or interfaces for detection, pose estimation, tracking, court calibration, and event analysis

#### Scenario: Future YOLO adapter is added
- **WHEN** a YOLO11-style detector is integrated later
- **THEN** it can produce normalized detections without changing frontend routes or report rendering components

#### Scenario: Future RTMPose adapter is added
- **WHEN** an RTMPose26-style pose estimator is integrated later
- **THEN** it can produce normalized pose keypoints or pose-derived features without changing frontend routes or report rendering components

### Requirement: Local storage conventions
The backend SHALL document and use local storage conventions for uploaded videos, generated reports, temporary processing files, and model weights.

#### Scenario: Developer reviews storage paths
- **WHEN** a developer reviews backend storage documentation or configuration
- **THEN** the system identifies where uploads, generated reports, temporary files, and model weights are expected to live

#### Scenario: Large generated assets exist locally
- **WHEN** uploaded videos, generated reports, temporary frames, model checkpoints, or training datasets are present in local storage
- **THEN** those files are excluded from version control by documented ignore rules or storage guidance

### Requirement: Lightweight backend smoke verification
The backend SHALL support a lightweight verification path before real model dependencies are installed.

#### Scenario: Developer runs backend verification
- **WHEN** a developer runs the documented backend smoke check
- **THEN** the backend imports or starts its API foundation without requiring YOLO11, RTMPose26, CUDA, model weights, or uploaded sample videos

