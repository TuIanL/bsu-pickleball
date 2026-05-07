# pickleball-algorithm-backend-mvp Specification

## Purpose
TBD - created by archiving change add-pickleball-algorithm-backend-mvp. Update Purpose after archive.
## Requirements
### Requirement: MVP algorithm backend module structure
The backend SHALL provide explicit MVP modules for CourtVision Calibration Engine, Player Tracking Engine, Pickleball Performance Engine, and Analysis Pipeline under the existing Python backend package.

#### Scenario: Developer inspects algorithm modules
- **WHEN** a developer opens the backend vision and service modules
- **THEN** the system exposes named modules for court geometry, homography, manual keypoint calibration, court overlay, person detection, multi-object tracking, footpoint estimation, player projection, trajectory metrics, speed metrics, zone metrics, doubles spacing metrics, heatmap generation, and the analysis pipeline

#### Scenario: Developer imports algorithm interfaces
- **WHEN** a developer imports the MVP algorithm modules without model weights installed
- **THEN** the imports succeed without requiring YOLO, CUDA, uploaded videos, or tracker model assets

### Requirement: Standard pickleball court geometry
The backend SHALL model a standard pickleball court in a two-dimensional coordinate system measured in feet with width 20, length 44, net line at y = 22, near kitchen line at y = 15, and far kitchen line at y = 29.

#### Scenario: Court geometry is requested
- **WHEN** code requests the standard court model
- **THEN** the model returns court bounds, net line, kitchen lines, non-volley zones, and left and right service zones using the canonical 20 ft by 44 ft coordinates

#### Scenario: Zone membership is evaluated
- **WHEN** a court coordinate is tested against standard zones
- **THEN** the system identifies whether the coordinate is in court bounds, in a kitchen zone, or in a service zone

### Requirement: Manual court calibration and homography
The backend SHALL accept manual or semi-manual court keypoint correspondences and compute a homography that maps image pixel coordinates into standard court coordinates.

#### Scenario: Valid calibration is submitted
- **WHEN** at least four valid non-collinear image-to-court point correspondences are submitted
- **THEN** the backend stores the calibration and returns a homography matrix with a stable calibration identifier

#### Scenario: Invalid calibration is submitted
- **WHEN** fewer than four correspondences or degenerate correspondences are submitted
- **THEN** the backend rejects the calibration with a clear validation error

#### Scenario: Pixel coordinate is projected
- **WHEN** a stored calibration projects an image footpoint
- **THEN** the system returns the corresponding standard court coordinate in feet

### Requirement: Video upload storage
The backend SHALL accept video uploads, persist them to local upload storage, and return a video identifier and basic file metadata.

#### Scenario: Supported video is uploaded
- **WHEN** a client uploads a supported video file
- **THEN** the backend stores the file, records its filename, size, content type, and local path, and returns a stable video identifier

#### Scenario: Unsupported upload is submitted
- **WHEN** a client uploads a missing or unsupported file type
- **THEN** the backend returns a clear validation error and does not create an analysis-ready video record

### Requirement: Player tracking and footpoint projection interfaces
The backend SHALL define replaceable interfaces for person detection, multi-object tracking, footpoint estimation, and projection from image coordinates into court coordinates.

#### Scenario: Detection output is normalized
- **WHEN** a detector returns person detections for a video frame
- **THEN** the backend normalizes each detection into frame index, confidence, bounding box, class label, and optional track hint fields

#### Scenario: Footpoint is estimated from a person box
- **WHEN** a person bounding box is passed to the footpoint estimator
- **THEN** the estimator returns a bottom-center footpoint suitable for court projection

#### Scenario: Track points are projected to court coordinates
- **WHEN** tracked image footpoints are passed through a valid calibration
- **THEN** the backend returns per-player projected track points with frame index, timestamp, track identifier, image point, and court point fields

### Requirement: Movement performance metrics
The backend SHALL compute basic movement performance metrics from projected player trajectories.

#### Scenario: Trajectory distance is computed
- **WHEN** projected track points for one player are ordered by time
- **THEN** the system computes total movement distance in feet from consecutive court-coordinate samples

#### Scenario: Player speed is computed
- **WHEN** projected track points include timestamps
- **THEN** the system computes per-segment speed and aggregate speed summaries

#### Scenario: Kitchen dwell is computed
- **WHEN** projected track points enter standard kitchen zones
- **THEN** the system reports kitchen dwell duration or frame counts per player

#### Scenario: Doubles spacing is computed
- **WHEN** two same-side player tracks overlap in time
- **THEN** the system computes their court-coordinate spacing over the overlapping samples

#### Scenario: Heatmap is generated
- **WHEN** projected player coordinates are provided
- **THEN** the system generates a court-binned heatmap representation suitable for JSON output

### Requirement: Analysis pipeline MVP flow
The backend SHALL provide an AnalysisPipeline service that links video metadata, optional calibration, tracking interfaces, projection, metrics, JSON output, and visualized output artifact references.

#### Scenario: Pipeline runs with available video metadata
- **WHEN** an analysis job is started for an uploaded video
- **THEN** the pipeline returns a structured result containing job id, video id, pipeline stage statuses, metrics summary, output JSON path or payload, and visualized video path when generated

#### Scenario: Pipeline runs before real models are configured
- **WHEN** real detector or tracker dependencies are unavailable
- **THEN** the pipeline still returns a deterministic mock or empty-tracks result through the same result schema

#### Scenario: Pipeline failure occurs
- **WHEN** the pipeline cannot read the video or required calibration data
- **THEN** the job records a failed status and exposes an error message through the analysis API

