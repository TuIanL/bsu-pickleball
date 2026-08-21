## Context

Library-first 工作区（`/library/:kind/:sourceId`）已具备底层最难的架构：`backend objects → libraryAdapter → LibraryItem → 统一 workspace route`。但 Workspace 当前把整页直接内嵌（`VisionPage / ReportPage / BallTrajectoryPage / RecordingWorkspacePage / SegmentManagerPage / MultiviewObservabilityPage / AnalysisDetailsPage`），并存在：

- 6 个 view 区块无守卫的三目渲染 bug（非当前 view 渲染各自空态）
- `video` view 限定 `kind === "recording"`，双摄素材无法打开
- `report` view 调用 `ReportPage`，后者默认挂 `PbVisionReportLayout`（含 `PbPlayerDrawer`/`PbDrawerExpander`），Drawer 在 workspace 内必现
- 结果类 view 门控只看 `primaryAnalysisJobId`，不看真实产出物
- Library 卡片仍为「数据库投影页」：标题= court_name、`fs_`/`sync_` ID 泄漏、标签同义重复、纯绿占位图、nested button + 无 relative 的 absolute 菜单、筛选看底层 mediaState

本 change 不做视觉精修，专注 composition 与数据语义。

## Goals / Non-Goals

**Goals:**
- 修复全部条件渲染 bug，让「非当前 view」什么都不渲染
- 双摄素材 `video` view 可正常回放，且 upload 板的 `video` view 可播放源视频
- Workspace 各结果 view 只消费抽取出的 `*Content` 组件，消灭「页面套页面」
- 报告 view 去 Drawer，作为 workspace 内容承载
- 结果类 view 按真实产出物（AnalysisResult manifest）门控
- Library 语义化：标题解析、工程 ID 去暴露、标签去重、封面有则消费否则中性占位、`displayState` 筛选、菜单 action 门控

**Non-Goals:**
- 不调整视觉风格/配色/阴影/圆角（后续单独做视觉精修）
- 不改变 `libraryAdapter` 的三轴状态模型（只增加派生 `displayState` 与语义标题）
- 不实现上传源视频的级联删除等真实业务（未接通前隐藏菜单项）
- 不迁移后端或改变 API 形状

## Decisions

**D1. `*Content` 从页面内部抽取（数据加载 + 渲染一起抽）。**
`VisionPage` 的 `useVisualAnalysisReport`、`RecordingWorkspacePage` 的 `PageState` 都把数据加载封装在页面内。只抽渲染切片会导致 workspace 与旧路由双份数据加载逻辑。因此每个页面拆为：`useXxxData`（或保留原页面内 hook 改用）+ `XxxContent(props)` 渲染组件；旧路由 `PageFrame + XxxContent`，workspace `XxxContent`。
> 替代：仅抽渲染 + workspace 单独重新取数 → 双份数据逻辑、易漂移，已否决。

**D2. Workspace 内容区统一 `effectiveView === xxx && (gate ? Content : EmptyState)`。**
所有 view 块统一为两段式（view 守卫在外、内容/空态在内），从结构上消灭「非当前 view 渲染 else 空态」的 bug。gate 由「素材是否有该 view 产出物」决定，而非仅 jobId。

**D3. 报告职责四层化：`ReportContent` / `PbReportContent` / `PbVisionReportLayout` 明确分层。**
为避免 `ReportContent` / `PbReportContent` 撞名后职责又漂移，锁成四层：

```
useJobReport(jobId)
   ↓
ReportContent（数据与业务状态）
   负责：loading / failed / canceled / no report / report data state
   ↓
PbReportContent（PB 视觉内容）
   负责：PbReportProvider + Player Header / Skill Rating / Court /
        Coverage / Serve&Return / Coach Insight ...
   NO Drawer，NO navigation
   ├─ Workspace 报告 view 直接挂它
   └─ 也作为 standalone 报告内容载体
   ↓（仅 standalone 时）
PbVisionReportLayout（standalone chrome）
   负责：PbPlayerDrawer / Drawer expander / standalone spacing
```

