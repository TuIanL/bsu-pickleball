## Why

Library-first 的统一素材工作区（`/library/:kind/:id`）已经具备正确的信息架构，但当前停留在「新 Workspace 外壳把旧整页硬塞进去」的阶段：每个 Tab 因条件渲染 bug 把其他 Tab 的空态全部渲染出来、双摄素材的视频 Tab 永远无法打开、Report 在 Workspace 内仍挂载独立 Drawer、数据分析里出现「页面套页面」的第二套标题与返回按钮。这导致用户看到的是一个拼接线明显的后台系统，而非一个统一工作区。需要一次收尾修复，把 Workspace composition contract 真正落地。

## What Changes

- **P0 · 修复所有 view 条件渲染 bug**：`LibraryItemWorkspace` 的 6 个 view 区块都缺少 view 守卫，导致非当前 view 也渲染各自的空态；改为 `effectiveView === xxx && (有内容 ? Content : EmptyState)`。
- **P0 · 打开双摄素材的视频 Tab**：`video` view 统一三类来源的视频分派 —— `upload` 用 `SourceVideoContent(videoId)`（经 `GET /api/videos/{videoId}/stream` 播放源视频）、`recording`/`sync_recording` 用 `RecordingWorkspaceContent`（内部已支持 single/dual 自动判定）；`availabilityState=unavailable` 时展示明确不可用状态。
- **P0 · Report 不再在 Workspace 内弹出独立 Drawer**：Workspace 的 `report` view 不再走完整 `ReportPage`（它会挂 `PbVisionReportLayout` 的 `PbPlayerDrawer`），改为内嵌 `PbReportContent`（复用现有 Pb* 组件，去掉 Drawer 骨架）；legacy 报告路由保持原样。
- **P1 · 抽取 Content 层，消灭「页面套页面」**：把 `VisionPage / ReportPage / BallTrajectoryPage / RecordingWorkspacePage / SegmentManagerPage / MultiviewObservabilityPage / AnalysisDetailsPage` 拆出可嵌入式 `*Content` 组件（数据加载 + 渲染一起抽），旧路由 `PageFrame + Content`，Workspace `Content`。
- **P1 · view capability 门控基于 AnalysisResult manifest**：引入 `LibraryViewCapabilities`，由「primary Job 状态 + AnalysisResult artifact manifest（`cleaned_ball_trajectory_url` / `ball_trajectory_url` / `reportId` 等）」一次判定各 view 可开性，避免逐一拉重产物造成请求风暴；缺产的 view 停在原 URL 显示「本次分析未生成该数据」，非法 view 才落到 overview。
- **P2 · Library 语义去工程化**：标题不再直接取 `court_name`，改为分析 metadata → FieldSession 标题 →「时间 + 比赛形式」；`buildLibraryItems` 一次性 `listFieldSessions()` 建 Map join（禁 N+1）；卡片标签去重（去掉 source+双摄+camera 重复）；场次/资产 ID 不再在用户层展示原值。
- **P2 · Thumbnail conditional（非本 Change 硬验收）**：`LibraryCard` 有稳定 `thumbnailUrl/previewUrl` 时渲染真实封面，无则中性占位且不在前端伪造截图；真实预览（poster 字段、hover preview、缓存）另开 `add-library-media-previews` Change。
- **P2 · 菜单与筛选收敛**：未实现的菜单项（重命名/下载/分享/upload 删除等）在未接通前隐藏或明确禁用；状态 tab 由底层 `mediaState` 改为统一 `displayState`（待处理/正在分析/分析完成/失败）语义。
- **P2 · 顺手修正 sync primary fallback**：明确无 multiview Parent 时 `primaryAnalysisJobId` 即为 `undefined`，删除代码里虚假的 single-view fallback 注释并补测试。

## Capabilities

### New Capabilities
- `workspace-content-composition`: 把旧整页拆出可嵌入式 `*Content` 组件、修复 Workspace 各 view 条件渲染正确性、双摄视频接入、view capability 门控——即「Workspace → Content 层」这个缺失的 composition contract。
- `library-semantic-metadata`: 标题解析策略、fieldSession/captureTake 工程 ID 去暴露、卡片标签去重、thumbnail/preview 有则消费否则中性占位、基于 `displayState` 的统一状态筛选与菜单 action 门控。

### Modified Capabilities
- `report-detail-pages`: 报告在 Library Workspace 中作为 report view 内容渲染，不再挂载独立抽屉/独立导航；既有的独立报告路由（`/reports/:type`、`/analysis/:jobId/reports/:type`）与 legacy 布局保留。
- `library-item-workspace`: view 条件渲染正确性、`sync_recording` 视频可开、capability 门控改为基于真实产出物；结果类 view 消费 `effectiveView && gate` 结构。
- `library-item-projection`: `LibraryItemViewModel` 增加语义标题与 `displayState` 推导；标题解析策略落地（court_name 降级为次要 metadata）。

## Impact

- **Frontend**
  - `src/components/library/LibraryItemWorkspace.tsx`：重构为 view 守卫 + Content 分发 + capability 门控。
  - `src/pages/{VisionPage,ReportPage,BallTrajectoryPage,RecordingWorkspacePage,SegmentManagerPage,MultiviewObservabilityPage,AnalysisDetailsPage}.tsx`：拆分 `*Content` 与 legacy `PageFrame` 外壳。
  - 新增 `src/components/pb-vizion/PbReportContent.tsx`（复用现有 Pb* 组件，去 Drawer）。
  - `src/services/libraryAdapter.ts`：`LibraryItemViewModel` 增加 `displayState`、语义 `title`、`thumbnailUrl/previewUrl`。
  - `src/pages/LibraryPage.tsx`、`src/components/library/LibraryCard.tsx`：displayState 筛选、真实封面、菜单 action 门控、去无效 DOM（nested button / 无 relative 的 absolute 菜单）。
  - 相关单测更新与新增。
- **API/后端**：无接口形状变化；仅消费已存在的 thumbnail/preview 与 FieldSession metadata（如缺字段则以语义化降级展示）。
- **风险**：内容抽取若误改 legacy 页面渲染，会回归旧路由；通过保留 legacy 路由 + 测试兜底控制。

**BREAKING**: `LibraryItemViewModel` 新增 `displayState` 字段（补数据侧 `buildLibraryItems`/`resolveLibraryItemByRef`）、`title` 语义化——依赖 `title === court_name` 的旧 UI 需同步调整。