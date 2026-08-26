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

### Requirement: Task status actions

The system SHALL expose task actions according to each analysis task's current status, including cancellation for active tasks, recovery actions for interrupted tasks, and delete actions for eligible historical tasks.

#### Scenario: Completed task is visible

- **WHEN** a task has status `succeeded` or compatible completed status
- **THEN** the task row or card provides a primary action to view the video analysis result, secondary access to the analysis details page, and a delete action

#### Scenario: Processing task is visible

- **WHEN** a task has status `queued`, `uploaded`, `running`, or compatible processing status with fresh Worker liveness
- **THEN** the task row or card shows progress, links to the job status detail, and offers cancellation when the backend allows it instead of enabling completed-result or delete actions

#### Scenario: Interrupted task is visible

- **WHEN** a task has status `interrupted` or Worker liveness is durably marked lost
- **THEN** the task row or card shows the user-facing label “任务失联” and the last known stage/progress
- **AND** SHALL stop treating the task as an active processing task
- **AND** SHALL offer task detail, explicit re-analysis/retry and delete actions instead of ordinary cancellation

#### Scenario: Failed task is visible

- **WHEN** a task has status `failed`
- **THEN** the task row or card shows failure context when available and provides actions to inspect the task detail, start a new upload, retry when available, or delete the failed task

#### Scenario: Canceled task is visible

- **WHEN** a task has status `canceled`
- **THEN** the task row or card shows cancellation context and provides actions to inspect the task detail, start a new upload, or delete the canceled task

### Requirement: Task list refresh

The system SHALL keep queued and genuinely running analysis tasks reasonably current while the user is viewing task management. An interrupted task SHALL stop active polling after its durable state is received.

#### Scenario: Active task is listed

- **WHEN** the task management page contains a queued, uploaded, or running task with fresh Worker liveness
- **THEN** the frontend refreshes the task list or affected task summaries until no active tasks remain

#### Scenario: Interrupted task is listed

- **WHEN** the task management page receives an interrupted task
- **THEN** the frontend SHALL render “任务失联” with the last heartbeat/interruption context when available
- **AND** SHALL remove the task from the active polling set

#### Scenario: User manually refreshes tasks

- **WHEN** the user activates a refresh control on the task management page
- **THEN** the frontend reloads task summaries and preserves stable navigation and scroll behavior

#### Scenario: Cancellation is pending

- **WHEN** a cancellation request has been made but the job has not reached terminal canceled state
- **THEN** the frontend continues refreshing the affected task until the latest durable status is visible

### Requirement: Analysis task deletion

The system SHALL allow users to delete eligible historical analysis tasks and their persisted local artifacts, including tasks durably marked interrupted.

#### Scenario: Completed task is deleted

- **WHEN** the user confirms deletion for a completed or succeeded analysis task
- **THEN** the backend removes the persisted job summary, generated report, raw pipeline result, per-job output directory, and active records for that job

#### Scenario: Failed task is deleted

- **WHEN** the user confirms deletion for a failed analysis task
- **THEN** the backend removes available persisted job artifacts for that job without requiring a completed report or result to exist

#### Scenario: Interrupted task is deleted

- **WHEN** the user confirms deletion for an interrupted analysis task and no Worker lease remains active
- **THEN** the backend removes the task record and available persisted artifacts
- **AND** SHALL preserve shared source video, calibration and recording assets according to existing reference rules

#### Scenario: Active task deletion is blocked

- **WHEN** the user attempts to delete a task whose status is `uploaded`, `queued`, or running processing with fresh Worker liveness
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

双摄录制卡片的 CTA MUST 将主操作改为「双摄协同分析」，次级的「分析 A/B 机位」MUST 降级为工程调试入口，分析状态展示 MUST 基于当前 Parent 和各机位任务分组。存在多次任务时，状态和操作 SHALL 指向最新任务，历史任务 SHALL 可展开查看。

#### Scenario: 录制卡片主 CTA

- **WHEN** 双摄录制卡片渲染且存在对应 CaptureTake
- **THEN** 主操作 SHALL 为「双摄协同分析」
- **AND** A/B 单摄入口 SHALL 置于次级操作

#### Scenario: 录制卡片展示多次任务

- **WHEN** 双摄录制卡片下存在同一类型的多个公开分析任务
- **THEN** 主视图 SHALL 展示该类型最近更新任务的状态
- **AND** SHALL 显示历史任务数量与展开入口
- **AND** SHALL 不将旧任务静默覆盖或丢弃

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

### Requirement: 双摄录制派生任务归属一致性

