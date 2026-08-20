## Why

当前前端的信息架构已经出现结构性矛盾：底层技术对象模型（FieldSession → CaptureTake → RecordingSession / SyncRecordingSession → AnalysisJob → Vision/Report/Trajectory/Observability）被直接暴露成用户导航层级，普通用户被迫在「上传任务 / 录制任务 / 双摄任务」之间理解后台对象关系。与此同时，`layered-product-navigation` 与 `app-sidebar` 两份 canonical spec 表达了互斥的两套导航架构（极简顶导 vs 固定六项侧边栏），代码实际执行后者，因而沿用后端 Job 对象作为用户主对象。以 PB Vision 的 `/library` 为参照，用户真正想表达的是「这是我的一场比赛/一个视频」，而非一组 AnalysisJob。

## What Changes

- 将用户层的用户对象模型从 **Job-centric 重构为 Library-centric**：引入统一的 Library Item 投影（upload / recording / sync_recording），`recorded-task-grouping` 的 FieldSession 分组能力从任务页迁入比赛库
- 保留 Job-centric 的工程层能力（Parent/Child、Pipeline Stage、取消/删除/批量/重试、可观测性），将其从一级主导航降级为工程模式入口
- **BREAKING**：一级主导航收敛为「比赛库 / 现场采集 / 设备与设置」；「分析任务」「报告中心」退出主导航；`/workspace` 保留路由但 alias 到 `/library`，Dashboard 本 Change 不做
- **BREAKING**：新增 `library-item-workspace`，将 Vision / Report / BallTrajectory / SegmentManage / RecordingWorkspace / AnalysisDetails / MultiviewObservability 等「兄弟结果页」收敛为同一工作区下不同 view
- **BREAKING**：契约冻结——`AnalysisJob.recordingSessionId` 升格为新建 sync recording 分析的 canonical ownership reference；`metadata.capture_take_id` 仅作 legacy fallback；P0 不新增 `syncRecordingSessionId` 字段、不新建后端 Match/MediaAsset 实体
- 引入双正交状态模型：媒体生命周期（mediaState）× 分析生命周期（analysisState）
- `pb-vision-style-report-page` 的视觉组件保留，但其「报告独立抽屉 / 报告专属导航 / real-job mock」与新方向冲突，纳入重构后由 workspace「报告」view 承载，mock 服从 `performance-insights` 证据约束
- 保留旧入口兼容：`/analysis/tasks`、`/tasks` 作为工程任务控制台 alias 继续工作，普通用户不暴露

## Capabilities

### New Capabilities
- `library-item-projection`: 将 upload / recording / sync_recording 投影为统一 LibraryItem 用户对象，含双正交生命周期状态与「identity 与 AnalysisJob 分离」原则
- `match-library`: 比赛库页面——缩略图卡片、搜索/筛选/状态、FieldSession 分组、生命周期显示
- `library-item-workspace`: 一个素材上下文下的统一工作区，承载视频/分析/球路/报告/片段/技术详情等 view

### Modified Capabilities
- `layered-product-navigation`: 从「双 workflow + 任务历史」首页模型改为 Library-first 导航；明确训练页软隐藏与工程层入口
- `app-sidebar`: 一级导航重定义——比赛库/现场采集/设备与设置；`/workspace` alias 到 `/library`；底部活跃录制块保留
- `frontend-architecture-boundaries`: 增加 Library route 与 workspace route 的 pathname/search 纯函数解析与 history 契约
- `analysis-task-management`: 从用户一级页面降为 Engineering Task Console，保存 Job 工程能力但默认不暴露
- `recorded-task-grouping`: FieldSession 对录制的分组能力从任务页迁入 Library
- `sync-recording-task-listing`: 双摄录制收敛为一个 Library Item；`recordingSessionId` 升格为 canonical ownership 契约
- `visual-analysis-workspace`: 从独立结果页变成 LibraryItemWorkspace 内的子 view，行为契约保留
- `report-detail-pages`: 报告进入统一 workspace「报告」view，独立报告外壳移除
- `legacy-analysis-workflow-consolidation`: 为旧 route（`/analysis/tasks`、`/tasks`、`/reports/:type` 等）增加兼容映射

## Impact

**Affected code**:
- `src/app/router.ts` / `navigationTypes.ts` / `AppRouter.tsx` / `navigationContext.ts` — 新增 Library/Workspace route，定义 view 的 replace/push 语义与 `/workspace` canonical redirect；旧 sibling RouteState 迁移期保留，由 `LegacyLibraryRouteResolver` 在 P3 收敛
- 新增 `src/pages/LibraryPage.tsx`、`src/services/libraryAdapter.ts`、`src/components/library/*` 与 `library-item-workspace` 外壳
- `src/pages/AnalysisTasksPage.tsx` — **保留现有 Job-centric 能力并原地降级为 Engineering Console**，不作为 Library 主实现基础；后续 cleanup 阶段按需拆组件
- `src/pages/ReportPage.tsx` 等结果页 → 收敛为 workspace 内容组件

**Affected APIs / dependencies**:
- 后端**不新建 domain entity、不新增 `syncRecordingSessionId`**；仅两处极小的 API/语义调整：
  1. 新增只读 `GET /api/videos` catalog（枚举现有 VideoMetadata），支撑 upload LibraryItem 独立资产生命周期；无新表
  2. 收敛 AnalysesJob 删除 source media 的旧级联行为——**删除 AnalysisJob ≠ 删除 Library source video**（资产所有权契约）
- 前端保证新建 sync recording Parent 正确写入 `recordingSessionId`（若缺则修创建链路 wiring，不扩 Schema）
- 前端依赖无新增（复用现有 img/ECharts/Three.js）

**Affected systems**:
- 用户主导航、比赛库、workspace 路由；工程任务控制台迁移至工程模式；AppShell 侧边栏