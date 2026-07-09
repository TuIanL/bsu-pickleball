# ball-tracking Delta Spec

## MODIFIED Requirements

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

#### Scenario: Stationary false positives are filtered over time
- **WHEN** ball tracker processes frames where a stationary object (e.g., court marking, debris) is repeatedly detected at the same image position
- **THEN** the tracker SHALL accumulate a per-position stationary vote count across frames
- **AND** SHALL permanently reject candidates at positions whose accumulated stationary frame count exceeds the configured threshold (default 60 frames)
- **AND** the rejection reason SHALL be recorded as `stationary_blacklisted`
- **AND** the blacklist SHALL be scoped to the current job (cleared on recalibration)

#### Scenario: Genuine ball movement overrides stationary blacklist
- **WHEN** a candidate at a blacklisted position passes continuity checks (within max_jump_pixels and prediction_gate_pixels of the last valid ball position)
- **THEN** the tracker SHALL accept the candidate despite the blacklist
- **AND** this ensures the blacklist does not inhibit real ball tracking when the ball happens to occupy a previously flagged position
