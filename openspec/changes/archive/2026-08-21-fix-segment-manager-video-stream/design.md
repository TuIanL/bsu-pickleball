# fix-segment-manager-video-stream — Design

## Context

片段管理页（`SegmentManagerPage`，比赛库「片段」Tab 与 `/capture/{fs}/takes/{takeId}/segments` 独立路由共用）当前用

```
/api/videos/${take?.source_session_id}/stream
```

作为播放源。但 `source_session_id` 是采集会话 ID（如 `rec_20260717_105958_e15240`），而 `/api/videos/{video_id}/stream` 期望的是视频目录里的 `video_id`（如 `rec-9e2d944d4d`）。实测前者 404、后者 200 —— 这是「片段加载正常但完全无法播放」的根因。

同时存在两个次要问题：

1. `GET /api/capture-takes/{id}/segments`（[routes_coding_actions.py](file:///Users/tuian/Documents/大学/竞赛/大创/匹克球/前期展示web/pre-pickleball/backend/app/api/routes_coding_actions.py#L356-L378)）手工拼 dict，缺少 `edit_status` / `edit_version` / `corrected_*` / `effective_*`，与前端 [CaptureSegmentSummary](file:///Users/tuian/Documents/大学/竞赛/大创/匹克球/前期展示web/pre-pickleball/src/types/report.ts#L660-L678) 契约不一致，导致 superseded 过滤、乐观锁、边界修正降级。
2. `loadData` 把 3 个请求包在单个 `try/catch` 并静默吞错，任一失败永久停在「加载中...」。

## Goals / Non-Goals

**Goals:**

- 片段页能真正播放视频（单摄 + 双摄）。
- `list_segments` 返回与前端编辑器契约一致的完整字段。
- 数据加载失败时给出可见错误态 + 重试，不再永久「加载中...」。

**Non-Goals:**

- 双摄同步偏移（`offset_ms`）的自动补偿播放（当前各机位按自身时间轴播放，偏移补偿留待后续）。
- 双摄「合并单视频」（`default_analysis_video_id` 融合流）接入片段页。
- 上传类素材（upload）的片段能力（`viewCapabilities` 已将其标为 invalid）。

## Decisions

### D1: 后端在 `CaptureTakeSummary` 暴露 `video_ids`（视频源真相单源化）

**决策**：给 `GET /api/capture-takes/{id}` 返回的 [CaptureTakeSummary](file:///Users/tuian/Documents/大学/竞赛/大创/匹克球/前期展示web/pre-pickleball/backend/app/schemas/coding_actions.py#L70-L84) 增加 `video_ids: list[str]`，由 `capture_track_service.get_tracks_for_take(db, take.id)` 汇总各 track 的非空 `video_id`，按 `slot` 顺序（cam_1、cam_2）排列。

**补充（实现期发现）**：部分 legacy/测试 take 的 track 从未注册 `video_id`（如 `virtual-test-camera`），但其来源录制会话（RecordingSession.video_id / SyncRecordingSession.registered_video_ids、default_analysis_video_id）有可播视频。因此当 track 汇总为空时，回退到来源会话的已注册视频填充 `video_ids`，保证这类素材在片段页仍可播放（而不是空态）。回退顺序：track video_id → 来源会话已注册机位视频。

**理由**：片段页既在比赛库工作台（有 `LibraryItemViewModel` 可传参）也在独立路由（只有 takeId）使用。把视频源放在 take 详情上是两条入口的唯一公共真相；也符合「录制回放用 video_id」的既有契约（`recording-playback` spec）。

**备选**：由 `LibraryItemWorkspace` 把 `coverVideoUrl`/`cameraCoverSources` 以 props 传入 —— 无法覆盖独立路由，且引入 props 管道，弃用。

### D2: 片段页用 `trackOptions` 支持单摄/双摄播放

**决策**：`SegmentManagerPage` 从 `take.video_ids` 构造 `trackOptions = video_ids.map((id, i) => ({ label: video_ids.length > 1 ? \`机位${i + 1}\` : "原视频", url: getVideoStreamUrl(id) }))`，传入 [SegmentVideoPlayer](file:///Users/tuian/Documents/大学/竞赛/大创/匹克球/前期展示web/pre-pickleball/src/components/SegmentVideoPlayer.tsx#L13-L24)（其已内置 `trackOptions` + `onTrackChange` 下拉）。页面用 `activeVideoUrl` state 承接切换，默认取第一个。

**理由**：复用现成播放器能力，改动最小；单摄即单个选项，双摄即机位切换。彻底移除 `source_session_id` 拼 URL 的路径。

### D3: `list_segments` 复用完整序列化器 `_seg_dict`

**决策**：`routes_coding_actions.py::list_segments` 改为复用 [routes_segment_editing.py::_seg_dict](file:///Users/tuian/Documents/大学/竞赛/大创/匹克球/前期展示web/pre-pickleball/backend/app/api/routes_segment_editing.py#L206-L226)（该函数已输出 corrected/effective/edit_version/edit_status 全量字段），删除手工拼 dict。

**理由**：`_seg_dict` 已是权威序列化器（PATCH/拆分/合并等接口一致使用），列表接口与之对齐即消除契约漂移。前端 `CaptureSegmentSummary` 类型无需改动。

### D4: `loadData` 拆分 + 可见错误态

**决策**：把 `take`、`segments`、`events` 三个请求拆成独立加载，各自 `try/catch` 独立兜底；新增 `loadError` state，任一只读请求失败时渲染错误块（含重试按钮）而非永久「加载中...」；单个源失败不影响其余源展示。

**理由**：数据源相互独立（take 详情、segments、timeline-events），一处 404 不应瘫痪整页；错误可视化符合 `recording-playback` 的「回放失败稳定反馈」既有要求。

## Risks / Trade-offs

- **双摄时间轴偏移**：各机位按自身时间轴播放，take-time 跳转与机位 2 存在 `offset_ms` 偏差 → 在 `trackOptions` 切换 UI 上标注「机位」含义，偏移自动补偿列入后续工作，不进本变更。
- **`video_ids` 为空**：部分历史 take 可能没有注册 track 视频 → 页面显示「暂无可用视频回放」稳定空态（沿用 workspace 既有文案），不黑屏不报错。
- **`list_segments` 行为扩展**：新增字段为向后兼容的追加，`RecordingWorkspacePage` / `useLiveCoding` 等既有调用方不受影响。

## Migration Plan

- 后端：改 schema 与两个路由，属纯追加字段，无数据迁移。
- 前端：改 `SegmentManagerPage` / 类型，`video_ids` 缺失时回退到旧 `source_session_id` 行为前的空态提示。
- 验证：跑后端 `pytest`（片段接口断言字段契约）、前端 build + 片段页相关单测；手工在比赛库打开单摄/双摄素材验证「片段」Tab 可播放、机位可切换。
