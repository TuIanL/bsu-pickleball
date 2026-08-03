# visual-analysis-workspace Specification Delta

## MODIFIED Requirements

### Requirement: Algorithm-backed movement visualization

The system SHALL visualize available player movement and court coverage data from backend pipeline results in the visual analysis workspace, including synchronized movement paths and current-position summaries in the video analysis HUD when projected tracks are available.

#### Scenario: Projected tracks are available

- **WHEN** a completed real analysis job includes projected player tracks
- **THEN** the workspace renders movement paths, current player positions, direction indicators, or heat distribution from those tracks rather than static demo coordinates
- **AND** the video HUD identifies stable player labels and uses a time window tied to the current video playback time

#### Scenario: Movement metrics are available

- **WHEN** a completed real analysis job includes distance, speed, kitchen dwell, doubles spacing, or heatmap metrics
- **THEN** the workspace presents movement-focused feedback derived from those metrics with readable labels and values
- **AND** the HUD MAY show a compact current-position or speed summary without replacing the detailed report metrics

#### Scenario: Movement track has a data gap

- **WHEN** a projected player track contains a timestamp gap beyond the safe interpolation/connection threshold
- **THEN** the workspace breaks the displayed movement path at the gap and communicates the missing or degraded coverage instead of drawing a misleading connecting line

#### Scenario: No detections are produced

- **WHEN** the backend pipeline completes but produces no usable player detections or projected positions
- **THEN** the workspace shows an analysis-completed-but-no-tracks state with guidance to check camera angle, calibration, model setup, or video quality
- **AND** the workspace does not render simulated player positions in the real-job HUD

### Requirement: Fullscreen real-video overlay playback

The visual analysis workspace SHALL provide fullscreen playback for real uploaded-video jobs without losing visible person boxes, skeleton joints, independently controlled HUD layers, or overlay status labels.

#### Scenario: User enters fullscreen real-video playback

- **WHEN** a user opens fullscreen playback from a completed real-job video that has detection, pose, player-track, ball, or bounce data
- **THEN** the fullscreen surface includes the source video, enabled overlay layers, the synchronized court HUD when data is available, layer toggles, and playback status labels in the same aligned visual area

#### Scenario: Fullscreen preserves HUD geometry

- **WHEN** the user enters or exits fullscreen while a court HUD is visible
- **THEN** the HUD preserves the standard court aspect ratio, remains within the video content area, and does not overlap the primary playback controls

#### Scenario: Fullscreen is unavailable

- **WHEN** the browser does not support fullscreen for the video overlay container
- **THEN** the workspace keeps inline playback usable and does not hide or break existing overlays or HUD status
