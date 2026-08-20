## Context

当前前端用户层对象仍以 AnalysisJob 为中心：`AnalysisTasksPage` 同时管理 AnalysisJob / RecordingSession / SyncRecordingSession / FieldSession，用「上传视频任务 / 录制视频任务 / 双摄录制」三个 Tab 解释后台对象关系。用户被迫理解 FieldSession→CaptureTake→RecordingSession→AnalysisJob→分析结果的完整链，而结果又被切成 vision/details/trajectory/report/multiview 等兄弟页面。

后端模型职责清晰且已有多年演进：`field-sessions`（采集顶层容器）、`recording-session-control`（单摄录制）、`dual-camera-sync-recording`（双摄）、`analysis-task-management`（工程任务控制台）。本重构**不改动这些 backend domain**，只在前端加一层用户对象投影。

经代码核查确认的关键事实：
- `AnalysisJobSummary` 顶层已有 `recordingSessionId` / `cameraSlot`，metadata 有 `recording_session_id` / `capture_take_id` / `camera_slot`
- 新建 multiview Parent 时 `MultiViewAnalysisSetupPage` 已写入 `recording_session_id: take.source_session_id || session.session_id, capture_take_id: take.id`
- 现有 `isAnalysisJobForSyncRecording()` 先比对 `recordingSessionId`，失败才 fallback 到 `capture_take_id`，且不使用 file/video/title 等模糊匹配

## Goals / Non-Goals

**Goals:**
- 用户层改造成 Library-centric：统一 LibraryItem 投影，用户看到「一场比赛/一个视频」
- 保留 Job-centric 工程能力，下沉为 Engineering Task Console
- 建立 sync ownership 契约使方案能在**不新增后端字段**下成立
- 收敛结果页到 `library-item-workspace` 的 view
- 定义干净的 routing / history 语义

**Non-Goals:**
- 不实现 Dashboard（`/workspace` alias 到 `/library`）
- 不新建后端 `Match` / `MediaAsset` 实体
- 不新增 `syncRecordingSessionId` 字段（P0）
- 不更换路由框架（继续自研 RouteState + 纯函数 parser）
- 不重写 FieldSession domain 语义
- 不重写七个结果页组件，而是逐步改造成 workspace content component 后复用

## Decisions

### D1：`/workspace` 保留兼容但不出现在一级导航，alias 到 `/library`
本 Change 不做 Dashboard。一级导航直接「比赛库 / 现场采集 / 设备与设置」。`/workspace` 解析后重定向到 `/library`，避免发布「建设中」占位页。
- 备选：保留占位 + 继续展示工作台入口 —— 拒绝，避免发布空壳主导航
- 后续需真正 Dashboard（今日任务/最近比赛/分析状态/设备/快捷入口）时，另开 `build-operations-dashboard`，届时恢复「工作台」一级入口

### D2：`AnalysisJob.recordingSessionId` 升格为 canonical sync ownership reference；`capture_take_id` 仅作 legacy fallback；P0 不新增字段
结论：当前 main 已接近 first-class reference，无需扩 Schema。

```
新任务：
SyncRecordingSession.session_id
        ↓
AnalysisJob.recordingSessionId
        ↓
LibraryItem(kind=sync_recording).sourceId
```
`metadata.capture_take_id` 只作为 legacy compatibility fallback。

验收契约（P0 硬测试）：
- **WHEN** 从 SyncRecordingSession 创建 public multiview Parent
- **THEN** `Parent.recordingSessionId MUST == SyncRecordingSession.session_id`
- **AND** Library projection 优先使用 `recordingSessionId`
- **AND** 仅当历史任务缺失 `recordingSessionId` 时 MAY 使用 `capture_take_id` fallback
- **AND** 不得使用 fileName / video title / timestamp 等模糊匹配

若 P0 测试发现某创建路径未正确写入 `recording_session_id`，修复**创建链路 wiring**（`MultiViewAnalysisSetupPage` 及 job creation payload），而不是立即新增字段。
若后续 `recordingSessionId` 同时承载普通 RecordingSession 与 SyncRecordingSession 产生语义冲突，再升级为：
```ts
sourceRef: { kind: "recording" | "sync_recording"; id: string }
```
而不是堆平行 ID 字段。

### D3：Workspace 内 view 切换使用 `replaceState`；层级跳转使用 `pushState`
浏览器 Back 一次从 `/library/sync/sr-123?view=analysis` 直接回到 `/library`，而非逐 view 回退。

