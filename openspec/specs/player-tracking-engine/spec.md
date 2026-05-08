# player-tracking-engine Specification

## Purpose
TBD - created by archiving change implement-player-tracking-engine. Update Purpose after archive.
## Requirements
### Requirement: Person detection for fixed-camera frames
The backend SHALL provide a Player Tracking Engine detector that reads decoded video frames, runs an optional Ultralytics YOLO person model, filters detections to `person` class only, applies a configurable confidence threshold, and emits normalized detection records.

#### Scenario: YOLO returns mixed classes
- **WHEN** the detector receives model results containing person and non-person boxes
- **THEN** the detector returns only records with `class_name` equal to `person`, each including `bbox`, `confidence`, and `class_name`

#### Scenario: Detector confidence threshold is configured
- **WHEN** a detection confidence is below the configured threshold
- **THEN** the detector excludes that detection from the normalized output

#### Scenario: Detector is imported without model assets
- **WHEN** backend modules import the detector package before YOLO weights are loaded
- **THEN** the import succeeds without requiring CUDA, downloaded model weights, or an active video file

#### Scenario: Detector selects runtime device
- **WHEN** the detector is initialized without an explicit device
- **THEN** the detector chooses GPU when available and otherwise uses CPU

### Requirement: Multi-object player tracking
The backend SHALL provide a replaceable `MultiObjectTracker` that accepts current-frame person detections and returns track records with stable integer `track_id`, bbox, confidence, and lost-state metadata.

#### Scenario: Detection overlaps an existing track
- **WHEN** a current detection has IOU above the configured association threshold with an active prior track
- **THEN** the tracker reuses that track's `track_id` for the current frame

#### Scenario: Detection has no matching track
- **WHEN** a current detection cannot be associated with an active prior track
- **THEN** the tracker creates a new integer `track_id` for that detection

#### Scenario: Track is temporarily unmatched
- **WHEN** an existing track is not matched in the current frame but has not exceeded the lost-frame limit
- **THEN** the tracker retains its internal state for possible reassociation without emitting it as an active player position

#### Scenario: Tracker implementation is replaced later
- **WHEN** ByteTrack or BoT-SORT is introduced as a future implementation
- **THEN** it can satisfy the same detection-in and track-out interface without changing projection, metrics, or pipeline result schemas

### Requirement: Footpoint estimation
The backend SHALL provide a `FootpointEstimator` that estimates the player's image-space ground contact point from each tracked person bbox using bbox bottom-center for the MVP.

#### Scenario: Bbox bottom center is estimated
- **WHEN** the estimator receives bbox `[x1, y1, x2, y2]`
- **THEN** it returns `image_footpoint` equal to `[(x1 + x2) / 2, y2]` with method `bbox_bottom_center`

#### Scenario: Future footpoint strategy is selected
- **WHEN** future pose or segmentation strategies are added
- **THEN** the estimator interface can report `pose_ankle_average` or `segmentation_mask_bottom` without changing downstream projection output shape

### Requirement: Player footpoint projection
The backend SHALL project tracked image footpoints through a CourtVision image-to-court homography into canonical pickleball court coordinates and emit frame-level player position records.

#### Scenario: Valid footpoint is projected
- **WHEN** a track has bbox, confidence, and a bottom-center image footpoint and a valid homography is available
- **THEN** the projector returns a `PlayerFramePosition` with frame index, timestamp, track id, bbox, image footpoint, court position, and confidence

#### Scenario: Projected point is outside tolerated court bounds
- **WHEN** a projected court coordinate falls outside the configured tolerant bounds around the standard 20 ft by 44 ft court
- **THEN** the projector either excludes the point from valid output or marks it invalid according to its configured filtering mode

#### Scenario: Spectators are detected outside the court
- **WHEN** YOLO detects people whose footpoints project beyond the tolerated court coordinate range
- **THEN** those detections do not contribute to valid player trajectories used by movement metrics

### Requirement: Tracking result serialization
The backend SHALL define JSON-serializable schemas for detections, tracks, per-frame player positions, and complete tracking results with video timing metadata.

#### Scenario: Tracking result is serialized
- **WHEN** a tracking result contains detections, tracks, positions, frame count, FPS, and frame stride metadata
- **THEN** the result can be dumped to JSON without custom encoders or non-serializable numeric types

#### Scenario: Double-player or four-player rallies are tracked
- **WHEN** two or four on-court players are detected across frames
- **THEN** the tracking result can represent multiple concurrent `track_id` trajectories in the same frame

### Requirement: Video tracking execution
The backend SHALL process uploaded video frames for player tracking using configurable frame stride, per-frame timestamps, FPS metadata, and progress logging.

#### Scenario: Every frame is processed
- **WHEN** `frame_stride` is set to 1
- **THEN** the engine attempts detection, tracking, footpoint estimation, and projection for every decoded frame

#### Scenario: Sparse frame processing is configured
- **WHEN** `frame_stride` is set to 2 or 5
- **THEN** the engine processes only matching frame indices while preserving timestamps derived from the source FPS

#### Scenario: Processing progress is logged
- **WHEN** a video with known or unknown frame count is processed
- **THEN** the pipeline logs progress at regular intervals without changing tracking output semantics

