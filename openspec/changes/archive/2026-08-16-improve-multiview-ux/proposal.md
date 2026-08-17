## Why

双摄录制与视频分析链路已具备完整功能，但多处的页面布局与交互流程停留在"功能可用"而非"体验顺手"：双摄任务分组纵向全宽堆叠浪费空间、球路空态无返回入口、从视频分析结果页进入协同详情需要绕行任务管理、Debug Replay 每次都要手动加载、球员显示诊断随 tick 无限向下撑长页面。本次一次性收敛这五处 UX 问题，降低用户在双摄分析链路中的操作成本。

## What Changes

- 双摄录制会话卡片内的分析任务分组改为网格化布局：**A 机位分析** 与 **B 机位分析** 并排同一行，**双摄协同分析** 单独占据一行，其他任务保持尾部全宽；解决当前纵向全宽排列空间利用率低、观感不佳的问题。
- 球路查看页（`/analysis/:id/trajectory`）在"暂无可用球路"与"读取失败"空态中补充**返回任务管理**入口，与既有"返回视觉分析"并存，确保任何情况下都可返回上一级页面。
- 视频分析结果页（`/analysis/:id/vision`）头部在双摄协同任务完成时新增**查看双摄协同详情**按钮，直达 `/analysis/:id/multiview`，省去"返回任务管理 → 进入任务详情 → 再进入协同详情"的三步绕行。
- 双摄协同详情页的 Debug Replay 面板在 canonical MP4 可用时**自动加载并播放**，不再要求每次手动点击；保留"卸载/重新加载"控制并在面板内说明大体积回放文件按需加载的设计权衡。
- 双摄协同详情页的"球员显示诊断"面板改为**折叠式列表**：每个 tick 默认只显示标题行（视角 · tick · 时间 · 帧状态），点击展开完整漏斗字段，控制页面高度。

## Capabilities

### New Capabilities

无新增能力，全部为既有功能的 UI/交互行为变化。

### Modified Capabilities

- `sync-recording-task-listing`: 双摄录制会话卡片内分析任务分组由纵向全宽排列改为网格化布局（A/B 机位分析并排、双摄协同分析独立成行）。
- `ball-trajectory-visualization`: 球路空态/失败态补充返回任务管理导航，保证始终有可用返回路径。
- `visual-analysis-workspace`: 视频分析结果页为双摄协同任务新增直达协同详情的入口按钮。
- `multiview-joint-observability`: Debug Replay 面板由手动加载改为资源可用时自动加载，并保留卸载/重载控制；per-player 显示诊断由逐 tick 全量展开改为默认折叠的列表交互，控制页面高度。

## Impact

- **前端页面（全部改动为纯前端，无后端/API 变化）**：
  - `src/pages/AnalysisTasksPage.tsx` — `renderTaskGroup` 容器布局改网格（需求 1）。
  - `src/pages/BallTrajectoryPage.tsx` — 空态/失败态补返回任务管理按钮（需求 2）。
  - `src/pages/VisionPage.tsx` — 头部加"查看双摄协同详情"按钮（需求 3）。
  - `src/pages/MultiviewObservabilityPage.tsx` — `DebugReplayPanel` 自动加载（需求 4）、`PlayerDisplayDiagnosticsPanel` 折叠交互（需求 5）。
- **导航/路由**：复用既有 `taskListPathForJob`、`withTaskListContext` 与 `/analysis/:id/multiview` 路由，无路由层改动。
- **测试**：`MultiviewObservabilityPage.test.tsx`（诊断标题行断言需保持兼容）、`AnalysisTasksPage.test.tsx`、`AppRouter.test.tsx` 等现有断言应继续通过；为需求 2/3/4/5 新增组件测试。
- **依赖**：无新增依赖。
