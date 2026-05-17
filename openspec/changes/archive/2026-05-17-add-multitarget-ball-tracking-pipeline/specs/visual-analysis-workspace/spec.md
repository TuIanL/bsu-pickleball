## ADDED Requirements

### Requirement: Synchronized ball overlay playback
The visual analysis workspace SHALL render backend-generated ball points and ball trajectories over uploaded source video for completed real jobs when ball overlay data is available.

#### Scenario: Ball overlay data is available
- **WHEN** the user plays or scrubs a completed real-job video with frame-indexed ball overlay data
- **THEN** the workspace draws the matching playback frame's ball point or trajectory segment aligned to the rendered video frame

#### Scenario: Ball trajectory includes repaired points
- **WHEN** the ball overlay artifact includes observed and repaired or predicted trajectory points
- **THEN** the workspace renders the point sources with distinguishable visual treatment or labels so repaired motion is not presented as direct detection

#### Scenario: Video is resized or letterboxed
- **WHEN** the video display size differs from the source frame dimensions
- **THEN** ball overlay coordinates are transformed into rendered video coordinates without drifting into letterbox areas

### Requirement: Ball overlay source clarity
The visual analysis workspace SHALL distinguish real ball overlays from demo shot trajectories and unavailable ball-tracking output.

#### Scenario: Real ball overlay is unavailable
- **WHEN** a completed real job has no available ball overlay artifact
- **THEN** the workspace does not render demo shot trajectories as real ball data and shows a clear unavailable or skipped state for ball tracking

#### Scenario: Real ball overlay is partial
- **WHEN** a completed real job has partial ball trajectory data
- **THEN** the workspace can render available points while communicating the partial status from the backend artifact detail

#### Scenario: Demo analysis is shown
- **WHEN** the visual analysis workspace is rendering local demo data without a real job context
- **THEN** existing simulated shot paths may remain visible as demo visuals and are not labeled as uploaded-video ball tracking

### Requirement: Ball overlay controls
The visual analysis workspace SHALL provide user controls for showing or hiding real ball overlays independently from player boxes and skeleton overlays when ball data is available.

#### Scenario: User toggles ball overlay
- **WHEN** real ball overlay data is loaded and the user changes the ball overlay control
- **THEN** the workspace hides or shows ball points and trajectory segments without changing video playback, player boxes, skeletons, or loaded artifact state
