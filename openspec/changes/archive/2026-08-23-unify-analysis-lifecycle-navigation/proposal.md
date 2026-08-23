# unify-analysis-lifecycle-navigation

## Why

Library-first 重构完成后，分析生命周期仍然运行在旧 Job/Task-first 导航体系里：两套「导航坐标系」（LibraryItem Workspace 与 AnalysisJob `/analysis/...`）并存，导致创建后去向不一致、Library 来源 `return` 在进入进度页时丢失、Library 不实时刷新分析状态、分析完成后 CTA 跳回旧路由、Workspace 内部仍残留旧导航。用户感知为「切换粗糙、突然跳回任务管理、状态不同步、像两套系统」。

## What Changes

- 定义 **`return` 即 origin** 契约：`return` 查询参数是 transient analysis flow（Setup / Calibration / Progress）的唯一 canonical origin carrier。任何子流程 SHALL 原样转发已有 `return`，SHALL NOT 丢弃、简化或自行重建上游 `return`。
- 新增纯函数 `resolveAnalysisFlowOrigin(return?, taskContext?)`：由 URL 推导 origin（`library` / `task-console` / `capture`），是只读「视图」而非第二份可变状态，避免上下文漂移。
- 统一四种分析创建完成行为：upload / recording / sync A/B / sync 协同，全部 `create job → Analysis Progress → completed → Library Item Workspace`。`NewAnalysisPage` 创建成功后同样进入进度页，不再直接 `goReturn()` 回 Library。
- **SyncCalibration 嵌套 return**：进入同步标定时把「完整上一层 URL」（含 `session` 与外层 `return`）编码为 `return` 传入，完成后回到原样外层 URL；不得重建简化 return。
- Progress 返回来源按 origin 决定：Library origin 显示「返回比赛详情」并回到 `/library/...`；Task Console origin 回到 `/analysis/tasks`；Capture origin 回到采集对象。completed / failed / canceled CTA 全部指向 `/library/:kind/:sourceId?view=...`，普通产品流不再主动送用户去 `/analysis/...`。
- **Library-origin Progress Sidebar 高亮「比赛库」**：`parseLocation` 识别 analysis 路由上以 `/library/` 开头的 `return`，覆盖 `navigationSection` 为 `library`。
- **`recording` / `recorded` 语义收敛**：`source=` 查询参数只保留给 `/analysis/tasks` 的任务上下文词汇表；transient 分析页一律以 `return` 决定去向，不再用 `source` 判定来源，消除两套命名冲突。
- **Live Analysis Projection**：`LibraryItemViewModel` 增加 `activeAnalysisJobId` / `analysisProgress` / `analysisStage`（取自 `listAnalysisJobs` 已有字段，无需新接口）；抽出共享 `useAnalysisJobWatch(jobId)`；Library 只在存在 active job 时轻量轮询 `listAnalysisJobs` 并 merge runtime snapshot，不重跑完整 `buildLibraryItems()`；Library Card 显示真实进度与当前阶段（替换固定 `w-2/3` 假进度）；Workspace active 历史任务行增加「查看进度」入口。
- **Workspace 内 embedded 导航清理**：Vision（含右侧 `AnalysisStatusRail`）、BallTrajectory、AnalysisDetails、Multiview 的 loading / failed / empty / success 状态统一消费 `*Content` + `onSelectView(view)`，embedded 时结果切换保持在同一个 Library Item，不泄漏旧导航。Report 已基本符合，作为模板。
- 旧 `/analysis/:jobId(/vision|details|trajectory|multiview|reports/...)` 路由 SHALL 保留，承担兼容与 Engineering Console deep-link，但**普通产品流不再主动把用户送过去**。

**BREAKING**：`NewAnalysisPage` 创建成功后的去向从「直接回 Library Item」改为「进入 Analysis Progress」（随后 completed 回 Library Item）。这是统一行为的必要变更，同时更新 `frontend-architecture-boundaries` 既有「上传创建后进入比赛详情」要求。

## Capabilities

### New Capabilities

- `analysis-flow-navigation`: transient analysis flow（Setup → Calibration → Progress）的统一导航上下文契约：`return` 即 origin、`resolveAnalysisFlowOrigin`、origin 完整转发、嵌套 return、完成后去向、origin 化返回文案、Library-origin Sidebar 高亮、`source` 词汇表收敛、Live Progress Projection（runtime snapshot 与素材身份解耦、共享 watch、真实进度）。

### Modified Capabilities

- `library-analysis-start`: 分析创建页携带来源上下文进入时，创建成功后统一进入 Analysis Progress（含转发 `return`），而非部分类型直接回来源；返回路径契约不变并强化为「原样转发 return」。
- `library-analysis-recreate`: 再次分析（recreate）创建成功后同样统一进入 Analysis Progress，转发来源 `return`。
- `library-item-workspace`: Workspace 成为结果统一宿主，embedded 内容（Vision/球路/技术详情/报告）不得泄漏旧导航；概览 active 历史任务提供「查看进度」；Workspace 实时消费真实 Job progress。
- `analysis-task-management`: Engineering Task Console 保留旧 `/analysis/...` 结果路由；普通产品流不再进入；Task Console origin 的返回保持回任务列表。
- `frontend-architecture-boundaries`: 上传/采集/录制创建后的落点从「直接进工作区」更新为「进 Analysis Progress → completed 进工作区」；路由解析支持从 `return` 推导 origin 与 `navigationSection` 覆盖；Page → `*Content` 边界继续收敛。

## Impact

纯前端变更，无后端改动。

- 路由/导航基建：`src/app/router.ts`、`src/app/navigationTypes.ts`、`src/app/navigationContext.ts`、`src/App.tsx`
- 分析创建页：`NewAnalysisPage.tsx`、`RecordingAnalyzePage.tsx`、`MultiViewAnalysisSetupPage.tsx`、`SyncCalibrationWorkbench`（调用方）
- 进度页：`AnalysisJobPage.tsx`
- Library：`libraryAdapter.ts`、`libraryAnalysisRouting.ts`、`LibraryPage.tsx`、`LibraryItemWorkspace.tsx`、`LibraryCard.tsx`
- 结果页 embedded 清理：`VisionPage.tsx`、`BallTrajectoryPage.tsx`、`AnalysisDetailsPage.tsx`、`MultiviewObservabilityPage.tsx`
- Sidebar：`AppSidebar.tsx`（仅消费 `navigationSection`，无结构改动）
- 新增共享 hook：`useAnalysisJobWatch`；新增 origin 解析：`resolveAnalysisFlowOrigin`