三类历史语义：
```text
Library → Item Workspace        pushState
Workspace 内一级 Tab 切换         replaceState   (?view=overview/video/analysis/trajectory/report/segments/technical)
Workspace → 外部对象               pushState     (工程任务详情 / 独立编辑向导)
报告证据跳回视频 ?view=video&t=26300   replaceState (仍在同一素材对象)
```
复用现有 `NavigateOptions.replace`，不改路由基础设施。

### D4：用户侧继续使用「比赛库」，语义用副标题与筛选保护
- 一级导航「比赛库」，副标题「统一管理比赛、训练与采集视频及其分析结果」
- 卡片明确标注「比赛 / 训练」
- `capture_mode = engineering` 素材**默认不混入普通主列表**，进入「筛选 → 显示工程素材」或未来开发者模式
- 主列表平时只展示 `match` / `practice`，缓解「比赛库」名称对 practice 集的语义压力

### D5：LibraryItem identity 与 AnalysisJob identity 完全分离（含 Upload 独立资产生命周期）
**LibraryItemRef 永久稳定，`primaryAnalysisJobId` 可变。**

```ts
SyncRecordingSession sr-123
    ├── Parent Job #1
    ├── Parent Job #2
    ├── A 单摄 Job #1
    └── B 单摄 Job #1

Library 永远只有：sync_recording:sr-123  一张卡
```
URL `/library/sync/sr-123?view=analysis` 不因重新分析失效。这正是 Library-centric 与 Job-centric 的本质区别。

对 `recording` / `sync_recording`，来源有真正独立的持久实体（`RecordingSession.session_id` 生成 `rec_...`、`SyncRecordingSession.session_id` 生成 `sync_...`，不同命名空间），identity 天然与 Job 分离。

**`upload` 目前在剔除 Job 后并不具备独立资产生命周期**——这是本 Change 必须在 tasks 前的关键拍板。现状上传链为：`选择文件 → POST /api/videos/upload → videoId → 四角标定 → createAnalysisJob(videoId)`。`videoId` 可作 `{ kind: "upload", sourceId: videoId }`，但存在两个缺口：

1. **无 video catalog**：当前 `/api/videos` 只有 `POST /upload`、`GET /{video_id}`、`GET /{video_id}/stream`，没有 `GET /api/videos` 枚举接口。若完全不加 API，Library 的 upload 只能从 `listAnalysisJobs()` 按 videoId 去重反推，会退回「Library 从 Job 构造」，与 D5 冲突。
2. **Job 删除可摧毁 upload source**：既有删除契约规定，删除最后一个引用某 upload video 的 Job 且无其余引用时，后台可连带删除 source video → Job lifecycle 仍能摧毁 Library identity。

**决策：允许一个极小的只读 backend API 调整，但坚持不做 domain rewrite。**
```text
GET /api/videos         # 新增只读 catalog，枚举现有 VideoMetadata，无新表、无新实体
GET /api/videos/{id}    # 保持原样
POST /api/videos/upload # 保持原样
```

**并重新拍板删除语义（资产所有权契约）：**
```text
删除 AnalysisJob   → 只删 job + job artifacts，不删 source video
删除 Library source video → 显式、独立、经 LibraryItem 触发，再决定如何处理关联 jobs
```
此乃真正的 Library-centric：Uploaded Video 拥有独立 catalog 与 ownership lifecycle，Job lifecycle 不得摧毁 Library identity。

> 若后续发现 `GET /api/videos` 对 staging / 存储可达性需更多字段，再按 availability 轴（见 D6）扩展该只读 catalog；本 Change 不建立 MatchAsset 实体。

### D6：Library Item 采用三轴状态模型（生命周期 × 可访问性 × 分析），而非单一 status
当前 `SyncRecordingSession` 后端已区分「录制/合并生命周期」与「视频当前是否可访问」：`video_availability` 枚举 `available / unavailable / pending`，注释明确「外置存储临时不可访问时保留 video ID、只更新 availability，不代表视频资产失败」——这对移动硬盘存储场景尤其重要。

