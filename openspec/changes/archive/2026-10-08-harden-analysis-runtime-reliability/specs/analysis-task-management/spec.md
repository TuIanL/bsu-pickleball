## MODIFIED Requirements

### Requirement: Task list refresh

The system SHALL keep queued and genuinely running analysis tasks reasonably current while the user is viewing task management. An interrupted task SHALL stop active polling after its durable state is received. A failed list request SHALL NOT stop the refresh loop, and SHALL NOT discard the tasks already displayed.

#### Scenario: Active task is listed

- **WHEN** The task management page contains a queued, uploaded, or running task with fresh Worker liveness
- **THEN** The frontend refreshes the task list or affected task summaries until no active tasks remain

#### Scenario: Interrupted task is listed

- **WHEN** The task management page receives an interrupted task
- **THEN** the frontend SHALL render “任务失联” with the last heartbeat/interruption context when available
- **AND** SHALL remove the task from the active polling set

#### Scenario: User manually refreshes tasks

- **WHEN** the user activates a refresh control on the task management page
- **THEN** the frontend reloads task summaries and preserves stable navigation and scroll behavior

#### Scenario: Cancellation is pending

- **WHEN** a cancellation request has been made but the job has not reached terminal canceled state
- **THEN** the frontend continues refreshing the affected task until the latest durable status is visible

#### Scenario: Transient list request failure keeps the refresh loop alive

- **WHEN** a task list request fails while active tasks are still present
- **THEN** the frontend SHALL schedule another refresh attempt after an interval
- **AND** SHALL keep refreshing until no active tasks remain, exactly as if the request had succeeded
- **AND** active task progress SHALL NOT freeze permanently because of a single failed request

#### Scenario: Failed request preserves the previously loaded task list

- **WHEN** a task list request fails after tasks have already been loaded
- **THEN** the frontend SHALL keep the previously loaded task list rendered
- **AND** MUST NOT replace the list with an empty list
- **AND** the page MUST NOT present an empty state that implies the tasks were deleted
- **AND** the failure SHALL remain visible as an inline error state

#### Scenario: Recovery after a failed request

- **WHEN** a subsequent refresh attempt succeeds after earlier failures
- **THEN** the frontend SHALL replace the displayed list with the fresh result
- **AND** SHALL clear the corresponding error state

#### Scenario: Loop stops only when no active tasks remain

- **WHEN** the most recent successful list contains no active tasks
- **THEN** the frontend SHALL stop scheduling further automatic refreshes
- **AND** an interrupted task alone SHALL NOT keep the refresh loop running

## ADDED Requirements

### Requirement: Destructive confirmations must live at the execution site

Any destructive action exposed to users MUST confirm at the place where the deletion is actually issued. A confirmation implemented only in a caller component SHALL NOT be considered sufficient, so that newly added call sites cannot bypass it.

#### Scenario: Deleting a field session confirms in the executing handler

- **WHEN** the user triggers deletion of a field session
- **THEN** the function that issues the delete request SHALL request confirmation itself
- **AND** the deletion MUST NOT proceed when the user declines

#### Scenario: Newly added call site cannot bypass confirmation

- **WHEN** a new component calls the field session deletion entry point
- **THEN** the confirmation SHALL still be requested
- **AND** the deletion MUST NOT proceed without an explicit user confirmation

#### Scenario: Every destructive entry point is covered

- **WHEN** 开发者审查任务管理与双摄录制页面的全部破坏性操作（单条删除、批量删除、清理终端任务、录制删除、录制级分析任务删除）
- **THEN** 每个操作 SHALL 在其执行处具备确认
- **AND** MUST NOT 存在确认逻辑只存在于部分调用方的操作

### Requirement: Selection computations must scale with list size

Selection and select-all derivations on the task management page SHALL NOT use linear scans inside per-item loops. Membership checks SHALL be expressible as constant-time lookups, and the page SHALL remain responsive at the documented dataset size.

#### Scenario: Selected-set intersection stays fast at full dataset size

- **WHEN** the page holds the full documented set of jobs (hundreds of items) and the user has a large selection
- **THEN** computing the selected-and-eligible intersection SHALL NOT perform a linear scan per selected item
- **AND** the resulting counts SHALL be identical to a naive implementation

#### Scenario: Select-all determination stays fast

- **WHEN** determining whether all visible eligible tasks are selected
- **THEN** the determination SHALL NOT perform a linear scan per visible task
- **AND** SHALL report the same result as a naive implementation

#### Scenario: Partial selection still renders as indeterminate

- **WHEN** only a proper subset of the visible eligible tasks is selected
- **THEN** the select-all control SHALL render an indeterminate state
- **AND** the selected count SHALL reflect the subset size