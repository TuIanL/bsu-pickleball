## ADDED Requirements

### Requirement: Real ball layer playback
The visual analysis workspace SHALL load and render real ball trajectory, ball overlay, and bounce candidate layers for completed uploaded-video jobs when the corresponding artifacts are available.

#### Scenario: Ball trajectory artifact is available
- **WHEN** a completed real job references a valid ball trajectory or cleaned ball trajectory artifact
- **THEN** the workspace SHALL fetch the artifact independently from the source video shell
- **AND** the workspace SHALL render a synchronized ball path or current ball marker using uploaded-video coordinates

#### Scenario: Bounce candidates are available
- **WHEN** a completed real job references `bounce_events.json` with candidate events
- **THEN** the workspace SHALL render timeline markers or court/video markers as candidate bounce events
- **AND** the workspace MUST NOT label them as confirmed scoring, landing, fault, or tactical outcomes

#### Scenario: Ball layer is unavailable
- **WHEN** a completed real job has no ball artifact because configuration is disabled, dependencies are missing, detection found no candidates, or the stage failed
- **THEN** the workspace SHALL show a layer state matching skipped, unavailable, no-detection, partial, or failed
- **AND** the workspace MUST NOT render demo ball paths as real job output

### Requirement: Ball layer controls preserve existing overlays
The visual analysis workspace SHALL allow ball-related layers to coexist with source video, person boxes, skeleton overlays, serve markers, and status rail actions.

#### Scenario: User toggles ball layer
- **WHEN** ball trajectory or ball overlay data is available and the user toggles the ball layer
- **THEN** the workspace hides or shows the ball layer without changing video playback, person boxes, skeleton state, or loaded artifact status

#### Scenario: Ball artifact request fails
- **WHEN** the ball layer artifact request fails after the completed job shell has loaded
- **THEN** the workspace marks only the ball layer as failed
- **AND** source video, person boxes, skeleton overlay, report navigation, and status rail remain usable
