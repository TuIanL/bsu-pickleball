## ADDED Requirements

### Requirement: Task card progress presentation
The system SHALL present active analysis task progress on task-management cards in a way that is consistent with the job status page and reduces reliance on the coarse overall percentage alone.

#### Scenario: Processing task card shows stage context
- **WHEN** a task on the task-management page has status `queued`, `uploaded`, `running`, or a compatible processing status
- **THEN** the task card progress area shows the overall percentage, the current stage label, and a compact stage stepper highlighting completed stages and the active stage, instead of a percentage bar alone

#### Scenario: Failed task card de-emphasizes progress
- **WHEN** a task on the task-management page has status `failed`
- **THEN** the task card shows the failure context as the primary message and does not show an active progress bar
