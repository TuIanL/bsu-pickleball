## MODIFIED Requirements

### Requirement: Layered page architecture
The system SHALL provide a simplified layered product structure with a main page, a video-analysis task flow, job-specific visual results, subordinate report detail pages, and training recommendations.

#### Scenario: User opens the overview page
- **WHEN** the user loads the application root
- **THEN** the system presents a concise main page with primary entry points to video analysis upload, analysis task history, and training recommendations

#### Scenario: User navigates to a top-level page
- **WHEN** the user selects Home, Video Analysis, or Training from navigation
- **THEN** the system displays the corresponding main page, upload/task workflow, or training page without exposing reports and hardware as equal top-level peers

### Requirement: Top navigation for core workflows
The system SHALL include a consistent top navigation that exposes only the main product workflows and primary actions.

#### Scenario: User views desktop navigation
- **WHEN** the application is displayed on a desktop viewport
- **THEN** the navigation shows the product identity, links for the main page, video analysis, and training, plus clear upload and task-history actions when space allows

#### Scenario: User views narrow navigation
- **WHEN** the application is displayed on a narrow viewport
- **THEN** navigation remains usable without text overlap or horizontal page scrolling and still exposes the main page, video analysis, and training destinations

### Requirement: Report entry flow
The system SHALL allow completed analysis results to route users into focused report pages for specific analysis types.

#### Scenario: User opens a report from visual analysis
- **WHEN** the user clicks a report tab or report action for landing analysis, movement analysis, rally tactics, or motion diagnosis from a completed result context
- **THEN** the system opens the matching report detail page for that report type

#### Scenario: User opens an unsupported report type
- **WHEN** the current route or selected report type does not match a supported report definition
- **THEN** the system provides a stable fallback to the overview, task management, or default report page instead of rendering a broken state

### Requirement: Analysis workflow navigation
The system SHALL expose the real-analysis workflow from the main product navigation and overview entry points.

#### Scenario: User views primary analysis action
- **WHEN** the user views the app shell on a desktop or narrow viewport
- **THEN** the primary video analysis action routes to the new analysis upload workflow rather than directly opening the completed-result workspace

#### Scenario: User starts analysis from overview
- **WHEN** the user selects the overview page action to analyze a new match
- **THEN** the system opens the new analysis upload workflow rather than only navigating to the demo visual workspace

#### Scenario: User opens task history
- **WHEN** the user selects an analysis task history action from navigation or the upload workflow
- **THEN** the system opens the analysis task management page
