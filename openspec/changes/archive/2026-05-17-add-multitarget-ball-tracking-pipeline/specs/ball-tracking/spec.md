## ADDED Requirements

### Requirement: Ball detection artifact
The backend SHALL persist frame-indexed ball detection artifacts for completed real jobs when ball detection is configured and processed.

#### Scenario: Ball detections are available
- **WHEN** a calibrated real analysis job processes video frames and produces usable ball detections
- **THEN** the backend writes a ball detection artifact containing job/video identifiers, source frame dimensions, frame timing metadata, ball boxes or centers, confidence, and detector status

#### Scenario: No ball detections are produced
- **WHEN** ball detection runs but no usable ball candidates pass filtering
- **THEN** the backend exposes a no-detections ball artifact or status with guidance to check model configuration, video clarity, camera angle, or thresholds

#### Scenario: Ball detection is skipped
- **WHEN** ball detection cannot run because configuration or model assets are unavailable
- **THEN** the backend records an unavailable or skipped status and omits any available ball overlay URL

### Requirement: Ball trajectory continuity
The backend SHALL derive a ball trajectory from frame-indexed ball detections and mark each trajectory point by source and confidence.

#### Scenario: Consecutive ball detections are valid
- **WHEN** consecutive processed frames contain plausible ball detections
- **THEN** the trajectory artifact includes observed points ordered by timestamp with frame index, image coordinates, confidence, and source `observed`

#### Scenario: A short detection gap occurs
- **WHEN** a ball track has a short gap within the configured repair limit and surrounding detections support a plausible motion path
- **THEN** the trajectory artifact includes repaired or predicted points for the missing frames with reduced confidence and source `repaired` or `predicted`

#### Scenario: A long or implausible gap occurs
- **WHEN** the ball is missing beyond the configured repair limit or the implied speed/direction is implausible
- **THEN** the backend starts a new trajectory segment or marks the gap unresolved instead of fabricating continuous high-confidence motion

#### Scenario: Implausible ball candidate is detected
- **WHEN** a ball candidate violates configured size, speed, frame-bound, or confidence constraints
- **THEN** the backend excludes it from the primary trajectory and preserves diagnostic counts where available

### Requirement: Ball overlay artifact retrieval
The backend SHALL expose browser-loadable ball overlay artifact references through completed pipeline results when ball trajectory data is available.

#### Scenario: Ball trajectory artifact is available
- **WHEN** a completed real job has persisted ball trajectory data
- **THEN** the raw pipeline result includes ball overlay status, detail text, local artifact path, and a browser-loadable artifact URL

#### Scenario: Ball trajectory artifact is partial
- **WHEN** the job has some ball detections but insufficient continuity for a complete trajectory
- **THEN** the pipeline reports a partial ball overlay state with available points and an explanatory detail instead of failing the whole analysis

#### Scenario: Ball artifact is unavailable
- **WHEN** ball tracking is disabled, skipped, failed, or produces no usable data
- **THEN** clients receive an explicit unavailable or no-detections state rather than an empty artifact that appears successful

### Requirement: Ball tracking does not imply shot events
The system SHALL keep ball trajectory output separate from hit, bounce, rally, shot-type, and tactical event claims.

#### Scenario: Ball trajectory is available without events
- **WHEN** a completed real job includes ball trajectory points but no event-analysis artifact
- **THEN** reports and workspace UI may show the trajectory while labeling shot events, rally segmentation, and tactical conclusions as unavailable for the current phase
