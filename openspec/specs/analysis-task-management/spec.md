# analysis-task-management Specification

## Purpose
TBD - created by archiving change rework-video-analysis-task-flow. Update Purpose after archive.
## Requirements
### Requirement: Analysis task list retrieval

`GET /api/analysis/jobs` MUST 默认只返回 `visibility=public` 的任务。`include_internal=true` 查询参数才返回 `visibility=internal` 的 child，且该参数仅用于开发/诊断界面。

#### Scenario: 默认隐藏 internal child

- **WHEN** 前端请求任务列表（不带 `include_internal=true`）
- **THEN** 返回结果 SHALL 只含 `visibility=public` 的任务
- **AND** multiview child（`visibility=internal`）SHALL 被过滤

#### Scenario: 诊断模式查看 internal

- **WHEN** 前端以 `?include_internal=true` 请求
- **THEN** 返回结果 SHALL 额外包含 internal child
- **AND** 该模式 SHALL 仅用于开发/诊断界面

### Requirement: Analysis task management page

任务管理页 MUST 对每个双摄分析只展示一张 Parent 卡片，卡片标注「双摄协同分析」与 A/B/融合子状态，不再出现两张无关联的机位任务卡片。双摄任务卡片的 CTA 按 Parent 状态区分：完成 → 查看报告；失败/取消 → 提供「重新双摄分析」入口；运行中 → 展示进度。

#### Scenario: 双摄任务单卡片

- **WHEN** 任务列表包含 multiview Parent
- **THEN** 该 Parent SHALL 以单张卡片展示，含「双摄协同分析」标题、A 机位/B 机位/多视角融合子状态与数据来源
- **AND** 其 internal child SHALL 不单独出现在列表中

#### Scenario: 失败/取消的 Parent 可重新分析

- **WHEN** multiview Parent 状态为 `failed` 或 `canceled`
- **THEN** 录制卡片 SHALL 提供「重新双摄分析」入口（导航到 `MultiViewAnalysisSetupPage`）
- **AND** SHALL NOT 误显示为「分析中」

### Requirement: Task status actions
The system SHALL expose task actions according to each analysis task's current status, including cancellation for active tasks and delete actions for eligible historical tasks.

#### Scenario: Completed task is visible
- **WHEN** a task has status `succeeded` or compatible completed status
- **THEN** the task row or card provides a primary action to view the video analysis result, secondary access to the analysis details page, and a delete action

#### Scenario: Processing task is visible
- **WHEN** a task has status `queued`, `uploaded`, `running`, or compatible processing status
- **THEN** the task row or card shows progress, links to the job status detail, and offers cancellation when the backend allows it instead of enabling completed-result or delete actions

#### Scenario: Failed task is visible
- **WHEN** a task has status `failed`
- **THEN** the task row or card shows failure context when available and provides actions to inspect the task detail, start a new upload, retry when available, or delete the failed task

#### Scenario: Canceled task is visible
- **WHEN** a task has status `canceled`
- **THEN** the task row or card shows cancellation context and provides actions to inspect the task detail, start a new upload, or delete the canceled task

### Requirement: Task list refresh
The system SHALL keep active analysis tasks reasonably current while the user is viewing task management.

#### Scenario: Active task is listed
- **WHEN** the task management page contains a queued, uploaded, running, or compatible processing task
- **THEN** the frontend refreshes the task list or affected task summaries until no active tasks remain

#### Scenario: User manually refreshes tasks
- **WHEN** the user activates a refresh control on the task management page
- **THEN** the frontend reloads task summaries and preserves stable navigation and scroll behavior

#### Scenario: Cancellation is pending
- **WHEN** a cancellation request has been made but the job has not reached terminal canceled state
- **THEN** the frontend continues refreshing the affected task until the latest durable status is visible

### Requirement: Analysis task deletion
The system SHALL allow users to delete eligible historical analysis tasks and their persisted local artifacts.

#### Scenario: Completed task is deleted
- **WHEN** the user confirms deletion for a completed or succeeded analysis task
- **THEN** the backend removes the persisted job summary, generated report, raw pipeline result, per-job output directory, and active records for that job

