## Context

双摄录制与视频分析链路已经功能完整，但存在五处影响体验的 UI/交互问题（详见 proposal）。所有改动集中在三个前端页面与一个任务卡片组件，均为纯前端行为调整，不涉及后端 API、数据模型或路由结构变化。相关页面与既有导航工具（`taskListPathForJob` / `withTaskListContext` / `/analysis/:id/multiview` 路由）均可直接复用。

## Goals / Non-Goals

**Goals:**
- 双摄录制任务卡片内分析任务分组改为网格布局，提升空间利用率。
- 球路查看页空态/失败态保证始终有可用返回路径。
- 视频分析结果页提供直达双摄协同详情的入口，消除三步绕行。
- Debug Replay 资源可用时自动加载，同时保留手动卸载/重载。
- 球员显示诊断改为逐 tick 默认折叠的列表，控制页面高度。
- 全部改动保持现有测试与既有行为兼容，并为关键交互补充测试。

**Non-Goals:**
- 不改后端 API、observability summary schema 或产物格式。
- 不改路由层与导航上下文协议。
- 不做双摄链路外的其他 UX 优化（如单摄录制页布局）。
- 不引入新依赖或设计系统。

## Decisions

### D1: 任务分组网格布局使用响应式 grid（`AnalysisTasksPage.tsx`）

当前 `renderTaskGroup` 在 `divide-y` 容器内纵向全宽渲染"双摄协同分析 → A 机位 → B 机位 → 其他"。方案：外层改为 `grid gap-2`；`cam_1`/`cam_2` 两个分组包在 `grid gap-2 sm:grid-cols-2` 容器内并排，`multiview` 分组与 `unassigned` 分组保持全宽行。`renderTaskGroup` 组件的标题、任务数徽标、历史展开、任务操作逻辑全部复用，仅调整容器与边框样式（`border-b` → `divide` 移除，改用 gap 布局）。

**备选**：重写 `renderTaskGroup` 支持 `columnSpan` 属性。否决——侵入更大，且组件内大量交互逻辑无必要改动。

### D2: 球路空态返回导航基于 URL 上下文生成（`BallTrajectoryPage.tsx`）

空态/失败态在既有"返回视觉分析"按钮旁新增"返回任务管理"按钮，路径用 `taskListPathForJob(job)`（job 为 null 时该函数基于 `window.location.search` 的 `taskContextFromLocation` 仍可生成带来源上下文的路径）。加载中态与正常态头部已有点击返回，无需改动。

### D3: VisionPage 头部新增双摄协同入口（`VisionPage.tsx`）

在头部"查看球路"按钮旁（`jobId` 分支内）新增"查看双摄协同详情"按钮，显示条件 `job?.analysisKind === "multiview" && job?.status === "completed"`，导航 `contextualPath(\`/analysis/${jobId}/multiview\`)`。`contextualPath` 已基于 `taskContextForJob(job)` 保留来源上下文。

**备选**：在 status rail 内新增入口。否决——头部与"查看球路"并列更符合用户"分析结果页直达"的预期，且 status rail 已承载过多状态信息。

### D4: Debug Replay 默认自动加载 + 卸载/重载（`MultiviewObservabilityPage.tsx`）

`DebugReplayPanel` 的 `enabled` 初始值由 `false` 改为在"资源可用"时 `true`（`useState(() => section.availability === "available" && Boolean(data.video_available))`），使 `<video>` 直接渲染。保留"卸载"按钮（`setEnabled(false)`）与卸载后的"重新加载"按钮（`setEnabled(true)`），并在面板文案中说明：canonical debug MP4 为四联拼合大文件，按需加载是为了避免每次打开详情页无条件下载大文件；自动加载是为"想看回放"的用户省去一次点击。`selectedSeek` 定位逻辑不变。

**风险**：自动加载可能在网络受限场景产生额外流量 → 卸载按钮与文案提供显式退出与解释，用户可手动卸载。

### D5: 诊断行折叠用受控 state 而非 `<details>`（`MultiviewObservabilityPage.tsx`）

`PlayerDisplayDiagnosticsPanel` 中每个 tick 卡片改为"标题行 + 详情区"结构：标题行常显（`view_id · tick · timestamp · frame_status` 徽标 + 展开箭头），详情区默认折叠；用 `expandedRowKey` state（`\`${row.canonical_tick}-${row.view_id}\``）控制展开项，允许同时展开多行（Set），满足"行展开互不影响"的 spec 要求。

**备选**：原生 `<details>`。否决——需要支持多行同时展开且保留测试可断言性，受控 state 更直接；`<details>` 的展开状态不可编程控制。

## Risks / Trade-offs

- [自动加载大体积 MP4 增加流量] → 提供卸载/重载控制与文案解释；仅 `video_available=true` 时自动加载。
- [诊断行折叠改变测试断言] → `MultiviewObservabilityPage.test.tsx` 断言"cam_1 · tick 210 · 7000ms"位于标题行，折叠后仍渲染，兼容；新增展开交互断言。
- [网格布局窄屏挤压] → 使用 `sm:grid-cols-2` 断点，窄屏自动回退纵向堆叠。
- [空态返回按钮依赖 URL 上下文] → `taskListPathForJob(null)` 在无显式来源时回退 `upload` 来源，仍有可用返回路径；不会出现无按钮状态。

## Migration Plan

无数据迁移。前端改动随下一次构建发布；各页面改动相互独立，可按 task 逐个合入。回滚：恢复对应页面文件即可，无状态或 schema 残留。

## Open Questions

- 诊断行展开是否需要"全部展开/全部折叠"批量控制？MVP 按单行展开实现，后续按反馈补充。
- Debug Replay 自动加载是否需要后端提供文件体积提示以增强文案？当前用通用说明，不阻塞实现。
