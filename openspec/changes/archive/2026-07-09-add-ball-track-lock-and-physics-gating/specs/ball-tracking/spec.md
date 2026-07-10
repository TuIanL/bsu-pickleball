## MODIFIED Requirements

### Requirement: Stationary false positives are filtered over time

**Note:** The existing stationary false-positive requirement is preserved and enhanced with player motion context and the lock-state-aware missing-over-false-positive policy.

#### Scenario: Stationary false positives are filtered over time

- **WHEN** ball tracker processes frames where a stationary object (e.g., court marking, debris) is repeatedly detected at the same image position
- **THEN** the tracker SHALL accumulate a per-position stationary vote count across frames
- **AND** the tracker SHALL also accept an optional `player_motion_pixels` signal from the pipeline
- **AND** if `player_motion_pixels` is provided and exceeds `player_motion_min_pixels`, the stationary vote SHALL be weighted higher
- **AND** SHALL permanently reject candidates at positions whose accumulated stationary frame count exceeds the configured threshold (default 60 frames)
- **AND** the rejection reason SHALL be recorded as `static_false_positive`
- **AND** the blacklist SHALL be scoped to the current job (cleared on recalibration)

#### Scenario: Genuine ball movement overrides stationary blacklist

- **WHEN** a candidate at a blacklisted position passes continuity checks (within dynamic physics gate of the last valid ball position)
- **THEN** the tracker SHALL accept the candidate despite the blacklist
- **AND** this ensures the blacklist does not inhibit real ball tracking when the ball happens to occupy a previously flagged position

#### Scenario: Stationary candidate during player inactivity is not penalized

- **WHEN** a candidate remains stationary
- **AND** player motion is below `player_motion_min_pixels` (player is also stationary or absent)
- **THEN** the tracker SHALL NOT apply the player-motion-aware static penalty
- **AND** the candidate SHALL be evaluated using normal state-dependent scoring

#### Scenario: Non-play timeline context is optional

- **WHEN** the pipeline does not provide non-play timeline events
- **THEN** the tracker SHALL use `player_motion_pixels` as a weak signal of active play
- **AND** if `player_motion_pixels` is also unavailable, the tracker SHALL fall back to the existing stationary blacklist behavior without error
- **AND** this ensures the player-motion-aware static suppression does not block on missing timeline data

## ADDED Requirements

### Requirement: Locked-state missing-over-false-positive policy

The system SHALL respect the missing-over-false-positive policy when the ball tracker is in LOCKED state. No candidate may be accepted solely because it has the highest detector confidence if it fails the dynamic physics gate.

#### Scenario: Missing frame preferred over distant false positive

- **WHEN** the ball tracker is in LOCKED state
- **AND** the true ball is temporarily occluded or missed by the detector
- **AND** the only available candidate is a high-confidence detection far from the predicted position
- **THEN** the tracker MUST reject the distant candidate
- **AND** SHALL emit a missing frame with `overall_decision = "missing_predicted_only"`
- **AND** SHALL record `predicted_position` in the frame output
- **AND** the ball trajectory artifact SHALL contain the predicted position for downstream use (interpolation, bounce detection, rally segmentation)

#### Scenario: Candidate must pass physics gate in LOCKED state

- **WHEN** the ball tracker is in LOCKED state
- **AND** multiple candidates exist
- **THEN** each candidate MUST pass the dynamic physics gate before being eligible for acceptance
- **AND** candidates that fail the gate SHALL be rejected regardless of detector confidence
- **AND** the rejection reason for gated candidates SHALL be `physics_gate_rejected`

#### Scenario: SEARCHING state does not enforce missing-over-false-positive

- **WHEN** the ball tracker is in SEARCHING state
- **AND** a single high-confidence candidate exists far from previous detections
- **THEN** the tracker MAY accept the candidate to initialize a new track
- **AND** the missing-over-false-positive policy SHALL NOT apply in SEARCHING state

### Requirement: Per-frame debug metadata in ball overlay

The ball overlay artifact SHALL include per-frame track state and candidate decision metadata when the ball tracking pipeline is enabled.

#### Scenario: Debug metadata is available in ball_overlay.json

- **WHEN** `ball_overlay.json` is generated with ball tracking enabled
- **AND** this change's state machine and physics gating are active
- **THEN** each frame SHALL include optional debug fields: `track_state`, `predicted_position`, `accepted_candidate_id`, and `overall_decision`
- **AND** the debug fields SHALL be optional and positioned after the core detection data

#### Scenario: Missing frame contains predicted position

- **WHEN** a frame has `track_status = "missing"` and the tracker is in LOCKED or LOST state
- **THEN** the frame SHALL include `predicted_position` in image coordinates
- **AND** the frame SHALL include `track_state` indicating LOCKED or LOST
