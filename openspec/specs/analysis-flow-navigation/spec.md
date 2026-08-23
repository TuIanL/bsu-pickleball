# analysis-flow-navigation Specification

## Purpose
TBD - created by archiving change unify-analysis-lifecycle-navigation. Update Purpose after archive.
## Requirements
### Requirement: return 是 canonical origin carrier

系统 SHALL 将 `return` 查询参数视为 transient analysis flow 的唯一 canonical origin carrier。任何 Setup、Calibration、Progress 子流程 SHALL 原样转发已有 `return`；子流程 SHALL NOT 丢弃、简化或自行重建上游 `return`。当子流程需要跳入更深一层流程时，SHALL 把「完整上一层 URL」（含其全部上下文参数）编码为 `return` 传入（嵌套 return）。

#### Scenario: Library 发起分析携带 return

- **WHEN** 用户从 Library Item 触发「开始分析 / 再次分析」
- **THEN** 生成的分析创建入口 URL SHALL 携带 `return=/library/:kind/:sourceId?view=overview`
- **AND** 该 `return` SHALL 在创建页内被保留用于取消/退出回跳

#### Scenario: 进入同步标定采用嵌套 return

- **WHEN** 双摄分析设置页（`/capture/takes/:takeId/analyze?session=:sid&return=:libraryPath`）触发进入 SyncCalibration
- **THEN** 标定 URL SHALL 为 `/sync-calibration?take=:takeId&return=<encodeURIComponent(完整上层 URL)>`
- **AND** 完整上层 URL SHALL 同时包含 `session=:sid` 与外层 `return=:libraryPath`
- **AND** 标定完成/取消后 SHALL 回到该完整上层 URL，链条不丢

#### Scenario: 子流程不得重建缩水 return

- **WHEN** 任一子流程需要构造跳往下一层流程的 URL
- **THEN** 该流程 SHALL 转发已携带的全部上下文（含外层 `return`），SHALL NOT 只回填自身路径而丢掉上游 `return`

### Requirement: 从 URL 推导 AnalysisFlowOrigin

系统 SHALL 提供纯函数 `resolveAnalysisFlowOrigin(returnPath?, taskContext?)`，由 URL 推导 origin，作为只读「视图」而非第二份可变状态。origin 类型为 `library` / `task-console` / `capture` 三态联合。

#### Scenario: Library origin 推导

- **WHEN** `return` 以 `/library/` 开头（如 `/library/sync_recording/sync_xxx?view=overview`）
- **THEN** 推导结果 SHALL 为 `{ kind: "library", itemKind, sourceId, returnPath }`
- **AND** `itemKind` / `sourceId` SHALL 从 return 路径解析得到

#### Scenario: Capture origin 推导

- **WHEN** `return` 以 `/capture/` 开头
- **THEN** 推导结果 SHALL 为 `{ kind: "capture", returnPath }`

#### Scenario: Task Console origin 回退

- **WHEN** `return` 缺失或不属于 `/library/`、`/capture/` 前缀
- **THEN** 推导结果 SHALL 为 `{ kind: "task-console", taskContext }`
- **AND** `taskContext` SHALL 复用既有 `taskContextForJob(job)` 语义

### Requirement: 统一创建后进入 Analysis Progress

upload / recording / sync A/B 单机 / sync 协同四类分析，在 Job 创建成功后 SHALL 统一进入分析进度页（`/analysis/:jobId?return=:上游 return`），而不是按来源类型走不同路线（如部分直接回 Library、部分进进度页）。

#### Scenario: 上传创建成功后进进度页

- **WHEN** 用户在 `NewAnalysisPage`（含上传/单摄录制流程）成功创建分析 Job
- **THEN** 系统 SHALL 导航到 `/analysis/:jobId?return=/library/:kind/:sourceId?view=overview`
- **AND** SHALL NOT 直接回跳 Library Item 或任务列表

#### Scenario: 双摄 A/B 单机创建成功后进进度页

