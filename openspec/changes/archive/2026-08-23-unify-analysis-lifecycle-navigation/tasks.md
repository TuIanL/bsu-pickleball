# unify-analysis-lifecycle-navigation Tasks

## 1. P0 基础契约与路由基建

- [x] 1.1 在 `src/app/navigationTypes.ts` 新增 `AnalysisFlowOrigin` 三态联合类型（`library` / `task-console` / `capture`）
- [x] 1.2 在 `src/app/navigationContext.ts` 新增纯函数 `resolveAnalysisFlowOrigin(returnPath?, taskContext?)`：`/library/` → library（解析 itemKind/sourceId/returnPath）；`/capture/` → capture；缺失/非法 → task-console
- [x] 1.3 新增 URL builder 辅助：`appendReturnPath(path, returnPath)`、`buildAnalysisProgressPath(jobId, returnPath?, taskContext?)`、`buildSyncCalibrationPath(takeId, outerUrl)`；内部全部用 `URLSearchParams` 组装，`return` 做安全校验（站内绝对 path、以 `/` 开头、禁 `//`、Library kind whitelist），禁止手写字符串拼接
- [x] 1.4 `parseTaskListContext` 增加 `recording → recorded` 归一化别名，消除非法值静默回退 `upload`
- [x] 1.5 `router.ts` `parseLocation` 对 analysis 系列路由读取 `return`：以 `/library/` 开头覆盖 `navigationSection=library`，`/capture/` 开头覆盖为 `capture`；非法值安全忽略
- [x] 1.6 新增纯函数 `resolveLibraryRefFromAnalysisJob(job)`：按 Library ownership 规则（`recordingSessionId` / `capture_take_id` / `analysisKind` / `videoId`）解析 job → Library ref，用于 capture origin 完成后的结果定位；无法归属返回 null
- [x] 1.7 单测覆盖：`resolveAnalysisFlowOrigin` 三分支、`parseTaskListContext` 归一化、`parseLocation` return 覆盖与非法 return 不抛错、URL builder 安全校验（含 `//` 拒绝与 kind whitelist）、`resolveLibraryRefFromAnalysisJob` 命中/未命中

## 2. P0 分析创建路径统一

- [x] 2.1 `NewAnalysisPage` 创建成功去向：有 `return` → 原样转发；无 `return` 且已获得稳定 `videoId` → **合成** `/library/upload/:videoId?view=overview`（materialize Library return）；仅真正 Engineering origin（显式进入且无 Library return）才允许 fallback task-console
- [x] 2.2 `NewAnalysisPage` 创建成功进入 Progress 使用 **replace** 语义（Back 不回已提交的 Setup，避免重复创建）；失败/取消仍回 `return` 或任务列表
- [x] 2.3 `RecordingAnalyzePage`：创建成功后导航带 `return`（Library origin 用 `returnParam`；采集入口用 `return=/capture/:session`），使用 `buildAnalysisProgressPath`
- [x] 2.4 `MultiViewAnalysisSetupPage`：创建 Parent 成功后导航到 `/analysis/:parentId?return=<来源>`（replace），保留 `session`，使用 `buildAnalysisProgressPath`
- [x] 2.5 `MultiViewAnalysisSetupPage` 进入 SyncCalibration 改为**嵌套 return**：`buildSyncCalibrationPath(takeId, 完整上层 URL 含 session+外层 return)`
- [x] 2.6 验证 SyncCalibration 完成/取消后回到完整上层 URL（replace 恢复），外层 `session` 与 library `return` 均不丢
- [x] 2.7 更新 `NewAnalysisPage` / `RecordingAnalyzePage` / `MultiViewAnalysisSetupPage` 相关测试（去向 + replace 语义断言，含 fresh upload 合成 return）

## 3. P0 Progress 页 origin 化

- [x] 3.1 `AnalysisJobPage` 读取 `returnParam` 并用 `resolveAnalysisFlowOrigin(returnParam, taskContextForJob(job))` 推导 origin，替换无条件 `taskListPathForJob(job)`
- [x] 3.2 library origin：顶部返回控件显示「返回比赛详情」，路径 `/library/:kind/:sourceId?view=overview`
- [x] 3.3 library origin completed：必有「查看分析结果」（→ `?view=analysis`）+「返回比赛详情」；次级 CTA（球路/报告/技术详情）仅在已有轻量 capability metadata 时显示，**不加载 GET result / trajectory / report / observability 等重产物**
- [x] 3.4 library origin failed/canceled：改为「返回比赛详情」+「再次分析」（复用 `libraryAnalysisPathFor`），移除「重新上传」类不符文案
- [x] 3.5 capture origin：返回指向 `return` 的采集控制台；completed「查看分析结果」经 `resolveLibraryRefFromAnalysisJob(job)`——成功 → `/library/:kind/:sourceId?view=analysis`，失败 → legacy `/analysis/:jobId/...` 工程结果
- [x] 3.6 task-console origin：保持 `/analysis/tasks` 返回与工程结果 CTA；`withTaskListContext` 仅在该 origin 下为结果 URL 追加任务上下文参数
- [x] 3.7 Progress → Workspace 结果使用 **replace** 语义（Back 不回 completed Progress）
- [x] 3.8 更新 `AnalysisJobPage` 相关测试（library / capture / task-console 三 origin 的返回与 CTA + replace 语义）

