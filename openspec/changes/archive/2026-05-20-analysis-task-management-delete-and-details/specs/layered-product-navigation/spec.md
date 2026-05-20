## MODIFIED Requirements

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