- **WHEN** 用户在 `RecordingAnalyzePage` 成功创建 A/B 单机分析 Job
- **THEN** 系统 SHALL 导航到 `/analysis/:jobId?return=<来源>`（来源为 Library Item 或采集控制台）
- **AND** 除既有任务上下文参数外 SHALL 保留 `return`

#### Scenario: 双摄协同 Parent 创建成功后进进度页

- **WHEN** 用户在 `MultiViewAnalysisSetupPage` 成功创建双摄协同 Parent Job
- **THEN** 系统 SHALL 导航到 `/analysis/:parentId?return=<来源>`
- **AND** SHALL 保留 `session` 与外层 `return`

#### Scenario: 全新上传无 return 时合成 Library return

- **WHEN** 用户从比赛库「上传视频」进入 `/upload`（此时无 `return` 且 `videoId` 尚未生成），上传成功并创建 Job
- **THEN** 系统 SHALL 以稳定 `videoId` 合成 `return=/library/upload/:videoId?view=overview`
- **AND** 进入 `/analysis/:jobId?return=<该合成 return>`
- **AND** 该路径 SHALL NOT 被识别为 `task-console`，返回/完成均回该上传素材的 Library Item

### Requirement: Progress 返回与完成去向 origin 化

`AnalysisJobPage` SHALL 依据 `resolveAnalysisFlowOrigin` 决定返回文案、返回路径与完成/失败/取消后的 CTA 目的地，而不得无条件使用 `taskListPathForJob(job)`。

#### Scenario: Library origin 返回比赛详情

- **WHEN** Progress 页的 origin 为 `library`
- **THEN** 顶部返回控件 SHALL 显示「返回比赛详情」
- **AND** 点击 SHALL 回到 `/library/:kind/:sourceId?view=overview`

#### Scenario: Library origin 完成后 CTA 指向 Workspace

- **WHEN** Progress 页的 origin 为 `library` 且任务完成
- **THEN**「查看数据分析 / 查看球路 / 查看报告 / 技术详情」SHALL 分别指向 `/library/:kind/:sourceId?view=analysis|trajectory|report|technical`
- **AND** SHALL NOT 指向 `/analysis/:jobId/...` 旧结果路由

#### Scenario: Library origin 失败/取消 CTA

- **WHEN** Progress 页的 origin 为 `library` 且任务失败或取消
- **THEN** 系统 SHALL 提供「返回比赛详情」与「再次分析」入口
- **AND** SHALL NOT 显示与来源不符的「重新上传」文案

#### Scenario: Task Console origin 保留旧行为

- **WHEN** Progress 页的 origin 为 `task-console`
- **THEN** 返回路径 SHALL 保持 `taskListPathForJob(job)`
- **AND** 完成 CTA SHALL 保留 `/analysis/:jobId/...` 工程结果路由

#### Scenario: Capture origin 返回采集控制台

- **WHEN** Progress 页的 origin 为 `capture`
- **THEN** 返回控件 SHALL 指向 `return` 携带的采集控制台路径

#### Scenario: Capture origin 完成后解析 Library 结果

- **WHEN** Progress 页 origin 为 `capture` 且任务完成
- **THEN**「查看分析结果」SHALL 经 `resolveLibraryRefFromAnalysisJob(job)`（复用 Library ownership 规则）解析 Library ref
- **AND** 解析成功时 SHALL 指向 `/library/:kind/:sourceId?view=analysis`
- **AND** 解析失败（无法归属到任一 LibraryItem）时 SHALL 降级 legacy `/analysis/:jobId/...` 工程结果

#### Scenario: Progress 完成页不承担重型产物探测

- **WHEN** Progress 完成页需要展示结果 CTA
- **THEN** 必有「查看分析结果」与「返回比赛详情」
- **AND** 次级 CTA（球路 / 报告 / 技术详情）SHALL 仅在已有轻量 capability metadata 时显示
- **AND** SHALL NOT 为 CTA 加载 GET result / trajectory / report / observability 等重产物
- **AND** 进入 Workspace 后 SHALL 由 `LibraryViewCapabilities` 统一门控结果可用性

