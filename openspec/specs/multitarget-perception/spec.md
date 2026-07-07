# multitarget-perception Specification

## Purpose
Define the player-focused perception contract while ball and paddle capture are out of scope for the active product flow.
## Requirements
### Requirement: Normalized multi-target detections
The backend SHALL define JSON-serializable frame-level detection records for pickleball perception targets including `player` and configurable `ball` targets, while leaving `paddle` as an optional future extension unless configured by a later capability.

#### Scenario: Multi-target detections are serialized
- **WHEN** a detector returns player or ball candidates for a processed video frame
- **THEN** each normalized detection includes `frame_index`, `timestamp_seconds`, `class_name`, `bbox` or point coordinates as applicable, `confidence`, and source frame dimensions using finite numeric values

#### Scenario: Unsupported classes are returned
- **WHEN** a detector returns classes outside the configured target map
- **THEN** the backend excludes those classes from normalized multi-target artifacts without failing the entire analysis job

#### Scenario: Low confidence detections are returned
- **WHEN** a detector returns a target below the configured confidence threshold for its class
- **THEN** the backend excludes that target from renderable multi-target artifacts while preserving stage diagnostics where available

### Requirement: Multi-class detector adapter boundary
The backend SHALL provide a replaceable detector adapter boundary for optional perception models without requiring model assets during lightweight imports or tests.

#### Scenario: Multi-class detector is configured
- **WHEN** a detector can emit supported player or ball classes for a processed frame
- **THEN** the pipeline can normalize those detections through the shared multi-target detection contract

#### Scenario: Multi-class detector is unavailable
- **WHEN** optional detector configuration, checkpoint, class map, or runtime device is unavailable
- **THEN** the pipeline reports a skipped or unavailable multi-target stage with a clear diagnostic and does not advertise missing ball or paddle overlays as available

#### Scenario: Lightweight backend imports run
- **WHEN** backend modules are imported without heavy model assets or CUDA installed
- **THEN** imports succeed and model-specific errors occur only when the configured detector is invoked

### Requirement: Player detection compatibility
The system SHALL preserve existing player/person detection, tracking, projection, and pose behavior while narrowing multi-target perception to the active player-focused flow.

#### Scenario: Existing person-only analysis runs
- **WHEN** a calibrated real analysis job runs with the existing person detector and no optional multi-class detector
- **THEN** the existing player tracking, projection, tracking overlay, and optional pose overlay behavior remain available through the current result contracts

#### Scenario: Multi-target player records are produced
- **WHEN** an optional detector emits player records for a processed frame
- **THEN** those records can be adapted into the existing player tracking path without changing frontend routes or movement metric schemas

### Requirement: Multi-target unavailable states
The backend SHALL distinguish unavailable, skipped, no-detection, partial, and available states for configured player and ball perception outputs.

#### Scenario: Model inference is disabled
- **WHEN** optional multi-target inference or ball detection is disabled by configuration
- **THEN** the pipeline marks the corresponding perception stage as skipped and avoids presenting missing ball or paddle data as detection failure

#### Scenario: Only some target classes are detected
- **WHEN** the detector produces usable player detections but no usable ball detections
- **THEN** the pipeline reports class-specific availability so player overlays can remain usable while ball output is marked no-detection, unavailable, or partial as appropriate

#### Scenario: Ball detections are produced
- **WHEN** the configured detector emits usable ball records for processed frames
- **THEN** those records can feed the ball trajectory engine without changing existing frontend routes or movement metric schemas

