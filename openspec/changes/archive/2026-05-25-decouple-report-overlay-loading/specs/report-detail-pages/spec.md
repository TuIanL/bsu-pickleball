## ADDED Requirements

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

## MODIFIED Requirements

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
