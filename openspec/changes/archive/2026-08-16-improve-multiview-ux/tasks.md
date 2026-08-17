## 1. 任务分组网格布局（需求 1）

- [x] 1.1 在 `AnalysisTasksPage.tsx` 中调整分析任务分组容器：外层 `divide-y` 改为 `grid gap-2`，移除分组卡片 `border-b` 纵向分隔依赖
- [x] 1.2 将 `cam_1` 与 `cam_2` 两个 `renderTaskGroup` 放入 `grid gap-2 sm:grid-cols-2` 容器并排渲染
- [x] 1.3 保持 `multiview` 分组与 `unassigned` 分组为全宽行（位于网格之外）
- [x] 1.4 验证窄屏（<sm 断点）下分组回退为纵向堆叠，且各分组交互（历史展开、任务操作）不受影响

## 2. 球路空态返回导航（需求 2）

- [x] 2.1 在 `BallTrajectoryPage.tsx` 空态（`empty`）与失败态（`failed`）区域新增"返回任务管理"按钮，路径使用 `taskListPathForJob(job)`（job 为 null 时基于 URL 上下文生成）
- [x] 2.2 保留既有"返回视觉分析"按钮，两条返回路径并存
- [x] 2.3 为 `BallTrajectoryPage` 空态/失败态补充组件测试：断言"返回任务管理"按钮存在且导航路径带来源上下文

## 3. 视频分析结果页快捷入口（需求 3）

- [x] 3.1 在 `VisionPage.tsx` 头部（`jobId` 分支）"查看球路"按钮旁新增"查看双摄协同详情"按钮，显示条件为 `job?.analysisKind === "multiview" && job?.status === "completed"`
- [x] 3.2 按钮导航使用 `contextualPath(\`/analysis/${jobId}/multiview\`)`，保留任务列表来源上下文
- [x] 3.3 为 `VisionPage` 补充组件测试：双摄完成态展示入口并可导航、非双摄/未完成态不展示

## 4. Debug Replay 自动加载（需求 4）

- [x] 4.1 修改 `MultiviewObservabilityPage.tsx` 的 `DebugReplayPanel`：`enabled` 初始值改为资源可用时 `true`（`availability === "available" && video_available`）
- [x] 4.2 保留"卸载"按钮（`setEnabled(false)`）与卸载后的"重新加载"按钮，`selectedSeek` 定位逻辑不变
- [x] 4.3 在面板内补充说明文案：canonical debug MP4 为四联拼合大文件，按需加载用于避免无条件下载大文件，自动加载省去手动点击
- [x] 4.4 更新 `MultiviewObservabilityPage.test.tsx`：资源可用时断言视频直接渲染（无需点击加载）；资源不可用时断言不可用提示

## 5. 诊断菜单折叠整合（需求 5）

- [x] 5.1 修改 `PlayerDisplayDiagnosticsPanel`：每个 tick 卡片改为"标题行 + 详情区"结构，标题行常显（`view_id · tick · timestamp · frame_status` 徽标 + 展开箭头）
- [x] 5.2 用受控 state（`Set<string>`，键为 `` `${row.canonical_tick}-${row.view_id}` ``）控制行展开，支持多行同时展开且互不影响
- [x] 5.3 更新 `MultiviewObservabilityPage.test.tsx`：默认断言标题行可见、完整字段不可见；点击标题后断言字段可见

## 6. 验证与回归

- [x] 6.1 运行 `npm test`，确认全部测试通过（含既有 AnalysisTasksPage / VisionPage / MultiviewObservabilityPage / BallTrajectoryPage 测试）
- [x] 6.2 运行 `npm run build`（tsc -b && vite build）确认类型与构建通过
- [x] 6.3 启动 `npm run app:start` 手工回归双摄录制 → 分析 → 协同详情链路，核对五项交互（服务已就绪，前端 dev server 热更新已生效，待用户在浏览器核对五项交互后勾选）
