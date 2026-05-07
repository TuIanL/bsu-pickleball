# layered-product-navigation Specification

## Purpose
TBD - created by archiving change build-layered-visual-analysis-platform. Update Purpose after archive.
## Requirements
### Requirement: Layered page architecture
The system SHALL provide a layered product structure with distinct pages for overview, visual analysis, report detail, training recommendations, and hardware fusion.

#### Scenario: User opens the overview page
- **WHEN** the user loads the application root
- **THEN** the system presents a concise product overview with entry points to visual analysis, report details, training recommendations, and hardware fusion

#### Scenario: User navigates to a top-level page
- **WHEN** the user selects Vision, Reports, Training, or Hardware from navigation
- **THEN** the system displays the corresponding page without stacking all platform sections into one long scrolling page

### Requirement: Top navigation for core workflows
The system SHALL include a consistent top navigation that exposes the main product workflows and primary actions.

#### Scenario: User views desktop navigation
- **WHEN** the application is displayed on a desktop viewport
- **THEN** the navigation shows the product identity, links for Dashboard, Matches or Vision, Shot Explorer or Reports, Progress, Drills or Training, Coach Mode, a secondary demo action, a primary upload or analysis action, and user or team context

#### Scenario: User views narrow navigation
- **WHEN** the application is displayed on a narrow viewport
- **THEN** navigation remains usable without text overlap or horizontal page scrolling

### Requirement: Report entry flow
The system SHALL allow the visual analysis page to route users into focused report pages for specific analysis types.

#### Scenario: User opens a report from visual analysis
- **WHEN** the user clicks a report entry for landing analysis, movement analysis, rally tactics, or motion diagnosis
- **THEN** the system opens the matching report detail page for that report type

#### Scenario: User opens an unsupported report type
- **WHEN** the current route or selected report type does not match a supported report definition
- **THEN** the system provides a stable fallback to the overview or default report page instead of rendering a broken state

### Requirement: Independent product identity
The system SHALL use original product naming, icons, copy, mock visuals, and interaction labels.

#### Scenario: User views brand and visual assets
- **WHEN** the application renders navigation, hero content, video mockups, cards, icons, and CTAs
- **THEN** the system does not display PB Vision or SwingVision logos, brand names, original imagery, original icons, or original marketing copy

### Requirement: Presentation-ready responsive layout
The system SHALL keep the layered product pages polished and legible across common desktop and mobile viewports.

#### Scenario: User captures a desktop screenshot
- **WHEN** the application is viewed on a desktop viewport
- **THEN** the page presents a premium AI sports analytics layout with clear hierarchy, stable spacing, no incoherent overlap, and a strong first-screen visual signal

#### Scenario: User views the product on mobile
- **WHEN** the application is viewed on a mobile viewport
- **THEN** page sections stack or condense into stable layouts while preserving readable text, accessible controls, and constrained visualization dimensions

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

