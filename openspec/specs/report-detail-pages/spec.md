# report-detail-pages Specification

## Purpose
TBD - created by archiving change build-layered-visual-analysis-platform. Update Purpose after archive.
## Requirements
### Requirement: Typed report detail pages
The system SHALL provide focused report pages for supported analysis types.

#### Scenario: User opens movement report
- **WHEN** the user opens `/reports/movement`
- **THEN** the system presents movement or court coverage analysis with metrics, path or balance visualization, and coach-readable interpretation

#### Scenario: User opens diagnosis report
- **WHEN** the user opens `/reports/diagnosis`
- **THEN** the system presents motion diagnosis content with evidence, severity, suggested correction, and links to relevant training recommendations

#### Scenario: User opens a removed landing report
- **WHEN** the user opens `/reports/landing`
- **THEN** the system shows a stable fallback or redirects to the analysis details page instead of rendering a current real-job landing analysis

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
Report detail pages SHALL render completed analysis job report data in addition to the existing local sample report data, using the lightweight generated report payload as the primary source for job-specific report pages.

#### Scenario: User opens a completed job report
- **WHEN** the user opens movement or diagnosis report detail for a completed analysis job
- **THEN** the page renders metrics, visualization data, insights, and training links from that job's analysis report payload without requiring raw algorithm result or overlay artifact downloads

#### Scenario: User opens a sample report
- **WHEN** the user opens the existing sample report route without a job identifier
- **THEN** the page continues to render structured local mock report data

### Requirement: Job-aware report states
Report detail pages SHALL communicate when job-specific report data is unavailable and distinguish report loading from visual overlay loading.

#### Scenario: User opens a report before job completion
- **WHEN** the user opens a report route for a job that is queued or processing
- **THEN** the system routes back to or displays the job status state instead of rendering incomplete report data

#### Scenario: User opens a report for a failed job
- **WHEN** the user opens a report route for a failed analysis job
- **THEN** the page shows a stable failed-analysis state with a return or retry action

#### Scenario: User opens an unknown job report
- **WHEN** the user opens a report route for a job identifier that cannot be found
- **THEN** the page shows a stable not-found or fallback state without rendering broken report modules

#### Scenario: User waits for report data
- **WHEN** a job-specific report page is waiting for the job summary or generated report payload
- **THEN** the loading state communicates that report data is being read and does not imply that heavyweight video overlay artifacts must finish loading first

### Requirement: Lightweight job report loading
Job-specific report detail pages SHALL render from the completed job summary and generated report payload without waiting for raw algorithm results, source video streams, tracking overlays, or pose overlay artifacts that are not required by the selected report page.

#### Scenario: Completed job report opens while large overlays exist
- **WHEN** the user opens `/analysis/:jobId/reports/:type` for a completed job whose generated report payload is available and whose overlay artifacts are large or slow to download
- **THEN** the report page renders the selected report content from the job/report payload without waiting for those overlay artifacts

#### Scenario: Report payload is still unavailable
- **WHEN** the user opens a job-specific report route and the job summary is found but the generated report payload is not available
- **THEN** the system shows a report-unavailable or still-generating state rather than blocking indefinitely on visual overlay artifacts

#### Scenario: Overlay artifact fails while report payload is available
- **WHEN** the user opens a job-specific report route and a tracking or pose overlay artifact would fail to load
- **THEN** the report page still renders from the available report payload unless the selected report explicitly requires that artifact

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
- **WHEN** the user selects movement or diagnosis from a completed job's status rail, report tabs, or task card
- **THEN** the system opens the matching job-specific report detail route with the completed task context preserved

#### Scenario: User returns from report to video result
- **WHEN** the user activates the report page's return action
- **THEN** the system navigates back to the associated job-specific visual analysis page when a job id is available

#### Scenario: User opens sample report route directly
- **WHEN** the user navigates directly to an existing sample report route without a job identifier
- **THEN** the system continues to render structured local mock report data with subtle sample context
