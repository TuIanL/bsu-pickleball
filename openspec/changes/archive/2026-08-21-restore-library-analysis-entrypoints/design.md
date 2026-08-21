## Context

Library-first 重构（commit `9c818a7`）后，一级导航收敛为「比赛库 / 现场采集 / 设备管理」，任务管理页 `/analysis/tasks` 降级为工程控制台（`analysis-task-management` spec 明确「从用户一级导航移除，通过工程模式进入」「用户层消费 LibraryItem 而非后台 Job」）。但"开始分析 / 再次分析 / 建立多次分析"的真实入口没有同步落到 Library 层，导致：

- 未分析素材 `OverviewView` 的「进入分析」导航到 `?view=analysis`，而该 view 依赖 `primaryAnalysisJobId`，无 job 时只渲染「暂无可用分析结果」空态 → 用户进不去分析创建页。
- `LibraryCard` 的 `canReanalyze` 仅对 `upload` 开放；`LibraryPage.handleReanalyze` 对录制/双摄错误跳转到 `/analysis/new`（上传页）。
- 多重分析方法（A/B 单摄 + 双摄 + 失败/取消重试 + 历史展开）只在工程控制台 `SyncRecordingTaskCard` 中存在，用户主线不可达。

实际创建分析与页面能力均已在 (RecordingAnalyzePage / MultiViewAnalysisSetupPage / NewAnalysisPage 预填)，本 Change 只需在 Library 层正确接线。

## Goals / Non-Goals

**Goals:**

- 未分析 LibraryItem 的「开始分析」按类型分派到正确的分析创建页。
- 已分析 LibraryItem 提供「再次分析」入口，可对一个录制建立多个分析任务。
- 保持 Library-first 定位，不动工程控制台 `/analysis/tasks`。
- 返回路径正确：创建页取消/完成回到比赛库或素材工作区。

**Non-Goals:**

- 不改后端、不改分析算法/流水线。
- 不把工程控制台重新挂回一级导航。
- 不改变既有多分析任务存储与删除语义（继续复用 AnalysisJob 体系）。

## Decisions

### 决策 1：分派逻辑收敛为一个纯函数，供卡片与工作区共用

新增纯函数（如 `libraryAnalysisPathFor(item): string | null`，放 `libraryAdapter.ts` 或新建 `libraryAnalysisRouting.ts`），统一计算「开始分析 / 再次分析」的目标 URL，避免在 `LibraryCard` 与 `LibraryItemWorkspace` 重复写分支。

分派规则（依据素材类型与元数据）：
- `sync_recording` 且存在 `captureTakeId` → `/capture/takes/:captureTakeId/analyze?session=:sessionId`（双摄协同）。
  - 若需 A/B 单摄再分析，另行提供 `/capture/:sessionId/analyze?cam=cam_1|cam_2` 选项。
- `recording`（单摄）→ 复用既有单摄分析入口：`/analysis/new?videoId=<video_id>&source=recording&sessionId=<sessionId>`（NewAnalysisPage 预填上传流程），与工程 `RecordingTaskCard` 当前行为一致。
- `upload` → `/upload?videoId=<sourceId>`。

**备选考虑**：曾考虑让单摄 `recording` 走 `RecordingAnalyzePage`（`/capture/:sessionId/analyze`）；但 `RecordingAnalyzePage` 面向双摄会话的 `cam_1/cam_2`（读 `SyncRecordingSession`），对独立单摄 `RecordingSession` 并不契合，故单摄录制沿用既有预填上传流程（见 Open Questions）。

### 决策 2：`LibraryItemViewModel` 补齐分派元数据

`libraryAdapter.ts` 当前已暴露 `captureTakeId` / `fieldSessionId` / `coverVideoUrl`。为分派需要补：
- `recording` 用途的 `video_id`（分析所需源视频 id），以便单摄 `recording` 生成 `/analysis/new?videoId=...`。
- (可选) `sort: 为 sync_recording 明确 A/B cam 可用标记`。

数据已存在于后端 `RecordingSession.video_id` / `SyncRecordingSession.registered_video_ids`，仅投影补齐。

### 决策 3：可分析门控接入既有三轴状态

「再次分析/开始分析」入口的可用性直接消费 `LibraryItemViewModel` 的 `mediaState` / `requiredAction` / `availabilityState`：
- `mediaState=ready` 且无 `pending_merge`、存储可用 → 可用。
- 正在录制 / 待合并 / 存储不可用 → 隐藏或禁用，不伪造。

复用 `displayState` 派生逻辑，不新增状态轴。

### 决策 4：返回路径携带来源上下文

从比赛库/工作区进入创建页时，通过 URL 参数或回跳地址保留来源：
- 双摄创建页已支持 `?session=:sessionId`；进入后其「返回双摄任务」仍指向任务列表——本轮在其返回路径上按来源上下文纠正为工作区/比赛库（或提供参数化回跳，见 Open Questions）。

### 决策 5：路由复用既有 AppRouter 分支

`recording-analyze` / `multiview-setup` 路由已存在，`AppRouter` 无需新增 route name；仅当需要区分返回来源时，扩展其参数读取。避免新增平行路由造成维护面。

## Risks / Trade-offs

- [单摄录制复用「上传分析页」在语义上不算完美（它标题是"上传视频"）] → 通过在 URL 携带 `source=recording` 并在该页针对录制来源显示录制上下文/返回，缓解；若用户更想专用录制分析页，可在 apply 前把该入口切换为 `RecordingAnalyzePage`（见 Open Questions）。
- [`OverviewView`「进入分析」改为跳转创建页后，与工程控制台/工作区 view 空态语义需保持一致] → 创建页返回回到该素材，已分析完成的素材仍走结果 view 不重复跳创建页。
- [再次分析入口放开后用户可能误建大量重复任务] → 明确入口为显式按钮动作（无隐式自动创建），并依靠 `analysisHistoryCount` 如实展示历史。

## Migration Plan

- 前端增量改动，无数据迁移。
- 回滚：恢复 `LibraryCard` / `LibraryPage` / `LibraryItemWorkspace` 的既有跳转即回退；`libraryAdapter` 新增字段为纯增量，旧字段保留。
- 验证：类型检查 `tsc` + 相关组件/路由测试 + 手工三类型素材（双摄/单摄/上传）未分析与已分析的入口路径。

## Open Questions

- 单摄 `recording` 的「开始分析/再次分析」目标页：**默认采用**「预填 videoId 的上传分析流程」（与工程 `RecordingTaskCard` 一致，最稳健）；是否改走专用 `RecordingAnalyzePage`（需先验证其能读取独立单摄 `RecordingSession`）待确认。
- 深摄 A/B 单摄再分析是否需要在用户层暴露（还是仅双摄协同 + 单摄各一次足够）：默认在工程控制台能力内保留，用户层工作区提供双摄协同为主入口、《再次分析》提供类型选择（双摄 / A 机位 / B 机位）。