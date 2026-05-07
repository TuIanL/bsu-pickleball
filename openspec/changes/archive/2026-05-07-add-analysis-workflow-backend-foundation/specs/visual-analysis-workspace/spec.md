## ADDED Requirements

### Requirement: Job-specific visual analysis data
The system SHALL allow the visual analysis workspace to render completed analysis job data in addition to the existing demo data.

#### Scenario: User opens visual analysis for a completed job
- **WHEN** the user navigates to a visual analysis route associated with a completed analysis job
- **THEN** the video analysis card, timeline markers, overlay labels, highlights, coach notes, shot explorer, and report actions render from that job's analysis report payload

#### Scenario: User opens visual analysis without job context
- **WHEN** the user navigates to the existing demo visual analysis route without a job identifier
- **THEN** the workspace continues to render the local demo analysis data

### Requirement: Job-aware visual analysis states
The system SHALL communicate when a job-specific visual analysis result is not ready or cannot be loaded.

#### Scenario: User opens visual analysis before completion
- **WHEN** the user opens a visual analysis route for a job that is queued or processing
- **THEN** the system routes back to or displays the job status state instead of showing incomplete report visuals

#### Scenario: User opens visual analysis for a failed job
- **WHEN** the user opens a visual analysis route for a failed job
- **THEN** the system shows a stable failed-analysis state with a return or retry action

#### Scenario: User opens visual analysis for an unknown job
- **WHEN** the user opens a visual analysis route for a job identifier that cannot be found
- **THEN** the system shows a stable not-found or fallback state without broken overlays

### Requirement: Result-source clarity
The system SHALL distinguish demo analysis from job-specific analysis without disrupting the visual hierarchy.

#### Scenario: User views demo analysis
- **WHEN** the visual analysis workspace is rendering local demo data
- **THEN** the system provides a subtle demo/sample indication in the page context or metadata

#### Scenario: User views job-specific analysis
- **WHEN** the visual analysis workspace is rendering a completed job result
- **THEN** the system shows job or match metadata associated with the uploaded video
