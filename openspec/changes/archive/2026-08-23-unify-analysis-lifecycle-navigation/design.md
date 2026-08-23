# unify-analysis-lifecycle-navigation Design

## Context

Library-first 重构后，用户产品层（`/library/:kind/:sourceId?view=...`）与工程层（`/analysis/:jobId...`）并存，但**分析生命周期仍运行在旧的 Job/Task-first 导航体系里**。经代码核验的现状：

- 三类创建路径行为不一致：[NewAnalysisPage](file:///Users/tuian/Documents/大学/竞赛/大创/匹克球/前期展示web/pre-pickleball/src/pages/NewAnalysisPage.tsx#L142-L143) 创建后 `goReturn()` 直接回来源；[RecordingAnalyzePage](file:///Users/tuian/Documents/大学/竞赛/大创/匹克球/前期展示web/pre-pickleball/src/pages/RecordingAnalyzePage.tsx#L128) 与 [MultiViewAnalysisSetupPage](file:///Users/tuian/Documents/大学/竞赛/大创/匹克球/前期展示web/pre-pickleball/src/pages/MultiViewAnalysisSetupPage.tsx#L259) 直接进 `/analysis/:jobId`。
- `AnalysisJobPage` 完全不读 Library 来源：`const returnPath = taskListPathForJob(job)`（[AnalysisJobPage.tsx](file:///Users/tuian/Documents/大学/竞赛/大创/匹克球/前期展示web/pre-pickleball/src/pages/AnalysisJobPage.tsx#L27)），返回文案固定「返回任务管理」，完成 CTA 全指向 `/analysis/...`。
- SyncCalibration 进入时重建缩水 return：`return=/capture/takes/:takeId/analyze`（[MultiViewAnalysisSetupPage.tsx](file:///Users/tuian/Documents/大学/竞赛/大创/匹克球/前期展示web/pre-pickleball/src/pages/MultiViewAnalysisSetupPage.tsx#L450)），吃掉 `session` 与外层 `/library/...` return。
- `LibraryPage` 只在 mount 时 `buildLibraryItems()` 一次（[LibraryPage.tsx](file:///Users/tuian/Documents/大学/竞赛/大创/匹克球/前期展示web/pre-pickleball/src/pages/LibraryPage.tsx#L23-L40)）；`LibraryItemWorkspace` 只在 `reloadToken` 变化时重载（[LibraryItemWorkspace.tsx](file:///Users/tuian/Documents/大学/竞赛/大创/匹克球/前期展示web/pre-pickleball/src/components/library/LibraryItemWorkspace.tsx#L55-L74)），无实时刷新。
- `LibraryCard` 在 running 时渲染固定 `w-2/3` 假进度（[LibraryCard.tsx](file:///Users/tuian/Documents/大学/竞赛/大创/匹克球/前期展示web/pre-pickleball/src/components/library/LibraryCard.tsx#L170)）。
- `LibraryItemViewModel` 只有 `analysisState / primaryAnalysisJobId / analysisJobs`，无 progress 字段（[libraryAdapter.ts](file:///Users/tuian/Documents/大学/竞赛/大创/匹克球/前期展示web/pre-pickleball/src/services/libraryAdapter.ts#L67-L103)）；但 `listAnalysisJobs` 返回完整 `AnalysisJobSummary`（含 `progress / stages / viewRuns`），adapter 只截取了 `id/status/kind/date`。
- Workspace 结果视图 embedded 不彻底：`VisionPage` 顶部 header 受 `!embedded` 控制，但右侧 `AnalysisStatusRail` 的「分析详情 / 下级报告 / 返回任务管理」无条件渲染（[VisionPage.tsx](file:///Users/tuian/Documents/大学/竞赛/大创/匹克球/前期展示web/pre-pickleball/src/pages/VisionPage.tsx#L1030-L1055)）。
- `source=recording`（Library 入口写入）与 `parseTaskListContext` 只认 `recorded` 冲突（[navigationContext.ts](file:///Users/tuian/Documents/大学/竞赛/大创/匹克球/前期展示web/pre-pickleball/src/app/navigationContext.ts#L22-L26)），非法值回退为 `upload`。
- Sidebar 只有 比赛库/现场采集/设备与设置（[AppSidebar.tsx](file:///Users/tuian/Documents/大学/竞赛/大创/匹克球/前期展示web/pre-pickleball/src/components/platform/AppSidebar.tsx#L23-L25)），而 `analysis-job` 等路由仍标 `navigationSection: "analysis"`，进入进度页后三个一级菜单都不高亮。

约束：纯前端改动，无后端变更；旧 `/analysis/...` 路由保留作兼容与 Engineering Console deep-link。

## Goals / Non-Goals

**Goals:**

1. 建立 **`return` 即 origin** 的单一来源契约，消灭「来源被丢弃后回错地方」这一类 bug。
2. 统一四种分析创建的完成行为：`create → Analysis Progress → completed → Library Item Workspace`。
3. 分析进行中，Library / Workspace / Card 实时消费真实 Job progress（stage + 百分比），替换固定假进度。
4. 分析完成后，普通产品流的所有结果入口回到 Library Item Workspace（`?view=analysis|trajectory|report|technical`），不再把用户送进 `/analysis/...`。
5. Workspace 内 embedded 内容彻底收敛为 `*Content`，不泄漏旧导航。
6. Library-origin 的 Progress 页 Sidebar 高亮「比赛库」，维持产品上下文。

**Non-Goals:**

- 不重写 `AnalysisJobPage` 的轮询 / `JobStageStepper` / progress / cancel 机制——它已成熟，只加「origin 感知」。
- 不删除 `/analysis/...` 旧路由——它们继续承担工程控制台与历史 deep-link。
- 不改任何跟踪 / 融合算法、权威指标与后端 API。
- 不为实时进度引入新后端接口（`listAnalysisJobs` / `getAnalysisJob` 已含所需字段）。
- 不处理无历史数据支撑的展示（如 Δ 值、长期平均线），沿用既有证据约束。

## Decisions

### D1：`return` 即 origin，不建第二份可变状态

**决策**：`return` 查询参数是 transient analysis flow 的唯一 canonical origin carrier；`AnalysisFlowOrigin` 由 URL 推导，是只读视图，不是可漂移的独立状态。

```ts
type AnalysisFlowOrigin =
  | {
      kind: "library";
      itemKind: "upload" | "recording" | "sync_recording";
      sourceId: string;
      returnPath: string; // 完整 /library/... 路径
    }
  | {
      kind: "task-console";
      taskContext: TaskListContext;
    }
  | {
      kind: "capture";
      returnPath: string; // 采集控制台 /capture/:session 路径
    };

resolveAnalysisFlowOrigin(returnPath?: string | null, taskContext?: TaskListContext): AnalysisFlowOrigin;
```

- `return` 以 `/library/...` 开头 → `kind: "library"`，解析出 itemKind/sourceId。
- `return` 以 `/capture/` 开头 → `kind: "capture"`。
- 无 `return`（或非上述前缀）→ 回退 `kind: "task-console"`（使用既有 `taskContextForJob(job)`）。
- 该纯函数放 `src/app/navigationContext.ts`（或同模块），保证可测。

**为什么不是平行 Context**：若另建 `AnalysisFlowContext` 状态并到处传递，等于维护「URL + 状态」两套真相，任何子流程忘记同步都会复现本轮 bug。`return` 本身已编码全部 origin 信息，且天然随 URL 持久化、刷新不丢。

**备选方案**：React Context / 模块级可变状态 → 刷新即丢、需层层传递、易漂移，否决。

**唯一例外（Fresh Upload）**：从比赛库「上传视频」进入 `/upload` 时，`videoId` 尚未生成，不存在上游 LibraryItem，因此没有可转发的 `return`。此时 SHALL 在拿到稳定 `videoId` 后 **materialize** 一个 Library return（`/library/upload/:videoId?view=overview`），再进入 Progress。这不算「重建上游 return」（因为上游不存在），且防止该路径被误判为 `task-console`（否则会出现「比赛库 → 上传 → 创建后 → 返回任务管理」的反向漏网流程）。仅真正 Engineering origin（显式进入 `/analysis/new` 且无 Library return）才允许 fallback 到 task-console。

### D2：所有分析创建成功 → Analysis Progress，转发 `return`

**决策**：统一为 `create job → /analysis/:jobId?return=<上游 return> → completed → /library/...`。

- `NewAnalysisPage`（upload / recording）：创建成功后改为 `onNavigate(withReturn(\`/analysis/${job.id}\`, returnParam))`，不再 `goReturn()`。需保留 `returnParam` 供失败/取消时回退。
- `RecordingAnalyzePage`（sync A/B）：`withTaskListContext(\`/analysis/${job.id}\`, taskContext)` 改为同时携带 `return`（优先 Library `returnParam`；采集入口则携带 `return=/capture/:session`）。
- `MultiViewAnalysisSetupPage`（双摄协同）：同上，`/analysis/${parent.id}?return=...`。

统一封装：新增辅助 `analysisJobProgressPath(jobId, returnPath?, taskContext?)`，组装进度页 URL。

**为什么进 Progress 而不是统一回 Workspace 靠轮询**：`AnalysisJobPage` 已具备 1.6s 轮询、stage stepper、双摄 A/B progress、cancel、失败上下文；双摄流程本就走进度页。统一到 Progress 是更小 delta，且把「执行中」明确为 LibraryItem 生命周期里的 transient execution，而非把轮询逻辑再复制进 Workspace。Workspace 只做轻量状态展示（P1）。

### D3：Progress 从 origin 推导返回与完成去向

**决策**：`AnalysisJobPage` 读取 `resolveAnalysisFlowOrigin(returnParam, taskContextForJob(job))`：

| origin | 返回文案 | 返回路径 | 完成 CTA |
|---|---|---|---|
| library | 返回比赛详情 | `/library/:kind/:sourceId?view=overview` | `?view=analysis / trajectory / report / technical` |
| task-console | 返回任务管理 | `taskListPathForJob(job)` | 保留 `/analysis/:jobId/...`（工程语义） |
| capture | 返回现场采集 | `/capture/:session` | 结果仍回 Library Item（若存在）或工程结果 |

- 完成态 CTA：library origin 下「查看分析结果」指向 `?view=analysis`；若已有轻量 capability metadata，可显示「查看球路 / 查看报告 / 技术详情」快捷 CTA（`?view=...`）。**Progress 页不为此加载重产物**（GET result / trajectory / report / observability 等一律不做）——进入 Workspace 后由 `LibraryViewCapabilities` 统一门控。
- 失败/取消态：library origin 下「重新上传」改为「返回比赛详情」+「再次分析」（复用 `libraryAnalysisPathFor`），不再出现「重新上传」这类与来源不符的文案。
- capture origin 完成后：「返回」→ `return` 携带的采集控制台；「查看分析结果」→ 通过 `resolveLibraryRefFromAnalysisJob(job)`（复用 Library ownership 规则：`recordingSessionId` / `capture_take_id` / `analysisKind` / `videoId`）解析 Library ref，成功 → `/library/:kind/:sourceId?view=analysis`，失败 → legacy `/analysis/:jobId/...` 工程结果。
- `withTaskListContext` 只在 task-console origin 下为结果 URL 追加 `taskSource/taskSession` 参数；library/capture origin 不再携带任务上下文参数。

### D4：SyncCalibration 嵌套 return

**决策**：进入同步标定时把**完整上一层 URL**（含 `session` 与外层 `return`）编码为 `return`，不得重建：

```ts
// MultiViewAnalysisSetupPage 现状（错误）：
`/sync-calibration?take=TAKE&return=${encodeURIComponent(`/capture/takes/TAKE/analyze`)}`

// 目标（嵌套 return）：
const outerUrl = `/capture/takes/${take}/analyze?session=${session}&return=${encodeURIComponent(libraryReturn)}`;
`/sync-calibration?take=${take}&return=${encodeURIComponent(outerUrl)}`
```

`SyncCalibrationWorkbench` 已支持 `returnPath`，无需改动；问题仅在调用方传入缩水 return。完成/取消后回到外层 URL，外层继续持有完整 library `return`，链条不断。

**不变量（写入 spec）**：任何 Setup / Calibration / Progress 子流程 SHALL 原样转发已有 `return`；SHALL NOT 丢弃、简化或自行重建上游 `return`。

### D5：`source` 词汇表收敛

**决策**：`source=/taskSource=` 只服务 `/analysis/tasks` 的任务上下文词汇表（`upload | recorded | sync_recording`）；transient 分析页的去向一律由 `return` 决定，不再用 `source` 判定来源。

- `parseTaskListContext` 增加 `recording` → `recorded` 归一化别名（兼容 Library 入口既有写入），消除误回退 `upload`。
- `libraryAnalysisRouting` / 各创建页不再依赖 `source` 做导航分支；`source` 仅在构造 task-list 目的地时使用。

### D6：Library-origin Progress 的 Sidebar 高亮

**决策**：`parseLocation` 对 analysis 系列路由检查 `return` 是否以 `/library/` 开头，是则覆盖 `navigationSection: "library"`。`RouteState` 保持纯函数、可测，不需要把 origin 对象塞进状态。

```ts
// parseLocation 内，analysis 路由分支：
const params = new URLSearchParams(search);
const returnPath = params.get("return");
const section = returnPath?.startsWith("/library/")
  ? "library"
  : routeMeta[route.name].navigationSection;
```

capture origin（`return` 以 `/capture/` 开头）同理覆盖为 `capture`。

### D7：Live Analysis Projection（P1）

**决策**：把「稳定结果」与「瞬时执行」拆为两个 selection contract，并把实时 watch 从「全量列表轮询」改为「按 active job 定向轮询」。

**Selection contract**（`libraryAdapter` 新增 `selectLibraryAnalysisState(jobs)`）：

```ts
// 稳定结果（驱动结果 view 门控；语义收敛自 primaryAnalysisJobId）：
primaryResultAnalysisJobId?: string;  // newest COMPLETED 权威结果
// 瞬时执行（驱动进度展示，不影响结果可用性）：
activeAnalysisJobId?: string;
analysisProgress?: number;   // 0-100
analysisStage?: string;      // 当前 stage 文案

// 独立运行时快照层（瞬时执行状态，不入库不持久）：
interface AnalysisRuntimeSnapshot {
  jobId: string;
  status: AnalysisJobSummary["status"];
  progress: number;
  stage?: string;
  stages: AnalysisJobSummary["stages"];
  viewRuns?: AnalysisJobSummary["viewRuns"];
}
```

- upload / recording：`primaryResultAnalysisJobId` = 最新 **completed** public job；`activeAnalysisJobId` = 最新 active（queued/uploaded/processing）public job。
- sync：`active` 与 `primaryResult` 均只取 public multiview Parent；A/B 单摄不参与（沿用既有 D9 契约）。
- **关键行为——再次分析不锁旧结果**：`activeAnalysisJobId=Job B(processing)` 时不顶掉 `primaryResultAnalysisJobId=Job A(completed)`；「数据分析 / 球路 / 报告 / 技术详情」继续由 Job A 供给。Job B completed 后经 reconciliation 重投影，`primaryResultAnalysisJobId` 切换到 Job B、`activeAnalysisJobId` 清空。

**Runtime watch**（独立快照层，不入库不持久）：

- 新增 `src/services/analysisRuntimeStore.ts`（纯 TS store + scheduler）与 `src/hooks/useAnalysisJobWatch.ts`（`useSyncExternalStore` 订阅）。物理分离，避免 StrictMode / 并发渲染下订阅不稳。
- **Cold build（discovery）**：`buildLibraryItems()` 一次找出当前 `activeAnalysisJobIds`。
- **Scheduler（定向轮询）**：单 scheduler 管理 active job IDs，对每个 job 调 `getAnalysisJob(jobId)`；concurrency ≤ 4、间隔 5s（Progress 页自身 1.6s 可并入同一 scheduler 按 job 差异化节流）、`document.hidden` 暂停、无 active job 即停。
- **不重跑 buildLibraryItems**：实时路径只更新 runtime snapshot，不改素材身份。
- **Terminal reconciliation**：active → terminal 后停止该 job 高频轮询，对该素材执行一次 `resolveLibraryItemByRef(ref)`（非全库 build），重投影 `primaryResultAnalysisJobId / analysisHistoryCount / displayState / capabilities`，并清理 runtime snapshot；`visibilitychange` 恢复可见时先 reconcile 一次。
- `LibraryCard`：running 时渲染真实 `analysisProgress` + stage；无真实 progress（queued）用 indeterminate，禁止硬编码。
- `LibraryItemWorkspace` 概览：active 行显示「正在分析 · N% · stage」+「查看进度」→ `/analysis/:jobId?return=/library/...`；`resolveLibraryItemByRef` 一次冷读后由 watch 驱动进度刷新。

**为什么不用全量 `listAnalysisJobs` 轮询**：`GET /api/analysis/jobs` 无 active filter，默认返回全部 public 历史任务；历史任务多时（数百/数千）每 5s 全量下载不是轻量 watch。改用 cold build 发现 active IDs + 按 job 定向 `getAnalysisJob`，通常同时 active 的 job 数极少，可扩展。`listAnalysisJobs` 仍用于冷投影（其字段已含 `progress/stages/viewRuns`，adapter 此前丢弃，属 spec/implementation gap——`library-item-projection` 已要求「正在分析 62%」）。

### D8：Workspace embedded 收敛为 `*Content` + `onSelectView`

**决策**：延续 Report 已建立的模式（`ReportContent` → `PbReportContent`），把 Vision / BallTrajectory / AnalysisDetails / Multiview 各抽 `*Content` 组件：

```tsx
interface ContentProps {
  jobId: string;
  embedded?: boolean;
  onNavigate: NavigateFn;
  onSelectView?: (view: LibraryView) => void; // embedded 时由 Workspace 提供
}
```

- embedded 时：结果切换（如 Vision 内「查看球路 / 技术详情 / 报告 / 分析详情」）调 `onSelectView("trajectory" | "technical" | ...)`，留在同一 Library Item；standalone 时回退旧 `/analysis/...` 路由。
- `AnalysisStatusRail` 必须 embedded 感知：embedded 下隐藏「返回任务管理 / 分析详情」等旧导航，或改为 view 切换。
- loading / failed / empty 状态不得再渲染 task-list `StatusState`（含「返回任务管理」），embedded 下给 Workspace 侧的空态/错误态。
- 页面外壳 `*Page` 保留，仅做 standalone 渲染，不再被 Workspace 直接挂载。

### D9：Transient flow 的浏览器历史语义

**决策**：Library/Capture → Setup 用 `push`；Setup → Progress、Progress → Workspace 结果用 `replace`；SyncCalibration 完成按嵌套 return 恢复（replace 回 Setup）。

```text
Library
  ↓ push
Library Item
  ↓ push
Setup
  ↓ replace
Progress
  ↓ replace
Library Item / Analysis
```

**为什么**：Progress 是已提交执行的结果，Back 回到已提交的 Setup 会造成「再次点击开始分析 → 重复创建 Job」的危险；completed Progress 也是无意义历史态。replace 保证 Back 不经过 submitted Setup / completed Progress。SyncCalibration 进入时把完整上层 URL 作为嵌套 return，完成 replace 恢复，Back 同样不回到标定表单残留。

### D10：URL builder 与 return 安全

**决策**：统一 `appendReturnPath(path, returnPath)`、`buildAnalysisProgressPath(...)`、`buildSyncCalibrationPath(...)`，内部全部用 `URLSearchParams` 组装，禁止手写字符串拼接。`return` SHALL 为站内绝对 path：以 `/` 开头、禁止 `//` 前缀、Library kind 走 whitelist（upload / recording / sync_recording），非法值安全忽略。

**为什么**：本轮出现过多处「重建 return / 缩水 return / encode 不一致」bug；集中 builder + 校验可避免第二轮 encode/decode 与路径注入问题，也保证 D1 的「原样转发」不变量在代码层面由 builder 强制。

## Risks / Trade-offs

- **嵌套 return 使 URL 变长、可读性差** → `encodeURIComponent` 单参数传递，实际长度可控；不透明但正确，换取链条不丢。
- **upload/recording 用户新增一个 Progress 页跳转** → 属明确的产品决策（统一生命周期）；进度页已完成大部分打磨，感知为「更明确的执行反馈」。
- **P1 轮询负载** → 不用全量 `listAnalysisJobs` 轮询；cold build 发现 active IDs，按 job 定向 `getAnalysisJob`，concurrency ≤4、无 active 即停、`document.hidden` 暂停。
- **进度页与 Library 轮询双重请求** → 同一 scheduler 按 job 差异化节流（进度页 1.6s / Library 5s），避免双源。
- **假进度回归（又写死一个数）** → 卡片 progress 一律来自 snapshot；无真实值时用 indeterminate，禁止硬编码。
- **再次分析期间误锁旧结果** → `primaryResultAnalysisJobId` 只取 completed，`activeAnalysisJobId` 不参与结果门控；terminal reconciliation 兜底。
- **`return` 指向的素材被删除/迁移** → `AnalysisJobPage` 解析 origin 失败时回退 task-console 行为，不抛错。
- **旧 deep-link / 书签进 `/analysis/...`** → 路由保留；`LegacyLibraryRouteResolver` 已具备的 job→library 解析继续兜底。

## Migration Plan

按 P0 → P1 → P2 三阶段独立落地、各自可回归：

1. **P0 Navigation Correctness**：`return 即 origin` 契约 + `resolveAnalysisFlowOrigin`；三种创建页统一进 Progress 并转发 return；`AnalysisJobPage` origin 化返回/CTA；SyncCalibration 嵌套 return；Sidebar 高亮；`source` 词汇表归一。本阶段完成后普通产品流不再跳错地方。
2. **P1 Live Analysis Projection**：`AnalysisRuntimeSnapshot` + `useAnalysisJobWatch` + `analysisRuntimeStore`；ViewModel 三个新字段；LibraryPage/Workspace/Card 消费真实进度；active 任务「查看进度」。
3. **P2 Workspace Navigation Cleanup**：抽 `*Content` + `onSelectView`；`AnalysisStatusRail` embedded 化；各页 loading/failed/empty 态去 task-shell。

回滚：纯前端，逐阶段 revert 对应 commit 即可；`return` 转发是增量行为，回退不破坏旧路径。`/analysis/...` 路由全程保留。

## Open Questions

- **capture completed 的 Library 归属歧义**：`/capture/:session` 可能同时映射 recording 与 sync_recording 两类 LibraryItem；`resolveLibraryRefFromAnalysisJob(job)` 以 job 的 ownership 字段（`recordingSessionId` / `capture_take_id` / `analysisKind` / `videoId`）消歧，无法消歧时降级 legacy 工程结果。
- **`primaryAnalysisJobId` 字段迁移**：将现有 `primaryAnalysisJobId` 语义收敛为 `primaryResultAnalysisJobId`（newest completed）并迁移消费方；迁移期保留兼容别名，避免一次性破坏 Workspace 门控与既有测试。
- **scheduler 节流粒度**：Progress 页 1.6s 与 Library 5s 由同一 scheduler 按 job 差异化节流；若引入成本高，允许 Progress 页保留自身 1.6s 轮询、store 只服务 Library 侧（阶段内评估）。
- **`analysisProgress` 快照在无 subscriber 时的保真度**：Library 卡只在用户停留时 watch；返回 Library 瞬间先显示冷 build 的粗粒度状态，随后 store 补齐，接受短暂旧值。