#### Scenario: Failed task is deleted
- **WHEN** the user confirms deletion for a failed analysis task
- **THEN** the backend removes available persisted job artifacts for that job without requiring a completed report or result to exist

#### Scenario: Canceled task is deleted
- **WHEN** the user confirms deletion for a canceled analysis task
- **THEN** the backend removes available persisted job artifacts for that job without requiring a completed report or result to exist

#### Scenario: Active task deletion is blocked
- **WHEN** the user attempts to delete a task whose status is `uploaded`, `queued`, `running`, or compatible processing status
- **THEN** the backend rejects or marks that deletion as blocked and leaves all local files intact

#### Scenario: Deleted task is no longer listed
- **WHEN** a task deletion succeeds and the frontend refreshes task management
- **THEN** the deleted task no longer appears in the task list and direct job/result/report routes for that job show stable not-found states

#### Scenario: Linked artifacts are shared
- **WHEN** a deleted task references an uploaded video or calibration that is still referenced by another remaining job
- **THEN** the backend preserves the shared video, video metadata, calibration, and preview files

#### Scenario: Linked artifacts are unreferenced
- **WHEN** a deleted task references an uploaded video or calibration that no remaining job references
- **THEN** the backend removes the linked source video, video metadata, calibration JSON, and generated calibration preview files when those files exist

### Requirement: Batch analysis task deletion
The system SHALL support deleting multiple eligible analysis tasks from task management in one user action.

#### Scenario: User selects multiple tasks
- **WHEN** the task management page contains historical tasks
- **THEN** the user can select individual tasks, select all eligible visible tasks, and see the number of selected tasks before deleting

#### Scenario: Batch delete succeeds
- **WHEN** the user confirms batch deletion for selected completed or failed tasks
- **THEN** the backend deletes each eligible task's persisted local artifacts and the frontend removes the deleted tasks from the visible list

#### Scenario: Batch delete has partial failures
- **WHEN** a batch delete includes missing, blocked, or failed items
- **THEN** the backend returns per-job deletion results and the frontend reports which tasks were deleted and which require attention

#### Scenario: User cancels batch deletion
- **WHEN** the user opens the batch delete confirmation and cancels it
- **THEN** no backend deletion request is made and task selection remains unchanged or is safely dismissed without deleting files

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

### Requirement: Task cancellation feedback
The system SHALL provide clear feedback for cancellation actions from task management and job status surfaces.

#### Scenario: Cancellation request is in progress
- **WHEN** a cancellation request is being submitted
- **THEN** the affected cancellation control shows a pending state and prevents duplicate cancellation requests for the same job

#### Scenario: Cancellation request succeeds
- **WHEN** the backend accepts a cancellation request
- **THEN** the frontend refreshes the affected task and communicates that cancellation will complete at a safe checkpoint when the job is running

#### Scenario: Cancellation request fails
- **WHEN** a cancellation request cannot be accepted or cannot reach the backend
- **THEN** the frontend shows a recoverable error and does not pretend the job has been canceled

### Requirement: Analysis task list filters by recording session

按录制 session 过滤的任务查询 MUST 同样默认只返回 `visibility=public` 的 Parent，保证录制卡片查询该 session 的分析任务时不会出现三条（Parent + 两个 child）。

#### Scenario: 录制卡片查询 Parent

- **WHEN** 录制卡片请求 `GET /api/analysis/jobs?recording_session_id=<sid>`
- **THEN** 返回结果 SHALL 只含该 session 的 public Parent 任务
- **AND** internal child SHALL NOT 混入

### Requirement: Analysis task recording origin display

双摄录制卡片的 CTA MUST 将主操作改为「双摄协同分析」，次级的「分析 A/B 机位」MUST 降级为工程调试入口，分析状态展示 MUST 基于 Parent。

#### Scenario: 录制卡片主 CTA

