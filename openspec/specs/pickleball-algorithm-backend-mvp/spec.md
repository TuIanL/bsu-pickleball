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
The backend SHALL model a standard pickleball court in a two-dimensional coordinate system measured in feet with width 20, length 44, x spanning 0 to 20, y spanning 0 to 44, net line at y = 22, near kitchen line at y = 15, far kitchen line at y = 29, and center lines for the standard service boxes.

#### Scenario: Court geometry is requested
- **WHEN** code requests the standard court model
- **THEN** the model returns court bounds, outer boundary lines, net line, kitchen lines, center service lines, non-volley zone polygons, and left and right service-zone polygons using the canonical 20 ft by 44 ft coordinates

#### Scenario: Canonical court keypoints are requested
- **WHEN** code requests the standard court keypoints
- **THEN** the model returns float coordinates for `top_left` at `(0, 0)`, `top_right` at `(20, 0)`, `bottom_right` at `(20, 44)`, and `bottom_left` at `(0, 44)`

#### Scenario: Zone membership is evaluated
- **WHEN** a court coordinate is tested against standard zones
- **THEN** the system identifies whether the coordinate is in court bounds, in a kitchen zone, or in a service zone

### Requirement: Manual court calibration and homography
The backend SHALL accept manual or semi-manual court keypoint correspondences, compute a RANSAC-backed homography that maps image pixel coordinates into standard court coordinates, compute the inverse homography that maps standard court coordinates back to image pixel coordinates, and expose validated single-point and batch-point transform helpers.

#### Scenario: Valid calibration is submitted
- **WHEN** at least four valid non-collinear image-to-court point correspondences are submitted
- **THEN** the backend stores the calibration and returns a stable calibration identifier, image-to-court homography matrix, court-to-image inverse homography matrix, court coordinate-system metadata, and calibration quality metadata

#### Scenario: Valid four-corner manual calibration is submitted
- **WHEN** a client submits `/calibration/manual` with `video_id` and named image points for `top_left`, `top_right`, `bottom_right`, and `bottom_left`
- **THEN** the backend automatically matches those points to the standard court outer-corner keypoints and returns JSON-serializable homography, inverse homography, coordinate-system, and quality fields

#### Scenario: Invalid calibration is submitted
- **WHEN** fewer than four correspondences, mismatched point counts, malformed 2D coordinates, or degenerate correspondences are submitted
- **THEN** the backend rejects the calibration with a clear validation error

#### Scenario: Pixel coordinate is projected
- **WHEN** a stored calibration projects an image footpoint
- **THEN** the system returns the corresponding standard court coordinate in feet

#### Scenario: Court coordinate is projected back to the image
- **WHEN** code projects a standard court coordinate through a valid inverse homography
- **THEN** the system returns the corresponding image pixel coordinate as floats

#### Scenario: Batch coordinates are transformed
- **WHEN** code submits multiple image or court coordinates to the transform helpers
- **THEN** the system returns a same-length sequence of transformed float coordinates without changing the requested direction

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

### Requirement: Court calibration overlay preview
The backend SHALL render a visual calibration preview by projecting standard court geometry back onto an image frame and drawing the boundary, net line, kitchen boundaries, center service lines, and translucent court-region fills.

#### Scenario: Overlay is drawn on a frame
- **WHEN** a frame image, inverse homography, and standard court geometry are provided
- **THEN** the overlay renderer returns an image with projected outer boundary lines, net line, kitchen lines, center lines, and translucent region fills while preserving the frame dimensions

#### Scenario: Calibration preview is requested
- **WHEN** a client posts to `/calibration/{calibration_id}/preview` with an input frame or a calibration associated with a readable video first frame
- **THEN** the backend generates an overlay preview image artifact and returns its local path

#### Scenario: Calibration preview cannot be generated
- **WHEN** the calibration id is unknown or no usable frame can be read or provided
- **THEN** the backend returns a clear not-found or validation error instead of creating an invalid preview artifact

