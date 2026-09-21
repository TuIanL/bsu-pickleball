# python-vision-backend-foundation Specification

## Purpose

定义 Python 视觉后端的工程基础：分析 API 与报告 schema、算法适配器边界、本地存储约定、轻量冒烟验证与本地 Worker 运行时。
## Requirements
### Requirement: Python backend project foundation
The system SHALL include a Python backend project area dedicated to real product video analysis APIs, durable job orchestration, MVP computer-vision algorithms, research-grade execution records, and future model-backed analysis.

#### Scenario: Developer inspects backend structure
- **WHEN** a developer opens the backend project area
- **THEN** the system provides an API entrypoint, route modules, schema modules, service modules, job orchestration modules, core configuration modules, and concrete MVP vision algorithm modules

#### Scenario: Developer inspects backend environment files
- **WHEN** a developer reviews backend setup documentation or metadata
- **THEN** the system identifies the lightweight Python API dependencies separately from optional heavy vision-model dependencies and optional orchestration/runtime dependencies

#### Scenario: Developer inspects algorithm engine boundaries
- **WHEN** a developer opens the backend vision module structure
- **THEN** the system provides clear package boundaries for CourtVision Calibration Engine, Player Tracking Engine, Pickleball Performance Engine, and orchestration-facing pipeline adapters

#### Scenario: Developer inspects product positioning
- **WHEN** a developer reviews backend or system architecture documentation
- **THEN** the system describes the platform as a real pickleball analysis product and research vehicle rather than only a competition demonstration

### Requirement: Analysis API endpoints
The backend SHALL expose API boundaries for video upload, manual calibration, analysis job creation, job status retrieval, job cancellation, algorithm result retrieval, and analysis report retrieval.

#### Scenario: Client uploads a video
- **WHEN** the client submits a valid multipart video upload to the backend API
- **THEN** the backend returns a stable video identifier and basic uploaded video metadata

#### Scenario: Client creates an analysis job
- **WHEN** the frontend submits a valid analysis request to the backend API
- **THEN** the backend returns a stable job identifier, durable initial job status, and stage telemetry suitable for task management

#### Scenario: Client requests job status
- **WHEN** the frontend requests the status for an existing analysis job
- **THEN** the backend returns job metadata, current status, current stage, progress, timing, completion information, cancellation context, or error information when available

#### Scenario: Client cancels an active job
- **WHEN** the frontend requests cancellation for an existing queued or running analysis job
- **THEN** the backend records the cancellation request or terminal canceled state and returns the latest durable job summary

#### Scenario: Client requests algorithm result
- **WHEN** the frontend or developer requests the algorithm result for a completed analysis job
- **THEN** the backend returns a structured JSON payload with pipeline stages, calibration reference when available, projected movement tracks, metrics, stage telemetry, and output artifact references

#### Scenario: Client requests completed report
- **WHEN** the frontend requests the report for a completed analysis job
- **THEN** the backend returns an analysis report payload matching the shared report contract

#### Scenario: Client requests missing job
- **WHEN** the frontend requests status, cancellation, algorithm result, or report data for an unknown job identifier
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
The backend SHALL document and use local storage conventions for uploaded videos, calibration files, durable job records, stage telemetry, generated JSON results, visualized output videos, temporary processing files, research artifacts, and model weights.

#### Scenario: Developer reviews storage paths
- **WHEN** a developer reviews backend storage documentation or configuration
- **THEN** the system identifies where uploads, calibrations, job records, stage telemetry, generated outputs, temporary files, research artifacts, and model weights are expected to live

#### Scenario: Large generated assets exist locally
- **WHEN** uploaded videos, generated reports, temporary frames, model checkpoints, visualized videos, research run outputs, or training datasets are present in local storage
- **THEN** those files are excluded from version control by documented ignore rules or storage guidance

#### Scenario: Job artifacts are shared across product and research use
- **WHEN** a real analysis job completes
- **THEN** its stored job metadata, stage telemetry, model/runtime context, and result artifacts can be used for product display and later research inspection without changing the storage contract

### Requirement: Lightweight backend smoke verification
The backend SHALL support a lightweight verification path before real model dependencies are installed.

#### Scenario: Developer runs backend verification
- **WHEN** a developer runs the documented backend smoke check
- **THEN** the backend imports or starts its API foundation without requiring YOLO11, RTMPose26, CUDA, model weights, or uploaded sample videos

### Requirement: Local worker runtime
The backend SHALL provide a local worker runtime boundary for executing queued analysis jobs outside request handlers.

#### Scenario: Backend starts with worker enabled
- **WHEN** the local runtime starts with job worker execution enabled
- **THEN** the backend starts or exposes a worker loop that can claim queued jobs according to queue and resource policy

#### Scenario: Backend starts with worker disabled
- **WHEN** the local runtime starts with worker execution disabled
- **THEN** the API can still create and list queued jobs, but no queued job is executed until a worker is enabled

#### Scenario: Worker reports progress
- **WHEN** a worker executes a job
- **THEN** it reports progress through the job orchestration service rather than mutating only process-local variables

### Requirement: Product and research platform documentation
The system SHALL describe the project as a real product and research platform in developer-facing and user-facing project descriptions.

#### Scenario: Developer reads architecture documentation
- **WHEN** a developer opens the system architecture documentation
- **THEN** it explains that the platform supports real video analysis, model-backed computer vision, reproducible execution records, and research outputs derived from the development process

#### Scenario: User sees product copy
- **WHEN** user-facing copy describes the platform's purpose
- **THEN** it frames the system as an operational pickleball analysis product while clearly labeling demo/sample data when the current view is not based on a real uploaded job

#### Scenario: Research maturity is described
- **WHEN** documentation describes research output
- **THEN** it states that datasets, experiments, model validation, calibration methods, and analysis records support research output without claiming unavailable publications or unsupported algorithm results

