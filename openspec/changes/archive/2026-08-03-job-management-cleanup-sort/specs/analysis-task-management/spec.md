## ADDED Requirements

### Requirement: Terminal task bulk cleanup
The system SHALL provide a one-click action on the analysis task management page that deletes all failed and canceled analysis tasks in the upload-task list, reusing the existing batch deletion path.

#### Scenario: User clears failed and canceled tasks
- **WHEN** the upload-task list contains at least one task with status `failed` or `canceled`
- **THEN** the clear control is enabled and, after the user confirms, the frontend submits the eligible task ids to the existing batch delete endpoint
- **AND** the frontend reports per-task deletion results using the existing delete feedback summary

#### Scenario: No terminal tasks exist
- **WHEN** the upload-task list contains no tasks with status `failed` or `canceled`
- **THEN** the clear control is disabled or performs no action

#### Scenario: User cancels cleanup confirmation
- **WHEN** the user dismisses the cleanup confirmation dialog
- **THEN** no backend deletion request is made and the task list remains unchanged

#### Scenario: Cleanup has partial results
- **WHEN** a cleanup request includes tasks that are missing or blocked
- **THEN** the frontend reports which tasks were deleted and which require attention

#### Scenario: Cleanup keeps the local fallback store consistent
- **WHEN** a cleanup succeeds through the backend
- **THEN** the frontend removes the same demo tasks from the browser local fallback store so the local list stays consistent

### Requirement: Analysis task list sorting
The system SHALL allow users to sort the upload-task list by creation time or update time, in ascending or descending order, on the analysis task management page.

#### Scenario: User sorts by creation time
- **WHEN** the user selects creation-time ordering on the upload-task list
- **THEN** the list is ordered by task `createdAt`, ascending or descending as chosen

#### Scenario: User sorts by update time
- **WHEN** the user selects update-time ordering on the upload-task list
- **THEN** the list is ordered by task `updatedAt`, falling back to `createdAt` when `updatedAt` is absent, ascending or descending as chosen

#### Scenario: Default ordering matches prior behavior
- **WHEN** the task management page loads with no explicit sort selection
- **THEN** the upload-task list is ordered by update time, newest first, matching the previous list order

#### Scenario: Sorting applies to all data paths
- **WHEN** the task list is sourced either from the backend API or from the browser local fallback store
- **THEN** the same sort logic is applied in both cases so ordering is consistent
