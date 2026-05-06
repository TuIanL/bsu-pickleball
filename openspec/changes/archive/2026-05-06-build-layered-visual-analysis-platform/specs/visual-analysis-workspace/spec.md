## ADDED Requirements

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
The system SHALL make the visual analysis workspace feel like a mature AI sports video analytics product.

#### Scenario: User views the visual analysis page
- **WHEN** the visual analysis page renders
- **THEN** the system uses a dark sports-tech theme, restrained bright green highlights, clean cards, subtle borders, hover states, and video-first hierarchy rather than a generic admin-table layout
