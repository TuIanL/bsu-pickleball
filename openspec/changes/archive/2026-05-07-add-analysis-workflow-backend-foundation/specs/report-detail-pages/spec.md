## ADDED Requirements

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
