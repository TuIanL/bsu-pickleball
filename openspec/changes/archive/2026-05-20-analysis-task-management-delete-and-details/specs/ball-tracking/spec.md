## MODIFIED Requirements

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
The system SHALL NOT surface ball overlay downloads, status rows, controls, or render layers for current real-analysis jobs.

#### Scenario: Client opens a current job
- **WHEN** a completed current job is displayed in the visual analysis workspace
- **THEN** the client ignores legacy ball overlay fields and does not fetch or render ball overlay artifacts

#### Scenario: Ball overlay endpoint is requested
- **WHEN** a client requests a removed ball overlay artifact type for a current job
- **THEN** the backend rejects the unsupported artifact request instead of returning active ball data

### Requirement: Ball tracking does not imply shot events
The system SHALL keep shot, bounce, rally, and tactical event claims unavailable in the active real-analysis product until a future event-analysis capability is proposed.

#### Scenario: Report requires event semantics
- **WHEN** a current real-job report surface would require ball tracking, bounce detection, hit events, shot classification, or rally segmentation
- **THEN** the system omits that surface or marks it unavailable rather than fabricating event conclusions
