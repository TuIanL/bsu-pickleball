# ball-physics-gating Specification

## Purpose
Define dynamic physics gating, state-aware candidate scoring, player-motion-aware static false-positive suppression, and structured debug metadata output for the ball tracker.
## Requirements
### Requirement: Smooth velocity prediction

The tracker SHALL predict the next ball position using smoothed velocity computed over multiple recent accepted points.

#### Scenario: Prediction from sufficient trajectory history

- **WHEN** the tracker has at least `min_prediction_points` (default 3) accepted points
- **THEN** the predicted position SHALL be computed as `last_position + avg_velocity * dt`
- **AND** `avg_velocity` SHALL be the average pixel displacement per frame over the last `min_prediction_points` frames

#### Scenario: Prediction with insufficient history

- **WHEN** the tracker has fewer than `min_prediction_points` accepted points
- **THEN** the prediction SHALL fall back to the last accepted point without extrapolation

#### Scenario: Prediction with no history

- **WHEN** the tracker has fewer than 2 accepted points
- **THEN** `predicted_position` SHALL be None

### Requirement: Dynamic physics gate

The tracker SHALL compute a per-frame dynamic gate threshold for rejecting implausible candidates, rather than using a fixed pixel distance threshold.

#### Scenario: Gate calculated from recent speed

- **WHEN** the tracker computes the dynamic gate
- **THEN** `dynamic_gate_pixels` SHALL be computed as `base_gate_pixels + speed_factor * recent_speed_px_per_frame + missing_factor * missing_frames + perspective_adjustment`
- **AND** `base_gate_pixels`, `speed_factor`, and `missing_factor` SHALL be configurable in `BallTrackerConfig`
- **AND** the result SHALL be clamped between `min_gate_pixels` and `max_gate_pixels`

#### Scenario: Gate expands with higher recent speed

- **WHEN** the recent ball motion is fast (e.g., 60+ px/frame)
- **THEN** the dynamic gate SHALL be wider than when the ball is slow
- **AND** a fast-moving ball SHALL NOT be rejected solely due to large pixel displacement

#### Scenario: Gate expands with more missing frames

- **WHEN** `missing_frames` increases (e.g., ball is occluded)
- **THEN** the dynamic gate SHALL widen to allow recovery from a larger area

#### Scenario: Gate has a minimum floor

- **WHEN** the computed dynamic gate is below `min_gate_pixels`
- **THEN** the gate SHALL be raised to `min_gate_pixels`
- **AND** this ensures slow-moving balls (dink, serve preparation) are not falsely rejected

#### Scenario: Gate has a maximum cap

- **WHEN** the computed dynamic gate exceeds `max_gate_pixels`
- **THEN** the gate SHALL be clamped to `max_gate_pixels`

#### Scenario: Gate includes perspective adjustment with fallback

- **WHEN** `perspective_adjustment` is computed for a candidate
- **THEN** a simple region adjustment SHALL be used: near-court (lower image region) adds positive adjustment, far-court (upper image region) adds negative adjustment
- **AND** if court region metadata is unavailable, `perspective_adjustment` SHALL default to 0 (no adjustment)

#### Scenario: Gate is not applied in SEARCHING state

- **WHEN** the tracker is in SEARCHING state
- **THEN** the dynamic physics gate SHALL NOT be used to reject candidates

### Requirement: State-aware candidate scoring

The tracker SHALL use different scoring weights for each track state. Detector confidence, prediction proximity, motion consistency, candidate size consistency SHALL be weighted according to the current state.

#### Scenario: SEARCHING state weights favor detector confidence

- **WHEN** the tracker scores candidates in SEARCHING state
- **THEN** `detector_confidence_weight` SHALL be higher than `prediction_weight`
- **AND** `jump_penalty_weight` SHALL be lower than in LOCKED state

#### Scenario: LOCKED state weights favor trajectory continuity

- **WHEN** the tracker scores candidates in LOCKED state
- **THEN** `prediction_weight` and `motion_consistency_weight` SHALL be higher than `detector_confidence_weight`
- **AND** `jump_penalty_weight` SHALL be higher than in SEARCHING state

#### Scenario: TENTATIVE state uses balanced weights

- **WHEN** the tracker scores candidates in TENTATIVE state
- **THEN** weights SHALL be between SEARCHING and LOCKED values
- **AND** the tracker SHALL not fully apply missing-over-false-positive policy

#### Scenario: LOST state uses recovery-biased weights

- **WHEN** the tracker scores candidates in LOST state
- **THEN** `lost_gate_multiplier` SHALL be applied to widen the acceptable search area
- **AND** the tracker SHALL prioritize returning to LOCKED state over strict physical consistency

### Requirement: Static false-positive suppression with player motion context

The tracker SHALL detect and suppress candidates that remain nearly stationary while player motion is active.

#### Scenario: Stationary candidate with active player motion is suppressed

- **WHEN** a candidate remains within `static_radius_pixels` for `static_window_frames`
- **AND** player motion exceeds `player_motion_min_pixels` during the same window
- **THEN** the tracker SHALL reject the candidate
- **AND** the rejection reason SHALL be recorded as `static_false_positive`

#### Scenario: Stationary candidate without player motion is not suppressed

- **WHEN** a candidate remains within `static_radius_pixels` for `static_window_frames`
- **AND** player motion does NOT exceed `player_motion_min_pixels` during the same window
- **THEN** the tracker SHALL NOT apply the player-motion-aware static penalty
- **AND** the candidate SHALL be evaluated using the normal state-dependent scoring only

#### Scenario: Player motion data is optional

- **WHEN** the pipeline does not provide `player_motion_pixels` (value is None)
- **THEN** the tracker SHALL fall back to the existing stationary blacklist and stationary candidate checks
- **AND** the player-motion-aware static suppression SHALL be skipped without error

### Requirement: Structured debug metadata output

The tracker SHALL emit per-frame debug metadata for every processed frame, recording candidate decisions and rejection reasons.

#### Scenario: Accepted frame emits debug data

- **WHEN** the tracker accepts a candidate
- **THEN** the frame SHALL emit debug metadata in `diagnostics.ball_frame_debug` including: `track_state`, `accepted_candidate_id`, `predicted_position`, and a list of all candidates with their `raw_confidence`, `final_score`, `distance_to_prediction`, `passed_physics_gate`, and `rejection_reason`

#### Scenario: Missing frame emits debug data

- **WHEN** the tracker produces a missing frame (no candidate accepted)
- **THEN** the frame SHALL emit debug metadata including: `track_state`, `predicted_position`, `overall_decision`, and `rejection_reason`
- **AND** `overall_decision` SHALL distinguish between `missing_no_candidates` (no candidates at all) and `missing_predicted_only` (candidates existed but all were gated)

#### Scenario: Rejection reasons are recorded

- **WHEN** a candidate is rejected
- **THEN** the rejection reason SHALL be one of: `physics_gate_rejected`, `static_false_positive`, `too_far_from_prediction`, `jump_too_large`, `speed_too_high`, `low_final_score`
- **AND** the reason SHALL be recorded as a structured string, not free text
