# visual-analysis-workspace Specification

## Purpose
TBD - created by archiving change build-layered-visual-analysis-platform. Update Purpose after archive.
## Requirements
### Requirement: Video-first analysis workspace
The system SHALL provide a dedicated visual analysis page centered on a simulated pickleball video player.

#### Scenario: User opens the visual analysis page
- **WHEN** the user navigates to `/vision`
- **THEN** the primary content is a large video-style analysis card with a 16:9 visual area, match score, current rally context, video controls, and timeline markers

#### Scenario: User views the simulated video layer
- **WHEN** the video analysis card is visible
- **THEN** the system shows a pickleball court mockup with court lines, kitchen zones, player markers or boxes, shot trajectories, landing or heat indicators, and AI labels

### Requirement: AI overlay labels
The system SHALL display contextual AI labels over the simulated video to explain important shot patterns and risks.

#### Scenario: User views active rally overlays
- **WHEN** an active rally is displayed in the visual analysis workspace
- **THEN** the system shows labels such as third-shot drop, high-risk drive, kitchen error, winning pattern, or equivalent original copy tied to mock rally events

### Requirement: Highlights and coach notes
The system SHALL pair video review with readable highlights and coach-like insights.

#### Scenario: User reviews coach notes
- **WHEN** the visual analysis page is visible
- **THEN** the system displays three to five AI coach notes covering strengths, risks, major errors, and training recommendations with distinct status treatments

#### Scenario: User reviews highlights
- **WHEN** key moments are available in mock data
- **THEN** the system displays a highlights list with rally title, time context, result or category, and an action affordance to inspect the moment

### Requirement: Rally timeline and shot filtering
The system SHALL include lightweight interaction for rally review and shot exploration without backend dependencies.

#### Scenario: User selects a shot filter chip
- **WHEN** the user clicks a shot filter such as All, Serve, Return, Third Shot, Dink, Drive, Reset, Volley, Smash, or Error
- **THEN** the selected chip visibly changes state and the displayed shot list or shot summary reflects that local selection

#### Scenario: User hovers timeline marker
- **WHEN** the user hovers or focuses a timeline marker
- **THEN** the system exposes a concise label or tooltip for the represented key event

### Requirement: Video workspace report actions
The system SHALL present clear report actions from the visual analysis workspace.

#### Scenario: User views report actions
- **WHEN** the user reviews the video analysis workspace
- **THEN** the system shows actions for landing analysis report, movement analysis report, rally tactics report, and motion diagnosis report

#### Scenario: User selects a report action
- **WHEN** the user clicks one of the report actions
- **THEN** the system navigates to the matching `/reports/:type` report detail page

### Requirement: Premium sports-tech visual style
The system SHALL make the visual analysis workspace feel like a mature AI sports video analytics product with a bright sports-tech theme.

#### Scenario: User views the visual analysis page
- **WHEN** the visual analysis page renders
- **THEN** the system uses bright primary surfaces, restrained green highlights, preserved blue/orange/red status accents, clean cards, subtle borders, hover states, and video-first hierarchy rather than a heavy dark interface or a generic admin-table layout

### Requirement: Job-specific visual analysis data
The system SHALL allow the visual analysis workspace to render completed analysis job data from backend report payloads and available MVP pipeline algorithm results in addition to the existing demo data.

#### Scenario: User opens visual analysis for a completed real job
- **WHEN** the user navigates to a visual analysis route associated with a completed uploaded-video analysis job
- **THEN** the video analysis card, timeline markers, overlay labels, highlights, coach notes, shot explorer, and report actions render from that job's report payload and algorithm-derived fields where available

#### Scenario: Completed real job only has limited algorithm output
- **WHEN** the completed job lacks calibration, projected tracks, or supported MVP metrics
- **THEN** the workspace shows a limited-analysis state for unavailable modules instead of filling those modules with unrelated demo shot or tactical labels

#### Scenario: User opens visual analysis without job context
- **WHEN** the user navigates to the existing demo visual analysis route without a job identifier
- **THEN** the workspace continues to render the local demo analysis data

### Requirement: Job-aware visual analysis states
The system SHALL communicate when a job-specific visual analysis result is not ready or cannot be loaded.

#### Scenario: User opens visual analysis before completion
- **WHEN** the user opens a visual analysis route for a job that is queued or processing
- **THEN** the system routes back to or displays the job status state instead of showing incomplete report visuals

#### Scenario: User opens visual analysis for a failed job
- **WHEN** the user opens a visual analysis route for a failed job
- **THEN** the system shows a stable failed-analysis state with a return or retry action

#### Scenario: User opens visual analysis for an unknown job
- **WHEN** the user opens a visual analysis route for a job identifier that cannot be found
- **THEN** the system shows a stable not-found or fallback state without broken overlays

### Requirement: Result-source clarity
The system SHALL distinguish demo analysis, limited real analysis, and algorithm-derived job analysis without disrupting the visual hierarchy.

#### Scenario: User views demo analysis
- **WHEN** the visual analysis workspace is rendering local demo data
- **THEN** the system provides a subtle demo/sample indication in the page context or metadata

#### Scenario: User views algorithm-derived job analysis
- **WHEN** the visual analysis workspace is rendering a completed uploaded-video job with pipeline output
- **THEN** the system shows job, match, uploaded video, calibration, and generated result metadata associated with the analysis

#### Scenario: User views limited job analysis
- **WHEN** the visual analysis workspace is rendering a completed job that lacks enough algorithm output for a module
- **THEN** the system labels the affected module as unavailable or limited and explains the missing prerequisite such as calibration or detections

### Requirement: Algorithm-backed movement visualization
The system SHALL visualize available player movement and court coverage data from backend pipeline results in the visual analysis workspace.

#### Scenario: Projected tracks are available
- **WHEN** a completed real analysis job includes projected player tracks
- **THEN** the workspace renders movement paths, player positions, or heat distribution from those tracks rather than static demo coordinates

#### Scenario: Movement metrics are available
- **WHEN** a completed real analysis job includes distance, speed, kitchen dwell, doubles spacing, or heatmap metrics
- **THEN** the workspace presents movement-focused feedback derived from those metrics with readable labels and values

#### Scenario: No detections are produced
- **WHEN** the backend pipeline completes but produces no usable player detections or projected positions
- **THEN** the workspace shows an analysis-completed-but-no-tracks state with guidance to check camera angle, calibration, model setup, or video quality

