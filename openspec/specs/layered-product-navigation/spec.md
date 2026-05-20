# layered-product-navigation Specification

## Purpose
TBD - created by archiving change build-layered-visual-analysis-platform. Update Purpose after archive.
## Requirements
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
The system SHALL allow completed analysis results to route users into supported lower-level result pages while directing general task details to the analysis details page.

#### Scenario: User opens analysis details from a completed task
- **WHEN** the user clicks a completed task's analysis details action from task management or a completed job context
- **THEN** the system opens the job-specific analysis details page for that task

#### Scenario: User opens a supported report from visual analysis
- **WHEN** the user clicks a supported movement or diagnosis report action from a completed result context
- **THEN** the system opens the matching job-specific report detail page for that report type

#### Scenario: User opens an unsupported or removed report type
- **WHEN** the current route or selected report type does not match a supported current report definition such as removed landing analysis
- **THEN** the system provides a stable fallback to the analysis details page, task management, or an available report page instead of rendering a broken state

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
- **THEN** the primary video analysis action routes to the new analysis upload workflow rather than directly opening the completed-result workspace

#### Scenario: User starts analysis from overview
- **WHEN** the user selects the overview page action to analyze a new match
- **THEN** the system opens the new analysis upload workflow rather than only navigating to the demo visual workspace

#### Scenario: User opens task history
- **WHEN** the user selects an analysis task history action from navigation or the upload workflow
- **THEN** the system opens the analysis task management page

### Requirement: Job-specific route support
The system SHALL support route states for analysis jobs, job-specific result pages, and job-specific analysis details.

#### Scenario: User opens job status route
- **WHEN** the user navigates to a route representing an analysis job identifier
- **THEN** the app shell preserves navigation context and renders the analysis job status page

#### Scenario: User opens job-specific visual route
- **WHEN** the user navigates to a route representing visual analysis for a specific job identifier
- **THEN** the app shell renders the visual analysis workspace with that job context

#### Scenario: User opens job-specific details route
- **WHEN** the user navigates to `/analysis/:jobId/details`
- **THEN** the app shell renders the analysis details page with that job context

#### Scenario: User opens job-specific report route
- **WHEN** the user navigates to a route representing a currently supported report type for a specific job identifier
- **THEN** the app shell renders the matching report detail page with that job context
