## ADDED Requirements

### Requirement: BallTrackState enum

The tracker SHALL maintain an explicit state machine with four states: SEARCHING, TENTATIVE, LOCKED, LOST.

#### Scenario: Tracker starts in SEARCHING

- **WHEN** a new `BallTracker` is created or a track is reset after prolonged loss
- **THEN** the initial state SHALL be SEARCHING

#### Scenario: SEARCHING transitions to TENTATIVE

- **WHEN** the tracker accepts at least `tentative_min_hits` consecutive physically plausible candidates
- **THEN** the state SHALL transition from SEARCHING to TENTATIVE

#### Scenario: TENTATIVE transitions to LOCKED

- **WHEN** the tracker accepts at least `lock_min_hits` consecutive physically plausible candidates
- **AND** the accepted positions form a physically plausible motion sequence
- **THEN** the state SHALL transition from TENTATIVE to LOCKED

#### Scenario: LOCKED transitions to LOST on missing detection

- **WHEN** the tracker is in LOCKED state
- **AND** no candidate passes the physics gate for a frame
- **THEN** the state SHALL transition from LOCKED to LOST

#### Scenario: LOST recovers back to LOCKED

- **WHEN** the tracker is in LOST state
- **AND** a candidate appears within the extended physics gate of the predicted position
- **THEN** the state SHALL transition from LOST back to LOCKED

#### Scenario: LOST transitions to SEARCHING after prolonged missing

- **WHEN** the tracker is in LOST state
- **AND** `missing_frames` exceeds `max_missing_frames_locked`
- **THEN** the state SHALL transition from LOST to SEARCHING
- **AND** the existing track SHALL be considered expired

#### Scenario: LOST transitions to SEARCHING on explicit state reset

- **WHEN** the change from LOST to SEARCHING requires a clean start
- **THEN** the tracker SHALL accept with `track_state: LOST` to SEARCHING
- **AND** `reset_after_gap` decision reason recorded in debug output

### Requirement: SEARCHING state candidate selection

In SEARCHING state, the tracker SHALL prioritize detector confidence and basic candidate validity, accepting candidates even when trajectory continuity is weak.

#### Scenario: SEARCHING selects highest-confidence candidate

- **WHEN** the tracker is in SEARCHING state
- **AND** multiple candidates exist
- **THEN** the highest-confidence candidate SHALL be accepted if it passes basic hard filters (area, aspect ratio, ROI)
- **AND** the candidate SHALL NOT be subject to strict physics gating

#### Scenario: SEARCHING rejects invalid candidate

- **WHEN** the tracker is in SEARCHING state
- **AND** all candidates fail basic hard filters
- **THEN** the tracker SHALL emit a missing frame
- **AND** `overall_decision` SHALL be `missing_no_candidates`

### Requirement: TENTATIVE state candidate selection

In TENTATIVE state, the tracker SHALL reference motion continuity but may still accept moderately distant candidates.

#### Scenario: TENTATIVE accepts continuity-consistent candidate

- **WHEN** the tracker is in TENTATIVE state
- **AND** a candidate is within the dynamic physics gate
- **AND** the candidate has a reasonable detector confidence
- **THEN** the tracker SHALL accept the candidate
- **AND** the candidate SHALL update the active trajectory

#### Scenario: TENTATIVE rejects distant high-confidence candidate

- **WHEN** the tracker is in TENTATIVE state
- **AND** a high-confidence candidate lies outside the dynamic physics gate
- **AND** a lower-confidence candidate exists within the gate
- **THEN** the tracker SHALL prefer the gate-consistent candidate
- **AND** the distant candidate SHALL be rejected or heavily downgraded

### Requirement: LOCKED state candidate selection

In LOCKED state, the tracker SHALL prioritize trajectory continuity and physical plausibility over detector confidence. The missing-over-false-positive policy SHALL apply.

#### Scenario: LOCKED accepts gate-consistent candidate

- **WHEN** the tracker is in LOCKED state
- **AND** a candidate is within the dynamic physics gate of the predicted position
- **THEN** the tracker SHALL accept the candidate
- **AND** the candidate SHALL update the active trajectory

#### Scenario: LOCKED rejects distant high-confidence candidate

- **WHEN** the tracker is in LOCKED state
- **AND** no candidate passes the dynamic physics gate
- **THEN** the tracker SHALL NOT accept any candidate
- **AND** the tracker SHALL emit a missing frame with `predicted_position`
- **AND** `overall_decision` SHALL be `missing_predicted_only`
- **AND** the rejection reason for the highest-scoring but gated candidate SHALL be recorded as `physics_gate_rejected`

#### Scenario: LOCKED enforces missing-over-false-positive

- **WHEN** the tracker is in LOCKED state
- **AND** the only available candidate is a high-confidence detection far from the predicted position
- **THEN** the tracker MUST reject that candidate
- **AND** SHALL emit a missing frame rather than a false positive

### Requirement: LOST state candidate recovery

In LOST state, the tracker SHALL continue predicting the ball position and apply an extended physics gate for recovery.

#### Scenario: LOST recovers candidate within extended gate

- **WHEN** the tracker is in LOST state
- **AND** a candidate appears within the extended physics gate (wider than LOCKED gate)
- **THEN** the tracker SHALL accept the candidate
- **AND** transition back to LOCKED state
- **AND** record `recovery_reason = "recovered_from_lost"`

#### Scenario: LOST emits predicted position when no recovery candidate

- **WHEN** the tracker is in LOST state
- **AND** no candidate appears within the extended physics gate
- **THEN** the tracker SHALL emit a missing frame with `predicted_position`
- **AND** `overall_decision` SHALL be `missing_predicted_only`
- **AND** `missing_frames` SHALL increment

### Requirement: Track lock threshold configuration

The state transition thresholds SHALL be configurable via `BallTrackerConfig`.

#### Scenario: Thresholds have sensible defaults

- **WHEN** a `BallTrackerConfig` is created with default values
- **THEN** `tentative_min_hits` SHALL default to 2
- **AND** `lock_min_hits` SHALL default to 4
- **AND** `max_missing_frames_locked` SHALL default to 10

#### Scenario: Thresholds can be overridden

- **WHEN** a `BallTrackerConfig` is created with custom values
- **THEN** the custom values SHALL override the defaults
- **AND** the tracker SHALL use the custom thresholds for state transitions
