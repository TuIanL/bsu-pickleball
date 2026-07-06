## MODIFIED Requirements

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
