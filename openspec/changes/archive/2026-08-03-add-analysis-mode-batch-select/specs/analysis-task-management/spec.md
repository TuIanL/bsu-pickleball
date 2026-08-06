## ADDED Requirements

### Requirement: Analysis task batch select by analysis mode
The system SHALL provide a "select by analysis mode" entry in the upload-task tab toolbar of the analysis task management page, allowing users to batch-select all eligible (non-active) tasks of a given analysis mode — 样例任务 / 有限真实分析 / 真实视频分析 — into the existing selection set, which is shared with the existing batch deletion flow.

#### Scenario: User opens the mode select popover
- **WHEN** the upload-task tab shows at least one analysis task
- **THEN** the toolbar SHALL expose a "按类型选择" button, and activating it SHALL open a small popover listing the three analysis modes with their eligible (deletable) task counts

#### Scenario: User checks an analysis mode
- **WHEN** the user checks an analysis mode in the popover
- **THEN** all eligible (non-active) tasks of that mode SHALL be added to the selection set
- **AND** the task card checkboxes and the selected-count label SHALL update to reflect the new selection

#### Scenario: User unchecks an analysis mode
- **WHEN** the user unchecks an analysis mode in the popover
- **THEN** all eligible tasks of that mode SHALL be removed from the selection set
- **AND** the task card checkboxes and the selected-count label SHALL update to reflect the new selection

#### Scenario: Mode checkbox shows indeterminate state
- **WHEN** only a proper subset of a mode's eligible tasks is present in the selection set, for example after the user manually adjusted individual cards
- **THEN** the mode checkbox SHALL render an indeterminate (partial) state

#### Scenario: Active tasks are excluded from mode selection
- **WHEN** a mode contains active (queued, uploaded, or processing) tasks
- **THEN** mode-based selection SHALL apply only to eligible tasks
- **AND** active tasks SHALL remain unselected and SHALL NOT be part of any subsequent batch deletion

#### Scenario: User deletes mode-selected tasks
- **WHEN** the user selects tasks via the analysis-mode popover and then confirms the existing batch delete action
- **THEN** the deletion SHALL reuse the existing batch delete endpoint and feedback flow, and the list SHALL refresh with the same per-task result reporting as existing batch deletion

#### Scenario: No deletable tasks in a mode
- **WHEN** a mode has zero eligible (deletable) tasks
- **THEN** its checkbox SHALL be disabled or non-selectable with a zero count, and checking it SHALL have no effect on the selection set

#### Scenario: Popover closes
- **WHEN** the user clicks outside the popover or presses Escape
- **THEN** the popover SHALL close without altering the current selection set

### Requirement: Analysis task list filter by analysis mode
The system SHALL allow users to filter the upload-task list by analysis mode from the same "按类型选择" popover, in addition to batch-selecting tasks.

#### Scenario: User filters the list by a mode
- **WHEN** the user clicks an analysis mode in the popover filter section
- **THEN** the upload-task list SHALL show only tasks of that analysis mode
- **AND** the filter section SHALL mark the active mode

#### Scenario: User returns to the full list
- **WHEN** the user clicks the currently active mode again or clicks "全部"
- **THEN** the upload-task list SHALL show all upload tasks again

#### Scenario: Filter and batch select coexist
- **WHEN** the popover shows both the filter section and the batch-select section
- **THEN** the batch-select checkboxes SHALL remain independent of the active filter and still operate on all eligible tasks

#### Scenario: Select-all follows the filtered list
- **WHEN** a mode filter is active and the user toggles select-all
- **THEN** select-all SHALL apply to the visible eligible tasks of the filtered list
- **AND** the "已选 N 个可删除历史任务" count SHALL reflect the visible eligible tasks

#### Scenario: Active filter is reflected on the trigger button
- **WHEN** a mode filter other than "全部" is active
- **THEN** the trigger button SHALL display the active mode label appended to "按类型选择"
- **AND** the trigger button SHALL render with an active-state style that distinguishes it from the default state

### Requirement: Mode filter survives navigation away and back
The system SHALL keep the active mode filter when the user navigates from the upload-task tab to another page (e.g. an analysis details page) and returns, by persisting it for the duration of the browser session.

#### Scenario: User navigates away and returns
- **WHEN** the user has a non-default mode filter active and navigates to a different route (such as an analysis detail page)
- **AND** the user navigates back to the upload-task tab within the same browser session
- **THEN** the upload-task list SHALL be filtered by the same mode as before navigation
- **AND** the trigger button SHALL still display the active mode label

#### Scenario: Session boundary resets the filter
- **WHEN** the user opens the app in a new browser session
- **THEN** the mode filter SHALL default to "全部" with no persisted state shown