Workspace 报告 view 用 `PbReportContent`；独立报告路由（`/reports/:type`、`/analysis/:jobId/reports/:type`）仍由 `ReportPage` → `PbVisionReportLayout` 承载（含 legacy 切换）。
> 替代：给 `PbVisionReportLayout` 加 prop 控制是否挂 Drawer → 会把 standalone chrome 和内容混在一个组件里，职责不清，已否决。

**D4. `video` view 三类来源统一分派。**
```
video view
├─ upload          → SourceVideoContent(videoId)
│                    └─ GET /api/videos/{videoId}/stream
├─ recording       → RecordingWorkspaceContent(sessionId)
├─ sync_recording  → RecordingWorkspaceContent(sessionId)  // dual playback
└─ availabilityState=unavailable → 明确「视频暂不可用」状态
```
upload 的 stable identity 即 `{ kind: 'upload', sourceId: videoId }`，其 `videoId` 本就可经 `getVideoStreamUrl` 播放，因此 upload 的 video view SHALL NOT 判空态。

**D4a. `view` 语义：非法 view 与 合法但缺产物 分开。**
- 非法 view（该素材 source 根本不支持，如 `upload?view=segments`）→ `replace` 落到 overview。
- 合法但当前缺产物（如 completed job 无 trajectory artifact）→ 仍停在原 URL，显示「本次分析未生成球路数据」。
区分两者，避免「URL 说 trajectory、UI 却落到 overview」的二次不一致。

**D5. 投影层新增 `displayState` 与语义 `title`。**
三轴状态不变，新增派生 `displayState`（合并媒体+分析语义，供筛选/徽章消费），并实现标题解析优先级（metadata.matchTitle → FieldSession 标题 → 时间+形式 → raw id）。`court_name` 仅作 `courtName`。标题 join：`buildLibraryItems` 一次性 `listFieldSessions()` 建 `Map<id, FieldSession>` 再统一 join（禁止每卡 `getFieldSession` 造成 N+1）；`resolveLibraryItemByRef` 只查单素材，可单次 `getFieldSession(fieldSessionId)`。

**D5a. sync primary 无 multiview 时即为 `undefined`。**
`pickPrimarySyncJob` 的现有注释（"回退到历史 single-view"）与实际返回值矛盾——fallback 其实永远拿空 `candidates`。按既有 D9 契约，正式规则就是：sync 的 primary = 最新 public multiview Parent；无 multiview Parent → `undefined`；A/B single view NEVER primary。仅删错误注释，不改成真 fallback，并补测试（只有 cam_1/cam_2 single-view jobs → primary 为 undefined）。

**D5b. View capability 门控基于 AnalysisResult manifest（一次判定，不拉重产物）。**
引入：
```ts
type CapabilityState = "available" | "unavailable" | "loading";
interface LibraryViewCapabilities {
  video: CapabilityState;
  analysis: CapabilityState;
  trajectory: CapabilityState;
  report: CapabilityState;
  segments: CapabilityState;
  technical: CapabilityState;
  reasons?: Partial<Record<LibraryView, string>>;
}
```
authority：
```
video       → source media availability
analysis    → completed primary job + AnalysisResult 存在
trajectory  → cleaned_ball_trajectory_url || ball_trajectory_url
report      → reportId / report-stage 证据（真正打开 Tab 后再 GET report）
segments    → captureTakeId
technical   → primary job；sync 时为 multiview technical capability
```
初始 gate 复用 `VisionPage` 已有的 `getAnalysisJob + getAnalysisReport + getAnalysisResult` 返回的 `AnalysisPipelineResult.artifacts.*_url`，一次完成，不逐 view 拉重产物。

