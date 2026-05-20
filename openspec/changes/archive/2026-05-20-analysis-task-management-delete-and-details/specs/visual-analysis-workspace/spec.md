## MODIFIED Requirements

### Requirement: Job-specific visual analysis data
The system SHALL allow the visual analysis workspace to render completed analysis job video and status data from backend report payloads, available MVP pipeline algorithm results, and person/pose overlay artifacts in addition to the existing demo data.

#### Scenario: User opens visual analysis for a completed real job
- **WHEN** the user navigates to a visual analysis route associated with a completed uploaded-video analysis job
- **THEN** the video analysis card, source video, person detection overlay status, pose overlay status, timeline markers, and status rail render from that job's report payload, algorithm-derived fields, and available detection or pose overlays

#### Scenario: Completed real job only has limited algorithm output
- **WHEN** the completed job lacks calibration, projected tracks, supported MVP metrics, detection boxes, or pose keypoints
- **THEN** the workspace shows limited or unavailable states in the status rail and lower-level analysis views instead of filling modules with unrelated demo shot, landing, ball, or tactical labels

#### Scenario: User opens visual analysis without job context
- **WHEN** the user navigates to the existing demo visual analysis route without a job identifier
- **THEN** the workspace continues to render the local demo analysis data with clear sample context

### Requirement: Video workspace report actions
The system SHALL present compact lower-level result actions from the visual analysis workspace without exposing removed landing or ball-capture analysis as current real-job reports.

#### Scenario: User views result actions
- **WHEN** the user reviews a completed job-specific video analysis workspace
- **THEN** the status rail or adjacent secondary navigation shows actions for analysis details and currently supported movement or diagnosis views rather than a landing report action

#### Scenario: User selects a result action
- **WHEN** the user clicks analysis details from a completed job-specific result
- **THEN** the system navigates to `/analysis/:jobId/details`

#### Scenario: User selects a supported report action
- **WHEN** the user clicks a currently supported report action from a completed job-specific result
- **THEN** the system navigates to the matching job-specific `/analysis/:jobId/reports/:type` report detail page or equivalent lower-level tab state

## REMOVED Requirements

### Requirement: Synchronized ball overlay playback
**Reason**: Ball capture and trajectory analysis are being removed from the active product flow until a later implementation can support reliable ball detection, coordinate conversion, and event semantics.
**Migration**: Use person detection, pose, player tracking, and the new analysis details court plan as the active visualization path. Reintroduce ball overlay playback in a future dedicated change if ball artifacts are restored.

### Requirement: Ball overlay source clarity
**Reason**: Real-job ball overlay states and partial ball trajectory claims should not be shown while ball capture analysis is intentionally out of scope.
**Migration**: Real-job workspaces SHALL omit ball overlay rows, controls, and rendered ball points. Demo-only shot visuals may remain only when clearly labeled as sample content.

### Requirement: Ball overlay controls
**Reason**: There is no active real-job ball layer to toggle after ball capture analysis is removed.
**Migration**: Keep independent toggles for supported real overlays such as person boxes and pose skeletons. Add ball controls back only with a future ball-capture capability.
