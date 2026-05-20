# analysis-details-page Specification

## Purpose
TBD - created by archiving change analysis-task-management-delete-and-details. Update Purpose after archive.
## Requirements
### Requirement: Job-specific analysis details page
The system SHALL provide a job-specific analysis details page for completed analysis jobs.

#### Scenario: User opens completed analysis details
- **WHEN** the user opens `/analysis/:jobId/details` for a completed analysis job
- **THEN** the page shows the job's match metadata, uploaded file label, analysis mode, generated timestamps, status summary, and available algorithm result context

#### Scenario: User opens details before completion
- **WHEN** the user opens `/analysis/:jobId/details` for a job that is uploaded, queued, or processing
- **THEN** the system displays or routes to the job status state instead of rendering final analysis details

#### Scenario: User opens details for a failed job
- **WHEN** the user opens `/analysis/:jobId/details` for a failed analysis job
- **THEN** the page shows a stable failed-analysis state with failure context and actions to return to task management or upload a new video

#### Scenario: User opens details for an unknown job
- **WHEN** the user opens `/analysis/:jobId/details` for a job identifier that cannot be found
- **THEN** the page shows a stable not-found state without broken visualizations

### Requirement: Standard pickleball court plan
The analysis details page SHALL render a standard two-dimensional pickleball court plan as the primary future visualization surface.

#### Scenario: Standard court is displayed
- **WHEN** the analysis details page renders
- **THEN** it shows a 20 ft by 44 ft court plan with outer boundary, net line at 22 ft, non-volley-zone lines at 15 ft and 29 ft, center service lines, and near/far service boxes

#### Scenario: Court plan adapts to viewport
- **WHEN** the details page is viewed on desktop or narrow screens
- **THEN** the court plan preserves its geometry aspect ratio, labels remain legible, and controls or metadata do not overlap the court

#### Scenario: Movement projection is not ready
- **WHEN** player coordinate conversion or displacement tracks are not yet available
- **THEN** the court plan shows an explicit empty or pending visualization state rather than fabricated movement paths

### Requirement: Future player movement projection handoff
The analysis details page SHALL reserve a structured handoff for future player movement visualization on the standard court plan.

#### Scenario: Projected tracks become available later
- **WHEN** a completed job provides projected player positions in standard court coordinates
- **THEN** the details page can render player positions, paths, or heat layers on the same 20 ft by 44 ft court coordinate system without changing the route

#### Scenario: Job lacks calibration
- **WHEN** a completed job has no calibration or no valid projected court coordinates
- **THEN** the details page identifies the missing prerequisite and keeps the court plan in a non-projected state

