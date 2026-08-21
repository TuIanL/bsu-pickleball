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

现有 `visual-analysis-workspace`、`report-detail-pages` 等行为契约 SHALL 保留，页面边界从独立结果页变为 workspace 的 view 内容组件；Workspace SHALL 直接消费抽取出的 `*Content` 组件，而非重新挂载完整 page shell；评估 `pb-vision-style-report` 的视觉组件纳入「报告」view。

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

