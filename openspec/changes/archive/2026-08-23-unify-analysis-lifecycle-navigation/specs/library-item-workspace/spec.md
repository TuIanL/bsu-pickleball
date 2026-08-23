# library-item-workspace Specification

## Purpose
LibraryItemWorkspace 作为素材统一工作区，结果视图 embedded 化且不泄漏旧导航；概览实时消费 Job progress 并提供「查看进度」入口。

## MODIFIED Requirements

### Requirement: 复用现有结果页组件为 workspace content

现有 `visual-analysis-workspace`、`report-detail-pages` 等行为契约 SHALL 保留，页面边界从独立结果页变为 workspace 的 view 内容组件；Workspace SHALL 直接消费抽取出的 `*Content` 组件，而非重新挂载完整 page shell；评估 `pb-vision-style-report` 的视觉组件纳入「报告」view。embedded 状态下，`*Content` 的 loading / failed / empty / success 各态 SHALL 均不渲染旧 page shell（标题 / 返回 / 任务导航），结果切换 SHALL 通过 `onSelectView(view)` 保持在同一个 Library Item 内。

#### Scenario: 报告 view 呈现 PB 风格组件但无独立抽屉/mock

- **WHEN** 素材存在权威分析结果时进入报告 view
- **THEN** 报告 view SHALL 复用 PB 风格视觉组件（Skill Card / Player Header / Court Coverage / Serves & Returns / Coach Insight / Filter）
- **AND** SHALL NOT 展示报告独立抽屉栏（PbPlayerDrawer / PbDrawerExpander）或报告专属导航
- **AND** SHALL NOT 为真实任务伪造无权威数据支撑的结论（mock 服从 performance-insights 证据约束）

#### Scenario: 数据分析 view 复用分析 Content

- **WHEN** 用户处于 workspace `?view=analysis`
- **THEN** 系统 SHALL 渲染抽取出的分析 `*Content`
- **AND** SHALL NOT 渲染旧页面自带的完整 page shell（标题/返回/导航）

#### Scenario: 旧结果页逐步收敛

- **WHEN** workspace 外壳建立后逐个吸收入口组件
- **THEN** 旧 page shell SHALL 在全部迁移完成前保留，不提前删除导致断链

#### Scenario: embedded 下结果切换留在工作区

- **WHEN** 用户在 workspace 内某个结果 view（如 `?view=analysis`）点击「查看球路 / 技术详情 / 报告」
- **THEN** 系统 SHALL 通过 `onSelectView("trajectory" | "technical" | ...)` 切换到同一素材的对应 view
- **AND** SHALL NOT 离开该 Library Item 跳转到 `/analysis/:jobId/...` 独立页

#### Scenario: embedded 下异常态不泄漏旧导航

- **WHEN** 结果 view 处于 loading / failed / empty 状态且由 workspace 嵌入
- **THEN** 系统 SHALL 显示 workspace 侧的空态/错误态
- **AND** SHALL NOT 渲染旧 task-shell（如「返回任务管理 / 返回视觉分析」）或完整 `AnalysisJobPage`

### Requirement: 依据素材状态门控 view

工作区各 view SHALL 依据素材状态可用/禁用，符合「先素材后分析」的生命周期；结果类 view 的可开性须同时满足 `mediaState=ready`、`analysisState=succeeded` 且存在该 view 所需的真实产出物。

#### Scenario: 素材未分析时不可见分析/球路/报告

- **WHEN** 素材 mediaState 为 `recording` / `processing` 或 analysisState 为 `not_started`
- **THEN**「视频」「片段」等素材视图可用，而「数据分析」「球路」「报告」等分析视图 SHALL 不可用或提示待分析

#### Scenario: 分析完成后可见结果视图

- **WHEN** mediaState 为 `ready` 且 analysisState 为 `succeeded` 且存在对应 view 的真实产出物
- **THEN**「数据分析」「球路」「报告」等结果视图 SHALL 可用

#### Scenario: 有任务但缺该 view 产出物

- **WHEN** 素材存在分析与 `primaryAnalysisJobId` 但未产出球路/报告等特定 artifact
- **THEN** 该结果类 view SHALL 不可用或显示空态，不得渲染空白结果，亦不得仅凭 jobId 判定可用

## ADDED Requirements

### Requirement: 概览 active 历史任务提供查看进度与实时进度

素材工作区概览 SHALL 实时消费该素材 active 分析 Job 的真实进度（百分比与当前 stage），并为 active 历史任务提供「查看进度」入口，而不是只有取消操作。

#### Scenario: active 任务行显示真实进度

- **WHEN** 素材概览列出处于 queued / uploaded / processing 的历史任务
- **THEN** 该行 SHALL 显示「正在分析 · N% · 当前阶段」（N 来自真实 Job progress）
- **AND** SHALL NOT 显示固定假进度或仅有状态文字

#### Scenario: active 任务提供查看进度入口

- **WHEN** 素材概览存在 active 历史任务
- **THEN** 该行 SHALL 提供「查看进度」操作
- **AND** 点击 SHALL 进入 `/analysis/:jobId?return=/library/:kind/:sourceId?view=overview`

#### Scenario: 实时进度不依赖手动刷新

- **WHEN** 用户在素材概览停留且该素材存在 active Job
- **THEN** 概览 SHALL 通过共享 `useAnalysisJobWatch` 实时更新 progress / stage
- **AND** SHALL NOT 要求用户刷新页面或触发 reload 才看到最新进度

#### Scenario: 再次分析期间旧结果保持可用

- **WHEN** 素材存在 completed 结果且用户触发再次分析（active Job 运行中）
- **THEN**「数据分析 / 球路 / 报告 / 技术详情」SHALL 继续由 completed 结果供给，保持可用
- **AND** 概览 SHALL 显示「正在重新分析 · N%」而不锁定结果视图

#### Scenario: 任务完成后概览自动重投影

- **WHEN** 素材的 active Job 由 processing 转为 terminal（如 completed）
- **THEN** 系统 SHALL 对该素材执行一次定向 `resolveLibraryItemByRef(ref)` 重投影
- **AND** `primaryResultAnalysisJobId` / `analysisHistoryCount` / capabilities SHALL 随之更新
- **AND** SHALL NOT 需要用户刷新页面才恢复结果视图
