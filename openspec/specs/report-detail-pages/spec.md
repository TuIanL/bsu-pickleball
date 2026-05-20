# report-detail-pages Specification

## Purpose
TBD - created by archiving change build-layered-visual-analysis-platform. Update Purpose after archive.
## Requirements
### Requirement: Typed report detail pages
The system SHALL provide focused report pages for supported analysis types.

#### Scenario: User opens landing report
- **WHEN** the user opens `/reports/landing`
- **THEN** the system presents landing or placement analysis with metrics, court heat or landing visualization, and coach-readable interpretation

#### Scenario: User opens movement report
- **WHEN** the user opens `/reports/movement`
- **THEN** the system presents movement or court coverage analysis with metrics, path or balance visualization, and coach-readable interpretation

#### Scenario: User opens rally report
- **WHEN** the user opens `/reports/rally`
- **THEN** the system presents rally tactics analysis with rally-level metrics, shot pattern summaries, and tactical interpretation

#### Scenario: User opens diagnosis report
- **WHEN** the user opens `/reports/diagnosis`
- **THEN** the system presents motion diagnosis content with evidence, severity, suggested correction, and links to relevant training recommendations

### Requirement: Report metrics and interpretation
Each report detail page SHALL pair numeric metrics with explanatory coaching context.

#### Scenario: User reads a report page
- **WHEN** a report detail page is displayed
- **THEN** the system shows core metrics, trend or comparison context, and at least one explanatory insight that translates data into action

### Requirement: Report visualizations
Report detail pages SHALL include visual analysis elements appropriate to the selected report type.

#### Scenario: User views a report visualization
- **WHEN** a report detail page is displayed
- **THEN** the system shows a chart, mini court map, heat visualization, route visualization, movement path, skill rating, or equivalent visual module that matches the selected report type

### Requirement: Report-to-training bridge
Report detail pages SHALL provide a clear path from findings to recommended practice.

#### Scenario: User sees a trainable weakness
- **WHEN** a report detail page identifies a weakness or improvement area
- **THEN** the system shows a training recommendation link or action related to that finding

### Requirement: Local mock report data
Report detail pages SHALL render from structured local mock data.

#### Scenario: Developer replaces mock report data later
- **WHEN** report definitions, metrics, insights, visualizations, and training links are inspected
- **THEN** they are represented as structured data objects rather than hard-coded unrelated page fragments

### Requirement: Job-specific report data
Report detail pages SHALL render completed analysis job report data in addition to the existing local sample report data.

#### Scenario: User opens a completed job report
- **WHEN** the user opens landing, movement, rally, or diagnosis report detail for a completed analysis job
- **THEN** the page renders metrics, visualization data, insights, and training links from that job's analysis report payload

#### Scenario: User opens a sample report
- **WHEN** the user opens the existing sample report route without a job identifier
- **THEN** the page continues to render structured local mock report data

### Requirement: Job-aware report states
Report detail pages SHALL communicate when job-specific report data is unavailable.

#### Scenario: User opens a report before job completion
- **WHEN** the user opens a report route for a job that is queued or processing
- **THEN** the system routes back to or displays the job status state instead of rendering incomplete report data

#### Scenario: User opens a report for a failed job
- **WHEN** the user opens a report route for a failed analysis job
- **THEN** the page shows a stable failed-analysis state with a return or retry action

#### Scenario: User opens an unknown job report
- **WHEN** the user opens a report route for a job identifier that cannot be found
- **THEN** the page shows a stable not-found or fallback state without rendering broken report modules

### Requirement: Report source metadata
Report detail pages SHALL show enough context for users to understand which match or analysis job produced the report.

#### Scenario: User views a job-specific report
- **WHEN** a report detail page renders completed job data
- **THEN** the page displays match metadata such as uploaded file label, venue, date, player context, report id, or job id where available

#### Scenario: User views a demo report
- **WHEN** a report detail page renders local sample data
- **THEN** the page preserves a subtle sample or demo context instead of implying the result came from an uploaded video

### Requirement: Result-scoped report navigation
Report detail pages SHALL behave as lower-level destinations reached from completed video analysis results or task management rather than as primary top-navigation peers.

#### Scenario: User opens a report from completed result
- **WHEN** the user selects landing, movement, rally, or diagnosis from a completed job's status rail, report tabs, or task card
- **THEN** the system opens the matching job-specific report detail route with the completed task context preserved

#### Scenario: User returns from report to video result
- **WHEN** the user activates the report page's return action
- **THEN** the system navigates back to the associated job-specific visual analysis page when a job id is available

#### Scenario: User opens sample report route directly
- **WHEN** the user navigates directly to an existing sample report route without a job identifier
- **THEN** the system continues to render structured local mock report data with subtle sample context