**决策：三轴正交，不合并。**
```ts
interface LibraryItemViewModel {
  mediaState:        "recording" | "processing" | "ready" | "failed" | "canceled"
  availabilityState: "available" | "pending" | "unavailable"
  analysisState:     "not_started" | "queued" | "running" | "succeeded" | "failed" | "canceled"
}
```
UI 派生（卡片主状态仍只显示一个，但有明确 sub-note）：
```text
mediaState=recording        → 正在录制
mediaState=processing       → 视频处理中

mediaState=ready
  analysisState=not_started → 待分析
  analysisState=running     → 正在分析 62%
  analysisState=succeeded   → 分析完成
  analysisState=failed      → 分析失败

availabilityState=unavailable (且 media=ready, analysis=succeeded)
                            → 分析完成 · 视频存储暂不可用  ← 不得解释为 mediaState=failed
```

**source-specific 状态映射必须显式写死，不能简单映射。**
`sync merge_status = pending` 可能意味着「等用户点击『合并视频』」，而非「正在处理」。为避免 UI 显示「正在处理中」实则在等用户：
```ts
merge pending → mediaState=processing + primaryAction=merge_required
merge running → mediaState=processing + primaryAction=none
```
LibraryItemViewModel 预留用户动作槽：
```ts
requiredAction?: "merge" | "retry_merge" | "start_analysis"
```
各来源的源状态→ViewModel 映射表 SHALL 在 `library-item-projection` spec 中显式定义。

### D7：统一身份用 typed reference，Route 用 query view
Phase 1 路由（自研 RouteState 纯函数解析，可刷新/复制/前进后退/深链/测试）：
```text
/library
/library/upload/:sourceId?view=overview
/library/recording/:sourceId?view=analysis
/library/sync/:sourceId?view=report
```
```ts
type LibraryItemRef =
  | { kind: "upload"; sourceId: string }
  | { kind: "recording"; sourceId: string }
  | { kind: "sync_recording"; sourceId: string }
```
一个 `RouteState (name: "library-item", kind, sourceId, view)` 取代大量 sibling states。后续若 Adapter 复杂化，再另开 Change 引入 canonical MediaAsset 并收敛为 `/matches/:matchId`。

### D8：`pb-vision-style-report-page` 组件保留，报告外壳与 mock 剔除
- **Keep**：Skill Card / Player Header / Court Coverage / Serves & Returns / Coach Insight / Filter（视觉组件）
- **Drop**：报告独立抽屉栏、报告专属导航体系、real-job mock 数据（mock 必须服从 `performance-insights` 证据约束，不得为填 UI 自动造数）

### D9：Primary Analysis Selection 契约
`latestPublicAnalysisJobId` 会造成双摄选错（A 单摄重跑把 primary 顶成 A 机位）。字段语义应是 **primary** 而非 latest。ViewModel 用：
```ts
primaryAnalysisJobId?: string
analysisHistoryCount: number
```
选择规则 SHALL 显式写死：
```text
LibraryItem(sync_recording)
  primary = 该 sync 会话下最新 public analysisKind=multiview Parent
  A/B public single-view 不得成为 primary

LibraryItem(recording)
  primary = 最新 public single-view，且 recordingSessionId == sourceId

LibraryItem(upload)
  primary = 最新 public single-view，且 videoId == sourceId
  且不得归属于 recording / sync_recording

internal child 永远不参与；A/B 工程单摄不成为 primary
```

### D10：`/workspace` canonical redirect + replaceState
`/workspace` 采用 canonical redirect（最终地址栏成为 `/library`），并用 replace 语义，不残留 `/workspace` 历史项。

### D11：一级「设备与设置」
本 Change 不新建独立 `/settings` shell，且不得出现标签/页面语义不一致。P0/P1 仍以「设备管理」→ `/camera` 呈现该项，避免再造一个无契约页面；待设置页真正成型（settings/开发者/工程入口需要承载时）再改名为「设备与设置」。

### D12：Engineering Console canonical URL
P0 canonical 仍为 `/analysis/tasks`（hidden route），`/tasks` 作 alias；本 Change 不新增 `/engineering/tasks`，避免多 URL。

### D13：LegacyRouteResolver 异步迁移
`/analysis/job-123/vision` 等旧 route 不含 `sourceType/sourceId`，纯函数 parser 无法确定 LibraryItemRef。迁移期 **保留旧 sibling RouteState**，P3 由 `LegacyLibraryRouteResolver` 异步加载 job → `resolveLibraryItemRef(job)` → replace 到 `/library/...` 后，才删除旧 sibling states。不得 P0/P1 直接删 RouteState。

