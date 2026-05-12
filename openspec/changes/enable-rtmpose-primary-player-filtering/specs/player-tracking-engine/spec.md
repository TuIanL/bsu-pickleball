## ADDED Requirements

### Requirement: Primary-player overlay subject selection
The backend SHALL select renderable overlay subjects from tracked people using a primary-player score based on detection confidence and track quality rather than using standard court-line bounds as the primary visibility rule.

#### Scenario: High-confidence match players are selected
- **WHEN** a processed frame contains tracked people with high detection confidence and stable recent track history
- **THEN** the backend includes those tracks in renderable overlay frames up to the configured participant limit

#### Scenario: Low-confidence incidental detections are dropped
- **WHEN** a processed frame contains tracked people whose detection confidence or track quality falls below the configured primary-player selection threshold
- **THEN** the backend excludes those tracks from renderable overlay frames while preserving raw detection or tracking diagnostics where available

#### Scenario: Player steps outside court lines
- **WHEN** a tracked player has high confidence and primary-player track quality but their projected footpoint is slightly outside the standard court lines during normal match movement
- **THEN** the backend keeps that track eligible for renderable overlay frames instead of hiding it solely because it is line-out

#### Scenario: Frame contains more tracked people than match participants
- **WHEN** a frame contains more eligible tracked people than the configured player count for the match context
- **THEN** the backend keeps the highest-ranked primary-player tracks and excludes lower-ranked incidental tracks from renderable overlay frames

#### Scenario: Person is clearly far from the match scene
- **WHEN** a tracked person is confidently detected but is clearly outside a broad match-scene sanity region or otherwise fails primary-player track quality checks
- **THEN** the backend may exclude that person from renderable overlay frames without treating normal court-line movement as invalid

## MODIFIED Requirements

### Requirement: Detection overlay artifact
The backend SHALL expose a tracking or detection overlay artifact for completed real jobs that processed video frames, and renderable overlay boxes SHALL be limited to selected primary-player tracked subjects derived from confidence and track quality.

#### Scenario: Tracking artifact is generated
- **WHEN** a real job runs YOLO detection and tracking
- **THEN** the raw pipeline result references a JSON artifact containing frame-indexed boxes and track labels for selected primary-player tracks

#### Scenario: Primary-player filtering is applied
- **WHEN** YOLO detects people beyond the selected primary-player set for a processed frame
- **THEN** those people are excluded from renderable detection overlay frames while raw detection and tracking internals may still record model output for diagnostics

#### Scenario: Player is line-out but still primary
- **WHEN** a tracked match player remains high-confidence and primary-ranked while stepping outside the standard court lines
- **THEN** the backend keeps that player eligible for renderable overlay boxes

#### Scenario: Artifact path is not browser-safe
- **WHEN** the backend stores overlay artifacts on the local filesystem
- **THEN** the API exposes a browser-loadable artifact URL or endpoint instead of requiring the frontend to read local paths directly
