## ADDED Requirements

### Requirement: Analysis workflow navigation
The system SHALL expose the real-analysis workflow from the main product navigation and overview entry points.

#### Scenario: User views primary analysis action
- **WHEN** the user views the app shell on a desktop or narrow viewport
- **THEN** the primary analysis action routes to the new analysis or upload workflow

#### Scenario: User starts analysis from overview
- **WHEN** the user selects the overview page action to analyze a new match
- **THEN** the system opens the new analysis workflow rather than only navigating to the demo visual workspace

### Requirement: Job-specific route support
The system SHALL support route states for analysis jobs and job-specific result pages.

#### Scenario: User opens job status route
- **WHEN** the user navigates to a route representing an analysis job identifier
- **THEN** the app shell preserves navigation context and renders the analysis job status page

#### Scenario: User opens job-specific visual route
- **WHEN** the user navigates to a route representing visual analysis for a specific job identifier
- **THEN** the app shell renders the visual analysis workspace with that job context

#### Scenario: User opens job-specific report route
- **WHEN** the user navigates to a route representing a report type for a specific job identifier
- **THEN** the app shell renders the matching report detail page with that job context