前端 SHALL 使用与后端录制级删除一致的归属规则识别双摄录制派生的公开分析任务：任务的 `recordingSessionId` 或 `metadata.recording_session_id` 命中 session id，或任务的 `metadata.capture_take_id` 命中该双摄会话的 `capture_take_id`。

#### Scenario: 任务通过 recording session 归属

- **WHEN** 公开分析任务的 `recordingSessionId` 或 `metadata.recording_session_id` 等于双摄会话的 `session_id`
- **THEN** 前端 SHALL 将任务展示在该双摄录制卡片的分析任务区域
- **AND** 前端 SHALL 将任务从上传任务 Tab 中排除

#### Scenario: 任务通过 capture take 归属

- **WHEN** 公开分析任务缺少 session id，但 `metadata.capture_take_id` 等于双摄会话的 `capture_take_id`
- **THEN** 前端 SHALL 将任务展示在该双摄录制卡片的分析任务区域
- **AND** 前端 SHALL 将任务从上传任务 Tab 中排除

#### Scenario: 任务不属于任何双摄会话

- **WHEN** 公开分析任务的 session id 和 capture take id 均未命中任何双摄会话
- **THEN** 前端 SHALL 将任务保留在上传任务 Tab 或未归属诊断范围
- **AND** SHALL NOT 将任务错误挂载到任一双摄录制卡片

### Requirement: 双摄任务按类型分组并保留历史

双摄录制卡片 SHALL 将归属该会话的公开分析任务分为双摄协同 Parent、A 机位单摄任务和 B 机位单摄任务。每组 SHALL 默认展示按最近更新时间排序的最新任务；同组其他任务 SHALL 作为历史任务保留并可展开查看。

#### Scenario: 双摄 Parent 作为主任务

- **WHEN** 双摄录制会话存在一个或多个公开 `analysisKind=multiview` 任务
- **THEN** 卡片 SHALL 将最新 Parent 作为双摄协同主任务展示
- **AND** internal child SHALL NOT 作为独立任务展示

#### Scenario: 同一机位存在多个任务

- **WHEN** A 或 B 机位存在多个公开单摄分析任务
- **THEN** 卡片 SHALL 展示该机位最新任务的状态和操作
- **AND** SHALL 提供历史任务数量与展开入口
- **AND** 历史任务 SHALL 保留各自的 job id 和状态

#### Scenario: 任务更新时间缺失

- **WHEN** 某任务没有 `updatedAt`
- **THEN** 前端 SHALL 使用 `createdAt` 参与当前任务和历史任务排序
- **AND** SHALL 使用 job id 作为相同时间下的稳定排序依据

### Requirement: 双摄任务操作绑定具体任务

双摄卡片上的查看报告、查看进度、重试、取消和任务级删除操作 SHALL 绑定用户当前看到的具体任务 ID，不得通过任务类型再次隐式选择第一条任务。

#### Scenario: 最新任务操作

- **WHEN** 用户在双摄卡片点击最新 Parent 或 A/B 任务的操作
- **THEN** 前端 SHALL 使用该任务行对应的 `job.id` 导航或调用操作接口

#### Scenario: 历史任务操作

- **WHEN** 用户展开历史任务并点击某一历史任务的详情或删除操作
- **THEN** 前端 SHALL 只作用于该历史任务的 `job.id`
- **AND** SHALL NOT 修改同组当前任务

### Requirement: 任务列表来源上下文可恢复

分析任务管理页 SHALL 使用有限来源枚举表示当前任务视图，并在 URL 中保留来源 tab；双摄视图可以额外保留其录制 session id。页面重新挂载、刷新或从任务详情返回时 SHALL 恢复 URL 指定的来源视图。

#### Scenario: 返回双摄任务列表

- **WHEN** 用户从双摄任务卡片进入分析详情后点击返回任务管理
- **THEN** 页面 SHALL 回到双摄录制 tab
- **AND** SHALL NOT 默认显示上传视频任务 tab

#### Scenario: 直接打开带来源的任务列表

- **WHEN** 用户打开 `/analysis/tasks?source=sync_recording&session=<sessionId>`
- **THEN** 页面 SHALL 激活双摄录制 tab
- **AND** SHALL 使用 session id 作为当前录制上下文

#### Scenario: 非法来源参数

- **WHEN** URL 中的 `source` 不是受支持的来源枚举
- **THEN** 页面 SHALL 安全回退到上传视频任务 tab
- **AND** SHALL 不抛出路由解析异常

### Requirement: 任务页 tab 切换不污染浏览器历史

任务管理页来源 tab 切换 SHALL 更新可恢复的 URL 状态，但 SHALL 使用 replace 历史语义；从任务页进入详情或创建页 SHALL 使用新的业务历史项。

#### Scenario: 用户切换任务来源

