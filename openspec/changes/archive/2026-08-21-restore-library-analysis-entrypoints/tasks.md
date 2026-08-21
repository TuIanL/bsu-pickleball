## 1. LibraryItem 分派元数据与路由纯函数

- [x] 1.1 在 `libraryAdapter.ts` 为 `LibraryItemViewModel` 补齐分派所需字段：`recording` 用途的源视频 `videoId`（取自 `RecordingSession.video_id`）、双摄 A/B 机位视频可用标记。
- [x] 1.2 新增纯路由函数 `libraryAnalysisPathFor(item)`（可新建 `libraryAnalysisRouting.ts`），按类型返回「开始/再次分析」目标 URL：双摄→`/capture/takes/:captureTakeId/analyze?session=:sessionId`；单摄 recording→`/analysis/new?videoId=...&source=recording&sessionId=...`；双摄 A/B 单摄→`/capture/:sessionId/analyze?cam=...`；upload→`/upload?videoId=:sourceId`；目标不可用时返回 `null`。
- [x] 1.3 为 `libraryAnalysisPathFor` 补充单元测试：三类素材的分派结果与不可用返回 `null`。

## 2. 未分析素材「开始分析」接线

- [x] 2.1 修改 `LibraryItemWorkspace.OverviewView`：`!hasAnalysis` 时「进入分析」按钮改为调用 `libraryAnalysisPathFor(item)` 跳转真实创建页；目标不可用时隐藏/禁用并给出待分析提示，不再跳 `?view=analysis` 空态。
- [x] 2.2 修改 `LibraryPage.handleReanalyze`：录制/双摄分支改为 `libraryAnalysisPathFor(item)`，删除对 `/analysis/new` 的错误跳转；upload 分支复用同函数。
- [x] 2.3 修改 `LibraryCard`：放开「分析/重新分析」菜单项对 `recording` / `sync_recording` 的可见性，依据 `libraryAnalysisPathFor(item)` 非 null 决定可用；保留 upload 行为。
- [x] 2.4 验证：未分析的三类素材从比赛库卡片与工作区均可进入对应创建页，且不落入 `?view=analysis` 空态。

## 3. 已分析素材「再次分析」接线

- [x] 3.1 `OverviewView` 在 `hasAnalysis` 时增加「再次分析」入口（复用 `libraryAnalysisPathFor`），多类型素材（双摄）提供「双摄协同 / A 机位 / B 机位」选择。
- [x] 3.2 `LibraryCard` 菜单在已分析素材上增加「再次分析」项。
- [x] 3.3 将再次分析入口的可用性接入既有三轴状态：`mediaState=ready` 且无 `pending_merge` 时可见，否则隐藏/禁用。
- [x] 3.4 验证：对已分析素材再建一次分析后 `analysisHistoryCount` 增加，历史任务保留且不受影响。
- [x] 3.5 修正可见性死角：`availabilityState=unavailable` 只阻断「未分析」素材的首次分析；已分析素材的再次分析不再被源视频流暂不可用隐藏（基于已注册/已落盘机位重跑）。补齐回归测试。

## 4. 返回路径与来源上下文

- [x] 4.1 使「开始/再次分析」创建页的取消/退出返回来源：双摄创建页按 `?session=` 上下文回到工作区或比赛库（而非任务列表）。
- [x] 4.2 为单摄 recording 复用上传分析流程时，在 URL 携带回跳来源，创建完成后返回工作区/比赛库。
- [x] 4.3 验证：从卡片/工作区发起分析，创建页取消与完成后均回到正确来源。

## 5. 测试与验收

- [x] 5.1 组件测试：`LibraryItemWorkspace` 未分析跳创建页、已分析显示「再次分析」。
- [x] 5.2 路由/组件测试：`LibraryPage`、`LibraryCard` 三类素材的入口可见性与目标 URL。
- [x] 5.3 运行 `tsc`（前端类型检查）与相关单测全绿。
- [x] 5.4 手工验收：双摄/单摄/上传素材「未分析」与「已分析」两种状态下，开始与再次分析路径均可达且返回正确。

## 6. 概览历史任务管理（删除/取消单个分析任务，保留视频）

- [x] 6.1 `libraryAdapter` 的 `LibraryItemViewModel` 新增 `analysisJobs`（公开历史任务，新→旧，排除双摄 internal Source Job），在 `buildLibraryItems` 与 `resolveLibraryItemByRef` 各分支填充。
- [x] 6.2 `LibraryItemWorkspace.OverviewView` 新增「历史分析任务」列表：已完成/失败/已取消→删除（`deleteAnalysisJob`），排队中/分析中→取消（`cancelAnalysisJob`）；操作后经 `reloadToken` 重刷素材状态，原视频保留。
- [x] 6.3 补充测试：概览列出历史任务并可删除；`tsc` 类型检查通过。