### Requirement: Library-origin Progress 的 Sidebar 高亮

系统 SHALL 在 analysis 系列路由上，依据 `return` 是否以 `/library/` 开头，将 `navigationSection` 覆盖为 `library`；`return` 以 `/capture/` 开头则覆盖为 `capture`。路由解析 SHALL 保持纯函数可测。

#### Scenario: Library origin 高亮比赛库

- **WHEN** 路由为 `/analysis/job-1?return=/library/recording/r-1?view=overview`
- **THEN** 解析出的 `navigationSection` SHALL 为 `library`
- **AND** Sidebar「比赛库」SHALL 处于活跃态

#### Scenario: 无 return 的进度页保持 analysis 语义

- **WHEN** 路由为 `/analysis/job-1`（无 `return`）
- **THEN** `navigationSection` SHALL 保持原值，Sidebar 无对应一级项激活

### Requirement: source 词汇表收敛

`source` / `taskSource` 查询参数 SHALL 仅服务任务列表（`/analysis/tasks`）的来源上下文词汇表（`upload | recorded | sync_recording`）；transient 分析页的来源判定 SHALL 由 `return` 决定，不再依赖 `source`。系统 SHALL 对历史遗留的 `source=recording` 提供 `recording → recorded` 归一化，禁止因非法值静默回退为 `upload`。

#### Scenario: recording 别名归一化

- **WHEN** 任务上下文解析器收到 `source=recording`
- **THEN** 解析结果 SHALL 等价于 `source=recorded`
- **AND** SHALL NOT 回退为 `upload`

#### Scenario: transient 页不因 source 判定去向

- **WHEN** 任一分析创建页或 Progress 页需要决定返回/完成去向
- **THEN** 系统 SHALL 使用 `return`（经 `resolveAnalysisFlowOrigin`）判定
- **AND** `source` 只在其构造 `/analysis/tasks` 目的地时参与

### Requirement: Transient flow 浏览器历史语义

系统 SHALL 对 transient analysis flow 采用明确历史语义：Library/Capture → Setup 使用 push；Setup → Progress、Progress → Workspace 结果使用 replace；SyncCalibration 完成按嵌套 return 恢复（replace）。浏览器 Back 不得回到已提交的 Setup 或已完成的 Progress，避免重复创建 Job 或回到无意义中转态。

#### Scenario: Setup 到 Progress 使用 replace

- **WHEN** 用户在 Setup 创建 Job 成功并进入 Progress
- **THEN** 系统 SHALL 以 replace 语义导航
- **AND** 浏览器 Back SHALL NOT 回到已提交的 Setup（避免重复创建第二个 Job）

#### Scenario: Progress 到 Workspace 结果使用 replace

- **WHEN** 用户在 Progress 完成后进入 `/library/:kind/:sourceId?view=analysis`
- **THEN** 系统 SHALL 以 replace 语义导航
- **AND** 浏览器 Back SHALL NOT 回到已完成 Progress

#### Scenario: Library 到 Setup 使用 push

- **WHEN** 用户从 Library / Capture 首次进入分析 Setup
- **THEN** 系统 SHALL 以 push 语义导航，浏览器 Back SHALL 可回到来源

### Requirement: 稳定结果与瞬时执行分离（primaryResult / active）

系统 SHALL 将「稳定结果」与「瞬时执行」拆为两个 selection contract：`primaryResultAnalysisJobId` SHALL 为最新 **completed** 的权威结果（驱动结果 view 门控）；`activeAnalysisJobId` SHALL 为最新 active 任务（驱动进度展示，不参与结果门控）。再次分析进行中，旧 completed 结果 SHALL 保持可用，不得被 active 任务顶掉。

#### Scenario: 再次分析期间旧结果保持可用

