# ball-tracking Specification

## Purpose
Define the inactive state for ball detection, trajectory, overlay, and event-analysis artifacts while the active product flow focuses on player movement and pose analysis.
## Requirements
### Requirement: Ball detection artifact
The backend SHALL create and expose ball detection artifacts for real-analysis jobs when ball detection is enabled and required detector dependencies are available.

#### Scenario: Ball detection enabled and candidates are produced
- **WHEN** a real analysis job completes with ball detection enabled and a configured detector emits usable ball candidates
- **THEN** the backend writes ball detection records into the shared detection artifact contract
- **AND** the job result exposes the generated artifact URL, status, and detail

#### Scenario: Ball detection disabled
- **WHEN** a real analysis job runs with ball detection disabled
- **THEN** the backend omits active ball detection artifacts for that job
- **AND** the pipeline records the ball detection stage as skipped or leaves the optional artifact reference null without failing the job

#### Scenario: Ball detector dependencies are unavailable
- **WHEN** ball detection is enabled but the detector configuration, model path, adapter, or runtime dependency is unavailable
- **THEN** the backend marks the ball detection stage as unavailable or failed with a clear diagnostic
- **AND** existing player movement, pose, tracking, projection, and serve outputs remain available when their own inputs are valid

#### Scenario: Legacy ball artifacts exist
- **WHEN** older persisted output directories still contain ball artifact files that are not referenced by the current job result
- **THEN** the system treats those files as legacy cleanup data rather than active analysis output

### Requirement: Ball trajectory continuity
The backend SHALL generate ball trajectory continuity artifacts when ball detection is enabled and the pipeline receives usable ball candidate samples.

#### Scenario: Trajectory processing runs
- **WHEN** a current real analysis job runs with ball detection enabled and frame-level ball candidates are available
- **THEN** the pipeline runs ball trajectory filtering, prediction, continuity checks, cleaning, and short-gap interpolation
- **AND** the pipeline writes raw and cleaned ball trajectory artifacts with status and detail

#### Scenario: Trajectory input is unavailable
- **WHEN** ball trajectory processing lacks detector samples, frame timing, or required video metadata
- **THEN** the pipeline records the trajectory stage as skipped, unavailable, partial, or no-candidates with an explanatory detail
- **AND** the job MUST NOT fail solely because ball trajectory output is unavailable

#### Scenario: Player movement remains supported
- **WHEN** ball trajectory processing is omitted, unavailable, or fails in a recoverable way
- **THEN** player/person detection, pose, tracking, projection, and movement metrics remain the supported analysis path

### Requirement: Ball overlay artifact retrieval
The system SHALL support ball overlay artifact retrieval through the shared analysis artifact contract when a job generates `ball_overlay.json`, and SHALL return a missing-artifact response when the known artifact is not generated.

#### Scenario: Client opens a current job with ball overlay available
- **WHEN** a completed current job references `ball_overlay.json` or equivalent ball layer artifact metadata
- **THEN** the client may fetch and render ball overlay data as a real job layer

#### Scenario: Client opens a current job without ball overlay
- **WHEN** a completed current job has no generated ball overlay field
- **THEN** the client ignores the missing ball overlay artifact or marks the layer unavailable
- **AND** the client MUST NOT render simulated ball overlay data as the real job result

#### Scenario: Ball overlay endpoint is requested for a missing current artifact
- **WHEN** a client requests `ball-overlay` for a current job that has not generated `ball_overlay.json`
- **THEN** the backend returns 404 for the missing artifact instead of rejecting the artifact name as unsupported

#### Scenario: Ball overlay endpoint is requested for an existing artifact file
- **WHEN** a client requests `ball-overlay` for a job directory containing `ball_overlay.json`
- **THEN** the backend returns the JSON artifact through the shared analysis artifact API

### Requirement: Ball tracking does not imply shot events
The system SHALL allow ball tracking, trajectory, and bounce candidate artifacts to become available before full shot, rally, scoring, or tactical event semantics are implemented.

#### Scenario: Ball trajectory facts are available
- **WHEN** a current real-job report surface has ball trajectory or bounce candidate artifacts
- **THEN** the system may present those facts as algorithm-derived candidates
- **AND** the system MUST label them distinctly from complete shot, rally, scoring, or tactical conclusions

#### Scenario: Report requires event semantics
- **WHEN** a current real-job report surface would require hit events, shot classification, rally segmentation, scoring, or tactical conclusions that are not implemented
- **THEN** the system omits that surface or marks it unavailable rather than fabricating event conclusions

