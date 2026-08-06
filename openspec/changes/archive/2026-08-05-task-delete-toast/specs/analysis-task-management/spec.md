## MODIFIED Requirements

### Requirement: Delete feedback and refresh

The system SHALL provide clear feedback for deletion actions via a compact floating toast that auto-dismisses when all selected items are deleted and requires manual dismissal when some items are blocked or failed, and SHALL keep task management state current after deletion. Persistent error states such as a failed task-list load SHALL remain inline rather than being shown as a transient toast.

#### Scenario: Delete request is in progress

- **WHEN** a single or batch deletion is running
- **THEN** the affected delete controls show a pending state and prevent duplicate deletion requests for the same selected tasks

#### Scenario: Delete request cannot reach backend

- **WHEN** a delete request fails because the backend cannot be reached
- **THEN** the frontend shows a recoverable error state and does not remove tasks from the list as if deletion had succeeded

#### Scenario: Delete completes

- **WHEN** a single or batch deletion finishes
- **THEN** the frontend refreshes task summaries, clears deleted task selections, and preserves access to upload and manual refresh actions

#### Scenario: Delete result shown as a floating toast

- **WHEN** a single or batch deletion finishes with any result
- **THEN** the frontend shows a compact toast fixed to the bottom-right of the viewport with a single line of text, without displacing the task list content

#### Scenario: Fully successful delete auto-dismisses

- **WHEN** all selected tasks are deleted successfully
- **THEN** the toast is green, auto-dismisses after 3 seconds, and does not show a countdown or progress indicator

#### Scenario: Delete with blocked or failed items requires manual dismissal

- **WHEN** a deletion result includes blocked, missing, or failed items
- **THEN** the toast is amber, includes a close button, and remains until the user dismisses it manually
