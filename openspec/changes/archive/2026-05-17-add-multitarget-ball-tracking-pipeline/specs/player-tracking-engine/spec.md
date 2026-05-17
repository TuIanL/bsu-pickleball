## ADDED Requirements

### Requirement: Multi-target player compatibility
The Player Tracking Engine SHALL remain compatible with existing person-only detections while allowing normalized multi-target player detections to feed the same tracking, projection, and overlay path.

#### Scenario: Person detector remains active
- **WHEN** a real analysis job runs with the existing person detector
- **THEN** the backend continues to generate player tracks, projected positions, detection overlays, and pose inputs using the current person tracking contract

#### Scenario: Multi-target detector emits players
- **WHEN** a configured multi-target detector emits `player` detections for processed frames
- **THEN** those detections can be converted into the Player Tracking Engine input shape without changing projected movement metrics or browser-facing player overlay schemas

#### Scenario: Ball or paddle detections are present
- **WHEN** normalized multi-target output includes `ball` or `paddle` detections alongside player detections
- **THEN** the Player Tracking Engine ignores non-player targets for player projection and movement metrics while preserving them for their dedicated artifacts