## 4. P1 Live Analysis Projection

- [x] 4.1 新增 `src/services/analysisRuntimeStore.ts`（纯 TS store + scheduler，不含 React）：`AnalysisRuntimeSnapshot`（jobId / status / progress / stage / stages / viewRuns）`Map` + subscribe/notify
- [x] 4.2 scheduler 定向轮询：管理 active job IDs，对每个 job 调 `getAnalysisJob(jobId)`；concurrency ≤ 4、间隔 5s（Progress 页 1.6s 可并入按 job 差异化节流）、`document.hidden` 暂停、无 active job 即停；不重跑 `buildLibraryItems`
- [x] 4.3 新增 `src/hooks/useAnalysisJobWatch.ts`：用 `useSyncExternalStore` 订阅模块级 store（物理分离，StrictMode / 并发渲染稳定）
- [x] 4.4 `libraryAdapter`：新增 `selectLibraryAnalysisState(jobs)` → `primaryResultAnalysisJobId`（newest **completed** public，sync 只取 multiview Parent）/ `activeAnalysisJobId`（newest active）/ `analysisProgress` / `analysisStage`；`primaryAnalysisJobId` 语义收敛为 `primaryResultAnalysisJobId` 并迁移消费方（迁移期保留兼容别名）
- [x] 4.5 再次分析期间旧 completed 结果保持可用：`activeAnalysisJobId` 不参与结果 view 门控，结果仍由 `primaryResultAnalysisJobId` 供给
- [x] 4.6 `LibraryPage`：冷 build 一次（发现 active job IDs）→ scheduler 驱动卡片进度更新；`visibilitychange` 恢复可见先 reconcile 一次
- [x] 4.7 `LibraryCard`：running 时渲染真实 `analysisProgress` 进度条 + 当前 stage；无真实进度（queued）用 indeterminate，禁止硬编码固定占比
- [x] 4.8 `LibraryItemWorkspace` 概览：active 历史任务行显示「正在分析 · N% · stage」并提供「查看进度」→ `/analysis/:jobId?return=/library/...`；取消操作保留
- [x] 4.9 **Terminal reconciliation**：active → terminal 后停止该 Job 高频轮询 → 对该素材执行一次 `resolveLibraryItemByRef(ref)` 定向重投影（更新 `primaryResultAnalysisJobId` / `analysisHistoryCount` / `displayState` / capabilities）→ 清理 runtime snapshot
- [x] 4.10 测试：selection contract（再次分析不锁旧结果、primaryResult 只取 completed）、store 订阅更新、scheduler 定向轮询（不调全量 list）、Card 真实进度、terminal reconciliation 自动重投影、快照与素材身份解耦

## 5. P2 Workspace embedded 导航清理

- [x] 5.1 `VisionPage` 抽出 `VisionContent`；`AnalysisStatusRail` embedded 化（隐藏「返回任务管理 / 分析详情」旧导航，或改为 `onSelectView`）
- [x] 5.2 `BallTrajectoryPage` 抽出 Content：loading / failed / empty 态在 embedded 下渲染 workspace 侧空态，不再渲染 task-shell「返回任务管理 / 返回视觉分析」
- [x] 5.3 `AnalysisDetailsPage` 抽出 Content：embedded 隐藏完成态 header，loading / error / not found 态去 task-shell；active job 不再直接 return 完整 `AnalysisJobPage`
- [x] 5.4 `MultiviewObservabilityPage` 抽出 Content：error / no-summary 返回逻辑去 Task Context
- [x] 5.5 各 `*Content` 接受 `onSelectView(view)`：embedded 下结果切换留在同一 Library Item；standalone 回退 `/analysis/:jobId/...`
- [x] 5.6 `LibraryItemWorkspace` 改挂载 `*Content`（不再挂 `*Page`），Report 沿用 `ReportContent` 作为模板对齐
- [x] 5.7 测试：embedded 下各态不泄漏旧导航、`onSelectView` 切换留在工作区

## 6. 全链路回归验证

- [x] 6.1 链路一：比赛库「上传视频」（**全新上传无 return**）→ 上传 → 创建 → Progress（「返回比赛详情」）→ 完成 → `?view=analysis`，全程不进任务管理、不被识别为 task-console
- [x] 6.2 链路二：Library 双摄素材 → 双摄协同 → A/B 标定 → SyncCalibration（嵌套 return）→ 回到设置页 → 创建 Parent → 进度页 → 完成 → `?view=technical`
- [x] 6.3 链路三：现场采集进入 A/B 单机分析 → Progress 返回采集控制台（capture origin）；completed「查看分析结果」经 `resolveLibraryRefFromAnalysisJob` 进对应 LibraryItem，无法归属时降级工程结果
- [x] 6.4 链路四：Engineering Task Console 发起 → 进度页返回 `/analysis/tasks`，工程结果路由保留
- [x] 6.5 验证 Library 页/卡片/Workspace 在 active job 期间实时显示真实进度（无固定假进度）；再次分析期间旧结果 view 保持可用；完成后自动重投影为 completed
- [x] 6.6 Back 历史语义验证：Setup → Progress → Workspace 一路 replace，Back 不回已提交 Setup / 已完成 Progress（不产生重复 Job）
- [x] 6.7 `tsc` 与前端测试全绿；`/analysis/...` 旧路由 deep-link 与 `LegacyLibraryRouteResolver` 兜底不受影响
