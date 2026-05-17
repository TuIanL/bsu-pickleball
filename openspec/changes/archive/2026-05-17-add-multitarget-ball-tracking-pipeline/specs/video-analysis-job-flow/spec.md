## ADDED Requirements

### Requirement: Ball tracking pipeline reporting
The system SHALL report ball detection and ball trajectory processing status in real analysis jobs without blocking existing player tracking and pose stages.

#### Scenario: Ball tracking runs successfully
- **WHEN** a completed real job produces ball detection or trajectory artifacts
- **THEN** the job result includes ball-tracking stage status, artifact availability, detail text, and browser-loadable artifact references where available

#### Scenario: Ball tracking is skipped
- **WHEN** a real job completes while ball tracking is disabled or lacks required model configuration
- **THEN** the job result marks the ball-tracking stage as skipped or unavailable without treating the overall analysis as failed

#### Scenario: Ball tracking fails after player tracking succeeds
- **WHEN** player tracking completes but ball detection or trajectory processing fails
- **THEN** the job preserves available player, pose, projection, and metric outputs while surfacing a clear ball-specific failure detail

### Requirement: Raw pipeline result includes ball artifact metadata
The system SHALL include ball overlay metadata in completed real analysis results when ball tracking has been attempted.

#### Scenario: Frontend requests completed raw result
- **WHEN** the frontend requests raw output for a completed real job with ball tracking metadata
- **THEN** the result exposes ball overlay status, detail, JSON artifact path when persisted, and URL when browser-loadable

#### Scenario: Ball metadata is absent in older results
- **WHEN** the frontend opens a completed result generated before ball artifact metadata existed
- **THEN** the result remains readable and the frontend treats ball overlays as unavailable rather than broken
