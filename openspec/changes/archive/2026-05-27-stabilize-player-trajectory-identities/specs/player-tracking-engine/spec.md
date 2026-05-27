## ADDED Requirements

### Requirement: Stable player identity handoff
The Player Tracking Engine SHALL expose projected tracker observations in a form that can be consumed by a downstream player identity manager without treating `track_id` as the final player identity.

#### Scenario: Projected observation is created
- **WHEN** a tracked person box is projected into court coordinates
- **THEN** the projected observation includes source `track_id`, bbox, image footpoint, court position, confidence, frame index, and timestamp

#### Scenario: Final identity differs from source track
- **WHEN** downstream identity assignment maps a source `track_id` to a stable `player_id`
- **THEN** overlay and trajectory consumers can display both identifiers without losing source tracker diagnostics

#### Scenario: Tracker is replaced
- **WHEN** the implementation changes from the simple IOU tracker to BoT-SORT, ByteTrack, or another compatible tracker
- **THEN** the projection and identity handoff contract remains stable

### Requirement: Metric projection compatibility
The Player Tracking Engine SHALL provide enough unit metadata or conversion behavior for downstream components to consume court coordinates in meters.

#### Scenario: Projection output is metric
- **WHEN** the projector emits metric court coordinates
- **THEN** downstream identity and trajectory components consume those coordinates directly with unit metadata declaring meters

#### Scenario: Projection output is imperial
- **WHEN** the projector emits coordinates in feet for compatibility with existing court geometry helpers
- **THEN** downstream components receive explicit unit metadata or convert the coordinates to meters before player identity matching

#### Scenario: Court dimensions are serialized
- **WHEN** tracking or trajectory artifacts include court coordinate metadata
- **THEN** they include canonical metric dimensions and imperial reference dimensions

### Requirement: Participant-limited overlay labels
The Player Tracking Engine SHALL support overlay labels that include stable player identity when available while preserving existing temporary track labels for diagnostics.

#### Scenario: Player identity is available for frame detection
- **WHEN** an overlay frame is built after player identity assignment
- **THEN** each eligible player box can include a renderable label equivalent to `P<player_id> / T<track_id>`

#### Scenario: Player identity is not available
- **WHEN** an overlay frame is built before identity assignment or identity assignment is disabled
- **THEN** the overlay remains compatible with existing `track_id`-only rendering

#### Scenario: More eligible tracks than match participants
- **WHEN** a frame contains more eligible tracked people than the configured participant count
- **THEN** the backend limits player-identity overlay subjects to the configured participant count and keeps rejected tracks in diagnostics where available
