## MODIFIED Requirements

### Requirement: Tracking result serialization
The backend SHALL define JSON-serializable schemas for frame-indexed detections, tracks, per-frame player positions, and complete tracking results with video timing metadata so both metrics and video overlays can consume the same analysis output.

#### Scenario: Tracking result is serialized
- **WHEN** a tracking result contains frame-indexed detections, tracks, positions, frame count, FPS, frame dimensions, and frame stride metadata
- **THEN** the result can be dumped to JSON without custom encoders or non-serializable numeric types

#### Scenario: Double-player or four-player rallies are tracked
- **WHEN** two or four on-court players are detected across frames
- **THEN** the tracking result can represent multiple concurrent `track_id` trajectories in the same frame

#### Scenario: Frontend consumes detection overlays
- **WHEN** a completed real job exposes tracking overlay data
- **THEN** each renderable person box includes `frame_index`, `timestamp_seconds`, `track_id` when available, `bbox`, `confidence`, and source frame dimensions

#### Scenario: Tracking data is used for court projection
- **WHEN** tracked player boxes are projected into court coordinates
- **THEN** the existing player position and movement metric data remain available for downstream metrics

## ADDED Requirements

### Requirement: YOLO-backed detection activation
The backend SHALL run YOLO person detection for real uploaded-video jobs when model inference is explicitly enabled and model assets are available.

#### Scenario: Model inference is enabled
- **WHEN** a real analysis job has a readable video, valid calibration, and model inference enabled
- **THEN** the pipeline uses the YOLO-backed person detector instead of the empty fallback detector

#### Scenario: Model inference is disabled
- **WHEN** model inference is disabled
- **THEN** the pipeline reports that person detection is unavailable or skipped and does not claim that uploaded-video person boxes were detected

#### Scenario: YOLO detects players
- **WHEN** YOLO returns person detections for processed frames
- **THEN** the pipeline persists those detections with frame timing so the frontend can render player boxes over the source video

#### Scenario: YOLO returns no players
- **WHEN** YOLO completes but returns no usable person detections
- **THEN** the pipeline completes with a no-detections state that guides the user to check camera angle, video quality, calibration, or model setup

### Requirement: Detection overlay artifact
The backend SHALL expose a tracking or detection overlay artifact for completed real jobs that processed video frames.

#### Scenario: Tracking artifact is generated
- **WHEN** a real job runs YOLO detection and tracking
- **THEN** the raw pipeline result references a JSON artifact containing frame-indexed boxes and track labels

#### Scenario: Artifact path is not browser-safe
- **WHEN** the backend stores overlay artifacts on the local filesystem
- **THEN** the API exposes a browser-loadable artifact URL or endpoint instead of requiring the frontend to read local paths directly