### D14：view capability gate + stable fallback
深链 `?view=report`（或 trajectory/multiview）而素材无成功 primary 分析时，不得空白页：SHALL 依据 availability/analysisState 门控 view，并落到 stable fallback（如 `overview` + 待分析提示），而不是空渲染。

### D15：上传/采集默认落点
Library-first 后，上传 + 创建分析成功 SHALL 进入 `/library/upload/{videoId}?view=analysis`（直接看到「正在分析 12%」），采集完成并 durable 后进入对应 LibraryItem；不再回 `AnalysisTasksPage` 任务列表。

## Risks / Trade-offs

- **[D2 P0 契约可能失败：历史/新增路径未写 `recordingSessionId`]** → 先跑 ownership 契约测试（upload / recording / sync_recording 三条映射），再动 UI；若缺则修 wiring 而非扩字段
- **[sync_recording 历史数据归不了类，仅能靠 `capture_take_id` fallback]** → 接受 legacy fallback；Library 卡若无法归属则降级处理，不阻塞主链路
- **[多 Job 归属单卡：重跑分析后 primary 变化]** → identity 分离原则保证 ref 稳定；历史分析进「技术详情 → 分析历史」；primary 由 D9 契约控制，杜绝选错
- **[upload 无独立 catalog / Job 删除可摧毁 source]** → 新增只读 `GET /api/videos`；重定义删除语义（删 Job ≠ 删源视频）为资产所有权契约，见 D5
- **[外置存储掉线被误判为视频失败]** → 引入 availability 轴（D6），media=ready + availability=unavailable 显示「存储暂不可用」，不当 failed
- **[merge pending 被 UI 误读为处理中]** → source-specific 映射表 + requiredAction（merge_required），见 D6
- **[replaceState 语义可能影响「从外部直接深链 view」场景]** → query 仍可深链特定 view，历史语义只在站内 tab 切换生效
- **[七个结果页收敛为 workspace content 是大工程]** → 分阶段：先建外壳 + 逐个吸收入口组件，旧 page shell 保留至全部迁移完成再删
- **[`analysis-task-management` 大规模降级可能内伤工程能力]** → 不删除、只包装为 Engineering Console，保留 Parent/child 与全部管理动作
- **[LegacyLibraryRouteResolver 异步解析可能造成跳转闪烁]** → 保留旧 sibling RouteState 直渲，resolver 完成后 replace；迁移期不清路由

## Migration Plan

采用五阶段增量迁移，后端改动极小：

| 阶段 | 内容 | 动后端 |
| --- | --- | --- |
| **P0 契约冻结** | LibraryItem projection（三轴+primary 契约）、ownership 契约测试、`GET /api/videos` catalog、legacy route 测试 | 只读 video catalog |
| **P1 Library** | 新 `/library` 统一显示录制/双摄/上传；旧 sibling RouteState 保留 | 否 |
| **P2 Workspace** | `library-item-workspace` 逐个吸收 Vision / Report / Trajectory / Segments / Multiview | 否 |
| **P3 导航收敛** | 新 Sidebar；任务页原地降级 Engineering Console；`LegacyLibraryRouteResolver` 收旧 route | 否 |
| P4 可选 | 若 Adapter 长期复杂，设计 canonical MediaAsset backend entity | 是（另开 Change） |

**实施一刀（重要）**：不改造 `AnalysisTasksPage` 成 Library。新建 `LibraryPage.tsx` / `src/services/libraryAdapter.ts` / `src/components/library/*`；`AnalysisTasksPage` 保留现有 Job-centric 能力并原地降级为 Engineering Console，后续 cleanup 阶段按需拆组件，不作为 Library 主实现基础。

回滚：旧 route（`/analysis/tasks`、`/tasks`、`/reports/:type`、`?legacy=1`）全程保留兼容，新 UI 失败可切回旧入口，无需后端回滚。

## Open Questions

- 是否在此 Change 内把 `build-operations-dashboard` 的裸空位（一级导航暂不出现工作台）作为一次性说明写进 release/演示材料？——默认是，避免评审时困惑「工作台去哪了」
- Library 卡片详情字段（venue、courtName）目前数据源是否稳定可用？——P1 实现时确认，缺失暂隐藏
- `GET /api/videos` catalog 是否需要为 upload LibraryItem 一并返回 availability/ownership 相关字段，还是仅返回 VideoMetadata 基础字段由前端投影？——倾向仅基础字段，availability 按 D6 由前端聚合现有接口