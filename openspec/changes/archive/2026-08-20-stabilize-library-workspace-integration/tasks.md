## 1. P0A · Rendering correctness（Workspace 条件渲染 bug）

- [x] 1.1 重构 `LibraryItemWorkspace` 内容区：把 6 个 view 区块统一改为 `effectiveView === xxx && (gate ? Content : EmptyState)` 两段式守卫，消除「非当前 view 渲染 else 空态」
- [x] 1.2 验证 `?view=overview` 不再出现其他 view 空态；`?view=analysis` 不再出现跨 view 空态

## 2. P0B · 统一 video 视频分派

- [x] 2.1 `upload` → 新建 `SourceVideoContent(videoId)`（经 `GET /api/videos/{videoId}/stream` 播放源视频），接入 Workspace video view
- [x] 2.2 `recording` / `sync_recording` → `RecordingWorkspaceContent(sessionId)`（解开 `kind === "recording"` 限制），双摄可回放
- [x] 2.3 `availabilityState=unavailable` 时显示明确「视频暂不可用」状态，不假造画面
- [x] 2.4 验证 `sync_recording?view=video` 与 `upload?view=video` 均可播放

## 3. P0C · 报告去 Drawer + 四层职责链

- [x] 3.1 新增 `PbReportContent`（复用现有 Pb* 组件 + `PbReportProvider`，NO Drawer / NO navigation）
- [x] 3.2 从 `ReportPage` 拆出 `ReportContent`（useJobReport 驱动 loading/failed/canceled/no report `数据状态`）；`ReportPage` 保留 legacy 切换与独立路由（`/reports/:type`、`/analysis/:jobId/reports/:type`）
- [x] 3.3 Workspace `report` view 改为渲染 `ReportContent` + `PbReportContent`，不再调会挂 Drawer 的 `PbVisionReportLayout`
- [x] 3.4 验证 Workspace 报告 view 无 Drawer、无报告独立导航

## 4. P1A · 抽取核心 Content

- [x] 4.1 Vision：从 `VisionPage` 拆出 `VisionContent`（含 `useVisualAnalysisReport` + 渲染），旧路由改 `PageFrame + VisionContent`
- [x] 4.2 RecordingWorkspace：从 `RecordingWorkspacePage` 拆出 `RecordingWorkspaceContent`
- [x] 4.3 Report：从 `ReportPage` 拆出 `ReportContent`（与 3.2 同步，确保单处实现）

## 5. P1B · 抽取其余 Content

- [x] 5.1 BallTrajectory：从 `BallTrajectoryPage` 拆出 `BallTrajectoryContent`
- [x] 5.2 SegmentManager：从 `SegmentManagerPage` 拆出 `SegmentManagerContent`
- [x] 5.3 Technical：分别从 `MultiviewObservabilityPage` / `AnalysisDetailsPage` 拆出 `*Content`
- [x] 5.4 Workspace 各结果 view 改消费 `*Content`，删除对完整 page 的内嵌引用；旧路由 `PageFrame + Content` 不回归

## 6. P1C · LibraryViewCapabilities 门控

- [x] 6.1 定义 `CapabilityState` 与 `LibraryViewCapabilities`（video/analysis/trajectory/report/segments/technical + reasons）
- [x] 6.2 依据「primary Job 状态 + AnalysisResult manifest artifact URL（`cleaned_ball_trajectory_url` / `ball_trajectory_url` / report 证据）」一次判定，禁止初始门控逐 view 拉重产物
- [x] 6.3 区分 invalid view（replace 到 overview）与 合法但缺产物（停在原 URL 显示「本次分析未生成该数据」）
- [x] 6.4 补齐场景测试：有 job 但无 trajectory artifact 停在 `?view=trajectory`；`upload?view=segments` replace 到 overview

## 7. P2A · 投影层 displayState / 语义标题 / bulk join / sync primary

- [x] 7.1 `libraryAdapter` 的 `LibraryItemViewModel` 新增 `displayState` 派生与语义 `title` 解析（metadata.matchTitle → FieldSession 标题 → 时间+比赛形式 → raw id）
- [x] 7.2 `buildLibraryItems` 一次性 `listFieldSessions()` 建 `Map<id, FieldSession>` 再统一 join（禁 N+1）；`resolveLibraryItemByRef` 单次 `getFieldSession`
- [x] 7.3 `court_name` 降级为 `courtName` 次要 metadata
- [x] 7.4 修正 `pickPrimarySyncJob`：删除「回退到 single-view」的错误注释，明确无 multiview Parent → `undefined`，A/B single view NEVER primary；补测试（只有 cam_1/cam_2 single-view → primary undefined）

## 8. P2B · LibraryCard DOM / 标签 / 菜单清理

- [x] 8.1 标题用语义 title；概览/场次分组不再展示 `sync_`/`fs_` raw id（改语义化）
- [x] 8.2 source/camera/matchFormat 标签去重
- [x] 8.3 修复无效 DOM：卡片根改 `<article className="relative">`，图片/内容为点击实体，菜单定位修正，消除 nested button
- [x] 8.4 菜单 action 门控：未实现项（重命名/下载/分享/upload 删除）移除或禁用；「重新分析/查看原视频」对 recording/sync 无 context 时隐藏

## 9. P2C · 封面 conditional plumbing + displayState 筛选

- [x] 9.1 `LibraryCard` 封面读 `thumbnailUrl/previewUrl`：有稳定 URL 渲染真实图，无则中性占位，不伪造截图；真实 poster / hover preview 留待 `add-library-media-previews`
- [x] 9.2 `LibraryPage` 状态 tab 筛选改基于 `displayState`（待处理/正在分析/分析完成/失败/待合并），不再直接读 `mediaState`
- [x] 9.3 补齐筛选场景测试（media ready + analysis running 落入「正在分析」而非「已完成」）

## 10. 回归与验证

- [x] 10.1 更新并新增单测：`libraryAdapter`（displayState/标题/bulk join/sync primary）、`library-item-workspace`（条件渲染/视频分派/capability 门控/invalid vs 缺产物）、`report-detail-pages`（四层职责/去 Drawer）
- [x] 10.2 跑 `npm run lint` + `npm run typecheck`，修复全部报错
- [x] 10.3 跑 `npm run test`，确认相关测试通过、无回归
- [x] 10.4 手动回归：legacy 报告/旧结果页路由视觉与行为一致；workspace 各 view 无跨 view 空态、无双外壳、无报告 Drawer、双摄可播
- [x] 10.5 在 P0 三项（1–3）完成后重新截图对比，确认无跨 Tab 空态、无报告 Drawer、无 Vision 第二层标题、双摄可播放，再继续 P1/P2
- [x] 10.6 最终验收对齐 proposal 的 P0A–P2C 阶段与 specs 场景