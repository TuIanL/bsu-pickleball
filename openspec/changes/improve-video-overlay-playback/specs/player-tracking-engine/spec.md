## MODIFIED Requirements

### Requirement: Detection overlay artifact
The backend SHALL expose a tracking or detection overlay artifact for completed real jobs that processed video frames, and renderable overlay boxes SHALL be limited to court-relevant tracked persons derived from calibrated footpoint projection.

#### Scenario: Tracking artifact is generated
- **WHEN** a real job runs YOLO detection, tracking, and calibrated footpoint projection
- **THEN** the raw pipeline result references a JSON artifact containing frame-indexed boxes and track labels only for tracked persons whose projected footpoints fall within the configured match-relevant court bounds

#### Scenario: Spectator is detected outside match bounds
- **WHEN** YOLO detects a person whose tracked footpoint projects beyond the configured match-relevant court bounds
- **THEN** that person is excluded from renderable detection overlay frames while raw detection and tracking internals may still record model output for diagnostics

#### Scenario: Player steps near court boundary
- **WHEN** a tracked player footpoint projects slightly outside the standard court lines but remains within configured tolerated bounds
- **THEN** the backend keeps that player eligible for renderable overlay boxes

#### Scenario: Artifact path is not browser-safe
- **WHEN** the backend stores overlay artifacts on the local filesystem
- **THEN** the API exposes a browser-loadable artifact URL or endpoint instead of requiring the frontend to read local paths directly

### Requirement: Video tracking execution
The backend SHALL process uploaded video frames for player tracking using configurable frame stride, per-frame timestamps, FPS metadata, and progress logging, with defaults suitable for smooth 60fps overlay presentation.

#### Scenario: Every frame is processed
- **WHEN** `frame_stride` is set to 1
- **THEN** the engine attempts detection, tracking, footpoint estimation, and projection for every decoded frame

#### Scenario: Sparse frame processing is configured
- **WHEN** `frame_stride` is set to 2 or 5
- **THEN** the engine processes only matching frame indices while preserving timestamps derived from the source FPS

#### Scenario: Default 60fps overlay processing is used
- **WHEN** a real job is processed without an explicit overlay frame stride override
- **THEN** the backend uses a default stride that produces substantially smoother overlay samples than 2fps for 60fps source footage

#### Scenario: Processing progress is logged
- **WHEN** a video with known or unknown frame count is processed
- **THEN** the pipeline logs progress at regular intervals without changing tracking output semantics
