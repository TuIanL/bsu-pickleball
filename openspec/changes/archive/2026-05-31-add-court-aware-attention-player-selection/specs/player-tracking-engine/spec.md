## MODIFIED Requirements

### Requirement: Primary-player overlay subject selection
The backend SHALL select renderable overlay subjects from tracked people using target-court-aware tracklet scoring and participant-limited ranking based on detection confidence, track quality, target court membership, and group consistency rather than using standard court-line bounds or single-frame track quality as the primary visibility rule.

#### Scenario: High-confidence match players are selected
- **WHEN** a processed frame or selection window contains tracked people with high detection confidence, stable recent track history, and strong target-court membership
- **THEN** the backend includes those tracks in renderable overlay frames up to the configured participant limit

#### Scenario: Low-confidence incidental detections are dropped
- **WHEN** a processed frame or selection window contains tracked people whose detection confidence, track quality, or target-court membership falls below the configured primary-player selection threshold
- **THEN** the backend excludes those tracks from renderable overlay frames while preserving raw detection or tracking diagnostics where available

#### Scenario: Player steps outside court lines
- **WHEN** a tracked player has high confidence, primary-player track quality, and strong target-court membership but their projected footpoint is slightly outside the standard court lines during normal match movement
- **THEN** the backend keeps that track eligible for renderable overlay frames instead of hiding it solely because it is line-out

#### Scenario: Frame contains more tracked people than match participants
- **WHEN** a frame or selection window contains more eligible tracked people than the configured player count for the match context
- **THEN** the backend keeps the highest-ranked target-court primary-player tracks and excludes lower-ranked incidental or non-target-court tracks from renderable overlay frames

#### Scenario: Neighbor court players are moving
- **WHEN** tracked people from an adjacent court are confidently detected, persist across frames, and show active match movement
- **THEN** the backend excludes them from target-court renderable overlay frames when their target-court membership and group consistency scores identify them as non-target-court candidates

#### Scenario: Person is clearly far from the match scene
- **WHEN** a tracked person is confidently detected but is clearly outside a broad match-scene sanity region or otherwise fails primary-player track quality checks
- **THEN** the backend may exclude that person from renderable overlay frames without treating normal court-line movement as invalid
