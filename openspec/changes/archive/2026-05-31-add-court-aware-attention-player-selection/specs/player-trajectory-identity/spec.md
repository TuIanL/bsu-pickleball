## MODIFIED Requirements

### Requirement: Stable doubles player identities
The backend SHALL assign target-court-eligible projected player observations to stable match-level `player_id` values for doubles analysis, distinct from detector observations and temporary tracker `track_id` values.

#### Scenario: Tracker emits fragmented IDs for four real players
- **WHEN** a doubles video produces more than four distinct source `track_id` values across the match
- **THEN** the final player trajectory artifact exposes no more than four stable `player_id` trajectories for target-court match metrics

#### Scenario: Source track history is preserved
- **WHEN** multiple source `track_id` values are assigned to the same real target-court player
- **THEN** the player state records current and historical source track IDs for diagnostics

#### Scenario: Existing track mapping is observed again
- **WHEN** an observation contains a `track_id` already bound to a `player_id` and remains target-court eligible or is within a configured reconnect grace period
- **THEN** the identity manager updates the existing player rather than creating a new player

#### Scenario: Neighbor court track is observed
- **WHEN** an observation belongs to a tracklet classified as non-target-court by the player selection layer
- **THEN** the identity manager does not create or update a final target-court `player_id` from that observation and records filtered diagnostics

### Requirement: Track-to-player reconnect scoring
The backend SHALL score new or unbound track observations against existing players using target-court eligibility, metric court position, motion continuity, and optional appearance similarity when available.

#### Scenario: New track appears near predicted lost player
- **WHEN** an unbound source `track_id` appears near a lost player's predicted metric court position and is target-court eligible
- **THEN** the identity manager assigns the track to that player when the score meets the configured threshold

#### Scenario: Candidate assignment implies implausible speed
- **WHEN** assigning an observation to a player would exceed the configured maximum plausible player speed in meters per second
- **THEN** the identity manager rejects or downranks that assignment

#### Scenario: Four player identities already exist
- **WHEN** four player identities already exist and a new unbound target-court-eligible track appears
- **THEN** the system does not create a fifth player identity and instead assigns, drops, or records the track as unmatched diagnostics

#### Scenario: Unbound track lacks target-court eligibility
- **WHEN** an unbound source `track_id` has low target-court membership or is classified as a neighbor-court candidate
- **THEN** the identity manager rejects the assignment regardless of generic person confidence or movement level