- **WHEN** 用户在任务管理页从上传任务切换到双摄录制
- **THEN** 地址 SHALL 反映双摄来源
- **AND** 用户随后按浏览器后退 SHALL 不需要逐个经过任务页 tab 切换状态

### Requirement: Task card progress presentation
The system SHALL present active analysis task progress on task-management cards in a way that is consistent with the job status page and reduces reliance on the coarse overall percentage alone.

#### Scenario: Processing task card shows stage context
- **WHEN** a task on the task-management page has status `queued`, `uploaded`, `running`, or a compatible processing status
- **THEN** the task card progress area shows the overall percentage, the current stage label, and a compact stage stepper highlighting completed stages and the active stage, instead of a percentage bar alone

#### Scenario: Failed task card de-emphasizes progress
- **WHEN** a task on the task-management page has status `failed`
- **THEN** the task card shows the failure context as the primary message and does not show an active progress bar

### Requirement: 工程任务控制台入口
分析任务管理能力 SHALL 作为 Engineering Task Console 保留，但从用户一级导航移除，通过工程/开发者模式进入。

#### Scenario: 工程入口可达
- **WHEN** 用户处于工程模式并进入分析任务
- **THEN** 系统 SHALL 呈现完整的 task management 能力（Parent/child 可见、进度、stage、cancel、delete、batch delete、retry、历史任务、失败状态、internal visibility）

#### Scenario: 普通用户默认不可达
- **WHEN** 普通用户在默认导航浏览
- **THEN** 分析任务管理 SHALL 不作为一级入口出现

### Requirement: 用户层消费 LibraryItem 而非后台 Job
单摄/双摄/上传的分析任务 SHALL 通过 LibraryItem 与 LibraryItemWorkspace 呈现，而不要求普通用户直接面对 AnalysisJob。

#### Scenario: 上传任务以素材呈现
- **WHEN** 一个上传任务存在
- **THEN** 用户层 SHALL 以一个 LibraryItem（upload）呈现，其分析状态作为该素材的生命周期
- **AND** 用户不直接首层面对 AnalysisJobRecord

### Requirement: 删除 AnalysisJob 不删除 Library 源资产
Engineering Console 删除 AnalysisJob SHALL 只删除 job 及其 artifacts，不得连带删除 Library source video / RecordingSession；源资产删除为经 LibraryItem 显式触发的独立动作。

#### Scenario: 删除最后的 Job 保留上传源视频
- **WHEN** 用户删除最后一个引用某 upload video 的 AnalysisJob
- **THEN** 系统 SHALL 仅删除该 job 及其产物
- **AND** SHALL NOT 删除 source video，`LibraryItem(upload)` 继续存在

#### Scenario: 录制/双摄资产不受 Job 删除影响
- **WHEN** 用户删除某录制派生的分析任务
- **THEN** 系统 SHALL 仅删除 job 产物
- **AND** RecordingSession / SyncRecordingSession（MediaAsset）SHALL 保留，LibraryItem 卡不消失

### Requirement: 普通产品流完成后不进入任务管理

从 Library 发起（`origin=library`）的分析，在进度页完成 / 失败 / 取消后，其去向 SHALL 是 Library Item Workspace，而不是 `AnalysisTasksPage`。`/analysis/tasks` 与 `/analysis/:jobId/...` 结果路由 SHALL 仅作为 Engineering Task Console 与兼容 deep-link 保留，普通产品流 SHALL NOT 主动把用户送过去。

#### Scenario: Library origin 完成后回工作区

- **WHEN** 从 Library 发起分析且进度页任务完成
- **THEN** 系统 SHALL 将结果入口指向 `/library/:kind/:sourceId?view=...`
- **AND** SHALL NOT 导航到 `/analysis/tasks`

#### Scenario: 工程控制台 deep-link 保留

- **WHEN** 用户经 Engineering Task Console 进入任务详情或结果页
- **THEN** 该入口 SHALL 保持可用的 `/analysis/:jobId/...` 路由与完整工程能力（Parent/child 可见、进度、stage、cancel、delete、batch delete、internal visibility）

#### Scenario: Task Console origin 返回任务列表

- **WHEN** 从 `/analysis/tasks`（或带任务上下文的任务列表）发起分析并进入进度页
- **THEN** 进度页返回 SHALL 回到 `/analysis/tasks`（含来源 tab 上下文）
- **AND** 完成 CTA SHALL 保留工程结果路由

#### Scenario: 进度页不得擅自切回任务管理

- **WHEN** Progress 页的 origin 为 `library` 或 `capture`
- **THEN** 其返回/完成 CTA SHALL NOT 进入 `/analysis/tasks`