**D6. Library 卡片：真实封面（conditional）+ 标签去重 + 修复无效 DOM + 菜单门控。**
- 封面读 `thumbnailUrl/previewUrl`：有稳定 URL 渲染真实图，无则中性占位，不在前端伪造截图；真实 poster（上传/录制/双摄 reference）与 hover preview 另开 `add-library-media-previews` Change
- source/camera/matchFormat 标签去重为唯一集合
- 卡片根改 `<article className="relative">`，图片/内容为可点击 button/link，菜单用 `relative` 定位或移出卡片根，消除 nested button
- 未实现菜单（重命名/下载/分享/upload 删除）在接通前移除或禁用；「重新分析/查看原视频」对 recording/sync 无 context 时隐藏

**D7. 状态筛选消费 `displayState`。**
`LibraryPage` 的 tab 筛选改基于 `displayState`（待处理/正在分析/分析完成/失败/待合并），不再直接读 `mediaState`。

## Risks / Trade-offs

- [内容抽取误改 legacy 渲染 → 旧路由回归] → 保留 legacy 路由（`PageFrame + Content`）与既有测试；抽取时先跑 `npm run test` 相关用例。
- [`displayState` 语义与底层多轴状态边界纠缠] → displayState 为只读派生值，三轴状态仍是唯一真源，避免新增可写状态轴。
- [封面字段缺失导致视觉仍显 prototype] → 本 Change 只做「有则消费、无则中性占位」，不伪造截图；真实 poster 另开 `add-library-media-previews`，不作为本 Change 硬验收。
- [菜单 action 简化为隐藏可能减少可用操作] → 仅隐藏未实现/无 context 的操作；已实现的 upload 重分析、技术详情、合并保留。
- [capability gate 误触发请求风暴] → 初始 gate 一律走 Job + AnalysisResult manifest 一次判定（D5b），禁止逐 view 拉重产物；重产物仅在真正打开对应 Tab 时按需加载。
- [invalid view 与缺产物 view 区分不清 → URL/UI 二次不一致] → 按 D4a 拆开：非法 view replace 到 overview；合法缺产物 view 停在原 URL 显示缺产物提示。

## Migration Plan

1. **P0A** 修 Workspace ternary 渲染 bug。
2. **P0B** 统一 `video` 视频分派（upload → SourceVideoContent；recording/sync → RecordingWorkspaceContent；unavailable 明确）。→ 重新截图，确认无跨 Tab 空态、双摄可播。
3. **P0C** 抽 `PbReportContent` 并接入 Workspace 报告 view，彻底去 Drawer；`ReportPage` 走四层职责链。→ 重新截图，确认无报告 Drawer。
4. **P1A** 抽 `VisionContent` / `RecordingWorkspaceContent` / `ReportContent`；**P1B** 抽 Trajectory/Segment/SegmentManager/Technical Content；workspace 改消费 `*Content`，旧路由 `PageFrame + Content`。
5. **P1C** 落地 `LibraryViewCapabilities`（Job + AnalysisResult manifest 判定 + invalid/缺产物区分）。
6. **P2A** 投影层 `displayState`/语义 title + FieldSession bulk join + sync primary 注释修正与测试。
7. **P2B** `LibraryCard` DOM / 标签去重 / 菜单门控。
8. **P2C** 封面 conditional plumbing（有则消费、无则占位，真实 poster 另开 Change）。
9. 回归：`npm run test`（libraryAdapter / library-item-workspace / report-detail-pages / video-analysis-workspace）+ `npm run lint && npm run typecheck`；手动验证 legacy 路由无回归、workspace 各 view 无跨 view 空态/无双外壳。

## Open Questions

- `thumbnailUrl/previewUrl` 当前后端是否有稳定可解析 URL 映射？——本 Change 采取 conditional 策略，缺字段不阻塞；真实 poster 统一交给 `add-library-media-previews`。
- 「重新分析」「查看原视频」对 recording/sync 的带 context 入口（`/analysis/new?recording=...`）是否需要本轮一并接通，还是先隐藏。