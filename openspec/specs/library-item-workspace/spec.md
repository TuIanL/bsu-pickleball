# library-item-workspace Specification

## Purpose
TBD - created by archiving change reframe-library-and-match-workspace. Update Purpose after archive.
## Requirements
### Requirement: LibraryItemWorkspace 作为一个素材的统一工作区

系统 SHALL 提供 `/library/:kind/:sourceId` 下的统一工作区，将 Vision / Report / BallTrajectory / Segment / RecordingPlayback / Details / Multiview 收敛为该素材下不同 view。

#### Scenario: 进入比赛/训练/采集详情
- **WHEN** 用户点击某个 LibraryItem
- **THEN** 系统 SHALL 进入该素材的工作区，并依据素材上下文显示「比赛详情 / 训练详情 / 采集详情」标题

#### Scenario: view 切换
- **WHEN** 用户点击工作区一级 Tab（概览 / 视频 / 数据分析 / 球路 / 报告 / 片段 / 技术详情）
- **THEN** 系统 SHALL 切换工作区内内容，且对应 view 反映在 URL query（`?view=...`）

### Requirement: 依据素材状态门控 view

工作区各 view SHALL 依据素材状态可用/禁用，符合“先素材后分析”的生命周期；结果类 view 的可开性须同时满足 `mediaState=ready`、`analysisState=succeeded`、存在该 view 所需真实产出物，并且报告 view 还必须存在至少一类有效报告证据。仅有 completed Job、jobId 或空 result manifest 不得判定报告可用。

#### Scenario: 素材未分析时不可用分析结果

- **WHEN** 素材 `mediaState` 为 `recording` / `processing` 或 `analysisState` 为 `not_started`
- **THEN** “数据分析”“球路”“报告”等结果类 view SHALL 置灰、禁用或提示待分析

#### Scenario: 分析完成且报告有有效证据

- **WHEN** `mediaState=ready`、`analysisState=succeeded`、selected Job 的 result manifest 可读取，且至少存在有效 canonical 场地轨迹点、有效运动指标条目或 available structured visualization artifact
- **THEN** “报告”Tab SHALL 可用并可进入

#### Scenario: 分析完成但没有有效报告证据

- **WHEN** selected completed Job 的 tracks、运动指标和 structured visualization artifact 均为空、无效、失败或跳过
- **THEN** 顶部“报告”Tab SHALL 保持可见但置灰并设置原生 `disabled`
- **AND** 点击或程序化 view 切换 SHALL 不得进入报告内容
- **AND** SHALL 提供“暂无有效报告数据”或等价原因

#### Scenario: 有任务但缺该 view 产出物

- **WHEN** 素材存在分析与 `primaryAnalysisJobId` 但未产出球路/报告等特定 artifact
- **THEN** 该结果类 view SHALL 不可用或显示明确空态，不得渲染空白结果，亦不得仅凭 jobId 判定可用

#### Scenario: 再次分析期间旧结果保持有效性

- **WHEN** 素材存在 completed 结果且用户触发再次分析
- **THEN** 结果 view SHALL 继续由旧 completed Job 的有效证据供给
- **AND** active Job 的空结果或处理中状态 SHALL NOT 覆盖旧结果的 capability

### Requirement: Workspace 路由与历史语义

系统 SHALL 采用 `pushState` 于层级跳转、`replaceState` 于工作区内 view 切换。

#### Scenario: Library → Workspace 入栈
- **WHEN** 用户从 `/library` 点击一场比赛
- **THEN** 系统 SHALL `pushState` 到 `/library/sync/sr-123?view=overview`

#### Scenario: 工作区内 view 替换
- **WHEN** 用户在 `?view=video` 下点击「数据分析」
- **THEN** 系统 SHALL `replaceState` 到 `?view=analysis`，不新增历史记录

#### Scenario: 报告证据跳回视频
- **WHEN** 用户在报告 view 点击证据跳回视频定位
- **THEN** 系统 SHALL `replaceState` 到 `?view=video&t=26300`，仍在同一素材对象内

