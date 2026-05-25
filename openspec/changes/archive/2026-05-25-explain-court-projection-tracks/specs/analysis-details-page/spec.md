## ADDED Requirements

### Requirement: Projected track explanation
The analysis details page SHALL explain the semantics of projected court marks whenever completed analysis data includes projected player positions.

#### Scenario: User views projected court marks
- **WHEN** the analysis details page renders a completed job with projected player positions
- **THEN** the court visualization identifies plotted points as estimated player footpoints projected from video image space into the standard 20 ft by 44 ft court coordinate system

#### Scenario: User needs to distinguish movement from other events
- **WHEN** projected player positions are displayed alongside any report, metric, or status context
- **THEN** the page distinguishes projected player movement marks from ball contacts, shot landing points, and manually annotated events

#### Scenario: Tracker identity is uncertain
- **WHEN** the page labels projected movement by raw tracker output
- **THEN** it communicates that track labels represent detected movement tracks and are not guaranteed named player identities across the whole video

### Requirement: Projected track legend and filtering
The analysis details page SHALL group projected player positions by track and provide readable controls for identifying and filtering those tracks.

#### Scenario: Multiple tracks are available
- **WHEN** a completed job provides projected positions for more than one track
- **THEN** the court visualization renders distinguishable per-track paths or points and shows a legend with stable display labels for each visible track

#### Scenario: User selects one track
- **WHEN** the user selects a track from the legend or track controls
- **THEN** the court emphasizes that track and reduces visual prominence of unselected tracks without losing the ability to return to the broader view

#### Scenario: Result contains short noisy track fragments
- **WHEN** projected positions include many low-persistence or very short track fragments
- **THEN** the page provides a way to hide or de-emphasize those fragments while preserving access to the full projected data context

#### Scenario: Track summaries are shown
- **WHEN** projected tracks are available
- **THEN** each displayed track summary includes enough context to compare tracks, such as point count, visible time range, and confidence or persistence context

### Requirement: Projected point inspection
The analysis details page SHALL allow users to inspect representative projected points or selected track details with source timing and reliability context.

#### Scenario: User inspects a projected point
- **WHEN** the user hovers, clicks, or otherwise focuses a projected point
- **THEN** the page shows the point's track label, timestamp or frame, court coordinate, and confidence when those fields are available

#### Scenario: User inspects start and latest positions
- **WHEN** a visible track is rendered on the court plan
- **THEN** the visualization distinguishes the track's start and latest rendered positions from intermediate points

#### Scenario: No projected positions are available
- **WHEN** a completed job lacks valid projected player positions
- **THEN** the court plan explains the missing prerequisite or unavailable projected-data state instead of rendering unlabeled placeholder movement marks

### Requirement: Projected court rendering performance
The analysis details page SHALL keep projected court rendering responsive for real analysis results that contain many projected points or fragmented tracks.

#### Scenario: Large projected result is opened
- **WHEN** a completed job contains thousands of projected points or many track identifiers
- **THEN** the page renders a bounded representative visualization without blocking the rest of the analysis details page

#### Scenario: Rendered points are sampled
- **WHEN** the page samples or caps points for drawing performance
- **THEN** the track summaries continue to reflect the complete available projected data rather than only the sampled drawing subset
