# ball-tracking Specification

## Purpose
Define the inactive state for ball detection, trajectory, overlay, and event-analysis artifacts while the active product flow focuses on player movement and pose analysis.
## Requirements
### Requirement: Ball detection artifact
The backend SHALL NOT create or expose ball detection artifacts for current real-analysis jobs while ball capture is out of scope.

#### Scenario: Current jobs omit ball detection artifacts
- **WHEN** a real analysis job completes in the current movement-focused flow
- **THEN** the backend omits ball detection artifacts, no-detection ball states, and ball overlay URLs from the job result

#### Scenario: Legacy ball artifacts exist
- **WHEN** older persisted output directories still contain ball artifact files
- **THEN** the system treats those files as legacy cleanup data rather than active analysis output

### Requirement: Ball trajectory continuity
The backend SHALL NOT generate or consume ball trajectory continuity artifacts in the current movement-focused flow.

#### Scenario: Trajectory processing is skipped
- **WHEN** a current real analysis job runs
- **THEN** the pipeline does not run ball trajectory repair, prediction, continuity checks, or segment generation

#### Scenario: Player movement remains supported
- **WHEN** ball trajectory processing is omitted
- **THEN** player/person detection, pose, tracking, projection, and movement metrics remain the supported analysis path

### Requirement: Ball overlay artifact retrieval
The system SHALL NOT generate, advertise, or render active ball overlay layers for current real-analysis jobs while ball capture is out of scope, but the backend SHALL treat `ball-overlay` as a known artifact name in the shared analysis artifact contract.

#### Scenario: Client opens a current job
- **WHEN** a completed current job is displayed in the visual analysis workspace
- **THEN** the client ignores missing ball overlay fields and does not fetch or render ball overlay artifacts unless a future feature explicitly surfaces them

#### Scenario: Ball overlay endpoint is requested for a missing current artifact
- **WHEN** a client requests `ball-overlay` for a current job that has not generated `ball_overlay.json`
- **THEN** the backend returns 404 for the missing artifact instead of rejecting the artifact name as unsupported

#### Scenario: Ball overlay endpoint is requested for an existing artifact file
- **WHEN** a client requests `ball-overlay` for a job directory containing `ball_overlay.json`
- **THEN** the backend returns the JSON artifact through the shared analysis artifact API

### Requirement: Ball tracking does not imply shot events
The system SHALL keep shot, bounce, rally, and tactical event claims unavailable in the active real-analysis product until a future event-analysis capability is proposed.

#### Scenario: Report requires event semantics
- **WHEN** a current real-job report surface would require ball tracking, bounce detection, hit events, shot classification, or rally segmentation
- **THEN** the system omits that surface or marks it unavailable rather than fabricating event conclusions