- **WHEN** 素材已有 `primaryResultAnalysisJobId=Job A(completed)` 且用户触发再次分析（`activeAnalysisJobId=Job B(processing)`）
- **THEN**「数据分析 / 球路 / 报告 / 技术详情」SHALL 继续由 Job A 供给，保持可用
- **AND** 概览 SHALL 显示「正在重新分析 · N%」而不锁定结果视图

#### Scenario: 完成后切换 primaryResult

- **WHEN** Job B 由 processing 转为 completed
- **THEN** 经 reconciliation 重投影后 `primaryResultAnalysisJobId` SHALL 切换为 Job B
- **AND** `activeAnalysisJobId` SHALL 清空

#### Scenario: primaryResult 只取 completed

- **WHEN** `libraryAdapter` 选择 primaryResult
- **THEN** 系统 SHALL 只从 completed（且 public、非 internal child）任务中选取最新者
- **AND** active（queued / uploaded / processing）任务 SHALL NOT 成为 `primaryResultAnalysisJobId`

### Requirement: Live Analysis Projection 与素材身份解耦

系统 SHALL 将「素材身份」（`LibraryItemViewModel`）与「某次 Job 瞬时执行状态」解耦：素材投影 SHALL 暴露 `primaryResultAnalysisJobId` / `activeAnalysisJobId` / `analysisProgress` / `analysisStage`；瞬时执行状态 SHALL 以独立 `AnalysisRuntimeSnapshot`（jobId / status / progress / stage / stages / viewRuns）承载，不持久化、不与素材身份耦合。实时进度 SHALL 来自真实 Job 摘要，禁止伪造或硬编码。

#### Scenario: 投影真实进度字段

- **WHEN** `libraryAdapter` 投影一个存在 active job 的素材
- **THEN** ViewModel SHALL 携带 `activeAnalysisJobId` / `analysisProgress` / `analysisStage`
- **AND** 其值 SHALL 来自真实 `AnalysisJobSummary`（`progress` / 当前 `stages` 项）

#### Scenario: 共享 watch 定向轮询

- **WHEN** Library / Workspace / Card 任一界面订阅某 active job 的进度
- **THEN** 系统 SHALL 通过共享 `useAnalysisJobWatch(jobId)` + 单 scheduler 对每个 active job 调 `getAnalysisJob(jobId)` 更新 `AnalysisRuntimeSnapshot`
- **AND** SHALL NOT 为刷新进度全量轮询 `listAnalysisJobs`，也 SHALL NOT 重跑完整 `buildLibraryItems()`

#### Scenario: active→terminal 定向 reconciliation

- **WHEN** 某素材的 active Job 由 processing 转为 terminal（completed / failed / canceled）
- **THEN** 系统 SHALL 停止该 Job 高频轮询，并对该素材执行一次 `resolveLibraryItemByRef(ref)` 定向重投影
- **AND** `primaryResultAnalysisJobId` / `analysisHistoryCount` / `displayState` / capabilities SHALL 随之更新
- **AND** SHALL NOT 需要用户刷新页面才恢复结果视图
- **AND** `visibilitychange` 恢复可见时 SHALL 先执行一次 reconciliation

#### Scenario: 卡片显示真实进度

- **WHEN** 素材 `analysisState` 为 running
- **THEN** Library Card SHALL 显示真实 `analysisProgress`（如「正在分析 · 47%」）与当前 stage
- **AND** SHALL NOT 显示固定占比（如 2/3）的假进度
- **AND** 无真实 progress（如 queued）时 SHALL 使用非确定性态而非伪造百分比

#### Scenario: 运行时快照不污染素材身份

- **WHEN** 同一素材下某次 Job 的瞬时 progress/stage 变化
- **THEN** `LibraryItemRef`、`primaryResultAnalysisJobId` 等素材身份/稳定结果字段 SHALL 不被改动
- **AND** 重跑分析 SHALL 不改变素材 URL 与主卡身份