- **WHEN** 双摄录制卡片渲染且存在对应 CaptureTake
- **THEN** 主操作 SHALL 为「双摄协同分析」
- **AND** A/B 单摄入口 SHALL 置于次级操作

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

### Requirement: 级联删除语义

`AnalysisDeleteResult` / 批量删除路径 MUST 支持 multiview Parent 的级联删除（Parent + owned child 分析产物 + fusion run 产物 + parent artifacts/report），且 MUST NOT 删除 CaptureTake、源视频或 CaptureTrack。child 的删除仅能由 Parent cascade 触发。

#### Scenario: 删除 Parent 级联

- **WHEN** 用户删除 terminal 的 multiview Parent
- **THEN** 删除结果 SHALL 覆盖 Parent 及其 owned child 的分析产物与 fusion run 产物
- **AND** 录制资产（CaptureTake / 源视频 / CaptureTrack）SHALL 保留

#### Scenario: 删除 child 被阻断

- **WHEN** 外部 API 尝试直接删除 internal child
- **THEN** 系统 SHALL 返回 `blocked`
- **AND** 删除 SHALL 仅经 Parent cascade 发生

### Requirement: 双摄录制卡片删除分析任务

「双摄录制」Tab 的录制卡片 SHALL 在存在分析任务时提供「删除分析任务」入口，用于清除该录制派生的所有分析任务及其本地产物，同时保留录制本身。

#### Scenario: 卡片显示删除分析任务按钮

- **WHEN** 录制卡片存在任一分析任务（multiview Parent、A 机位或 B 机位单摄任务）
- **THEN** 卡片 SHALL 提供「删除分析任务」操作
- **AND** 该操作 SHALL 区别于「删除」（整条录制）按钮

#### Scenario: 卡片无分析任务时不显示

- **WHEN** 录制卡片不存在任何分析任务
- **THEN** 卡片 SHALL 不显示「删除分析任务」操作

#### Scenario: 用户确认后删除分析任务

- **WHEN** 用户确认删除该录制的分析任务
- **THEN** 前端 SHALL 调用后端录制级删除接口
- **AND** 删除完成后 SHALL 刷新任务列表
- **AND** 录制卡片 SHALL 保留在「双摄录制」Tab

#### Scenario: 有活跃分析任务被阻断

- **WHEN** 删除结果中包含 `blocked`（处理中任务）或 `failed` 项
- **THEN** 前端 SHALL 报告哪些任务已删除、哪些需要用户处理
- **AND** SHALL NOT 将阻塞项当作删除成功移除

### Requirement: 分析任务删除清理完整产物目录

删除分析任务 SHALL 清除该任务在本地磁盘的**完整产物目录**，而不只是部分已知文件；录制资产 MUST NOT 被误删。

#### Scenario: capture job 产物目录整体删除

- **WHEN** 用户删除一个产物位于 `take_dir/analysis/<job_id>/` 的 capture 分析任务
- **THEN** 后端 SHALL 删除该 `<job_id>` 目录及其全部内容，包括 `analysis_overlay.mp4`、`position_visualizations/`、`fused_*.json`、`ball_trajectory.json`、`cleaned_ball_trajectory.json`、`bounce_events.json`、`player_render_trajectory.json`、`players_trajectory.*`、`detections.jsonl` 等
- **AND** `take_dir` 下的录制视频、分段与 `sync_calibration.json` SHALL 保留

#### Scenario: 删除路径安全校验

- **WHEN** 后端准备整体删除分析任务产物目录
- **THEN** 目标路径 SHALL 严格匹配 `<take_dir>/analysis/<job_id>` 或 `<outputs_dir>/<job_id>` 格式
- **AND** `job_id` SHALL 以 `job-` 前缀开头并仅含 URL 安全字符（`^job-[A-Za-z0-9_-]+$`），避免误删录制目录

#### Scenario: 非 capture job 行为不变

- **WHEN** 用户删除产物位于 `<outputs_dir>/<job_id>` 的非 capture 分析任务
- **THEN** 后端 SHALL 删除该 job 的输出目录
- **AND** 既有删除行为 SHALL 保持一致

