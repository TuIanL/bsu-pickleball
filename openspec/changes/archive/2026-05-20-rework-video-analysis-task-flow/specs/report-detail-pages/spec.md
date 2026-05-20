## ADDED Requirements

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