#### Scenario: Back 回到 Library
- **WHEN** 用户在 `?view=analysis` 按一次浏览器 Back
- **THEN** 系统 SHALL 回到 `/library`，而非逐 view 回退

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

### Requirement: 工作区支持选择历史分析版本

素材工作区 SHALL 允许用户从当前素材所属的公开历史分析任务中选择要查看的版本。工作区 SHALL 将同一 selected Job 用于数据分析、球路、报告和技术详情，MUST NOT 在不同结果 Tab 间混用不同 Job 的产物。

#### Scenario: 选中已完成历史任务
- **WHEN** 用户对属于当前素材的 completed 公开 Job 点击“查看结果”
- **THEN** 工作区 SHALL 将该 Job 标记为当前选中版本
- **AND** 数据分析、球路、报告和技术详情 SHALL 全部读取该 Job

#### Scenario: 选中版本在 Tab 切换中保持
- **WHEN** 用户已选中 Job A，并在数据分析、球路、报告或技术详情间切换
- **THEN** 每个 Job-bound 结果 Tab SHALL 继续读取 Job A
- **AND** 工作区 MUST NOT 因 Tab 切换恢复到最新 Job

#### Scenario: 无显式选择时使用最新结果
- **WHEN** 工作区 URL 未指定 analysisJob
- **THEN** 结果视图 SHALL 使用 primaryResultAnalysisJobId 指向的最新 completed 公开 Job
- **AND** 现有无 analysisJob 的 Library 深链 SHALL 保持可用

#### Scenario: 显式选择不被新任务顶掉
- **WHEN** 用户显式选中 Job A 后另一个 Job B 完成并成为新的 primary result
- **THEN** 当前工作区 SHALL 继续显示 Job A
- **AND** 系统 MAY 提示有新版本可用，但 MUST NOT 自动改变用户选择

### Requirement: selected Job 必须通过素材归属校验

工作区 SHALL 仅允许将当前 LibraryItem 所属的公开 Job 解析为 selected Job。跨素材 Job、internal child、不存在或已删除 Job MUST NOT 被用于加载结果产物。

#### Scenario: URL 指向其他素材的 Job
- **WHEN** analysisJob 指向一个存在但不属于当前 LibraryItem 的 Job
- **THEN** 工作区 SHALL 拒绝将其解析为 selected Job
- **AND** SHALL 回退到当前素材的 primary result 或无结果态
- **AND** SHALL NOT 请求该跨素材 Job 的报告或 artifact

#### Scenario: URL 指向 internal child
- **WHEN** analysisJob 指向 multiview Parent 的 internal source child
- **THEN** 工作区 SHALL 将该选择视为无效
- **AND** 历史版本选择器 SHALL NOT 列出该 internal child

#### Scenario: 选中任务被删除
- **WHEN** 当前 selected Job 被删除或刷新后已无法解析
- **THEN** 工作区 SHALL 定向重投影当前素材
- **AND** SHALL 回退到最新 completed 结果或无结果态
- **AND** SHALL 以 replace 语义清理失效 analysisJob

### Requirement: 历史版本的结果边界按 Job 自身确定

工作区 SHALL 依据 selected Job 自身的 status、analysisKind 和 AnalysisResult manifest 决定可打开的结果视图与技术详情类型。

#### Scenario: 历史 Job 缺少球路产物
- **WHEN** selected completed Job 未生成可用球路 artifact
- **THEN** 球路 view SHALL 显示“该版本未生成球路”类明确空态
- **AND** MUST NOT 显示最新 Job 或其他历史 Job 的球路

#### Scenario: 双摄素材选中 A/B 单摄 Job
- **WHEN** sync_recording 素材中 selected Job 的 analysisKind 为单摄分析
- **THEN** 技术详情 SHALL 打开该 Job 的单摄 AnalysisDetails
- **AND** SHALL NOT 仅因素材类型是 sync_recording 而打开 MultiviewObservability

#### Scenario: 选中失败或取消任务
- **WHEN** 用户查看 failed 或 canceled 历史 Job
- **THEN** 工作区 SHALL 显示该 Job 自身的状态、失败阶段和可用诊断
- **AND** 数据分析、球路与报告 MUST NOT 借用任何 completed Job 的产物

