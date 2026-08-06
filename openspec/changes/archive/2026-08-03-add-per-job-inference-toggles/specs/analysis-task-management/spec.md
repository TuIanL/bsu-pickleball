## ADDED Requirements

### Requirement: Analysis task inference toggles display
The system SHALL expose the inference toggle states used by each analysis job in its summary and SHALL display them in the task management UI and job detail page.

#### Scenario: Job summary exposes toggle states
- **WHEN** the frontend retrieves an analysis job summary
- **THEN** the summary SHALL include `enableModelInference` and `enablePoseInference` reflecting the values the job was created with

#### Scenario: Legacy jobs have fallback values
- **WHEN** an existing job record predates the toggle fields and lacks them
- **THEN** the summary SHALL fall back to the backend global configuration values rather than failing to render

#### Scenario: Task management page shows toggle states
- **WHEN** the task management page lists analysis jobs
- **THEN** each job card SHALL display the inference toggle states (e.g. a compact badge such as "检测开 / 姿态关")

#### Scenario: Job detail page shows toggle states
- **WHEN** the user opens the job detail page
- **THEN** the task information section SHALL show the human detection and pose estimation toggle states alongside the other task metadata
