## Context

「分析任务」页面的「录制视频任务」Tab 当前在 `src/App.tsx` 的 `AnalysisTasksPage` 内以扁平列表渲染：`recordings.map((session) => <RecordingTaskCard .../>)`（`App.tsx` 约第 833 行）。每条 `RecordingSession` 已携带 `field_session_id?` 字段，且后端在开录时已将其与 `FieldSession`（采集任务）关联；`listFieldSessions()` 与 `listRecordings({ field_session_id })` 前端封装均已就绪。数据层具备分组条件，但前端未利用。

现状约束：
- `RecordingSession` 持久化为 `data/recordings/sessions/{id}.json`，字段内含 `field_session_id`；`FieldSession` 存于 SQL 数据库。
- `RecordingTaskCard` 功能完整（播放 / 开始分析 / 查看结果 / 删除），可整体复用。
- 与进行中的 `add-dual-camera-sync-recording` 变更无关，本变更不触碰双摄录制路径。

## Goals / Non-Goals

**Goals:**
- 在「录制视频任务」Tab 内，按 `FieldSession` 分组展示 `RecordingSession`，先呈现采集任务大分组卡，再在其下挂对应的录制任务条。
- 分组卡支持**展开 / 收起**，采集任务较多时可折叠管理。
- 展示**全部采集任务分组**（含 0 条录制的空分组），空分组内部显示"暂无录制"占位。
- `field_session_id` 为空或指向已删除采集任务的录制归入底部**「未归类录制」**兜底分组。
- 顶部统计卡片保持跨全量计数，不受分组影响。
- 纯前端重构：后端零改动。

**Non-Goals:**
- 不修改 `RecordingSession` / `FieldSession` 数据模型或磁盘存储结构。
- 不改动「上传视频任务」Tab 与分析任务（AnalysisJob）链路。
- 不为采集任务增加新的增删改操作（创建/删除采集任务在球场采集页已完成）。
- 不实现"采集任务 → 录制 → 分析"三层嵌套（分析任务不在本次范围）。
- 不引入新的前端依赖或状态管理库。

## Decisions

### D1: 取数策略——先拉全量采集任务，再分发录制

因为需求要求**显示空采集任务分组**，必须拿到全部 `FieldSession` 作分组骨架，再把录制分发进去。

决策：`AnalysisTasksPage` 进入录制 Tab 时，先 `await listFieldSessions()`（取全量，必要时传大 `limit` 或不传）得到分组骨架；再 `await listRecordings()` 拿全部录制；前端纯函数 `groupRecordingsByFieldSession(fieldSessions, recordings)` 产出分组数组。

替代方案：只拉 `listRecordings()` 后按 `field_session_id` 去重 join `listFieldSessions(ids)`。否决，因为无法表达"0 条录制的采集任务"分组，与用户明确的"显示空分组"冲突。

### D2: 分组与排序规则

- **组间排序**：按采集任务「组内最近录制时间」倒序；空分组按 `FieldSession.created_at` 倒序参与排序。
- **组内排序**：录制按 `started_at` 倒序（最新录制在最上）。
- **未归类组**：永远排在分组列表最底部，其内部录制同样按 `started_at` 倒序。

决策理由：用户浏览录制时最关心"最近采集了什么"，以最近录制时间排序比按采集任务创建时间更贴近使用直觉；空分组仍需可见（用户明确要求）。

### D3: 分组卡组件 `FieldSessionGroupCard`

新增独立组件 `src/components/platform/FieldSessionGroupCard.tsx`，承载：
- 头部：采集任务 `title`、`venue` + `court_name`、`status` 标签、录制数徽标、组内最近录制时间；当组内存在 `status === "recording"` 时显示"录制中"高亮。
- 展开 / 收起按钮（chevron），受本地 `useState` 控制；默认展开。
- 折叠态下隐藏组内任务条列表，仅保留头部信息。
- 组内列表复用 `<RecordingTaskCard>`。
- 空分组：头部正常渲染，列表区显示"暂无录制"占位文本。

决策理由：把分组 UI 抽成独立组件，避免 `AnalysisTasksPage` 进一步膨胀（其已超 5000 行）；`RecordingTaskCard` 不改，保证播放/分析/删除行为稳定。

### D4: 未归类兜底分组

当录制的 `field_session_id` 为空，或该 id 在 `fieldSessions` 中找不到对应采集任务（采集任务已被删除）时，归入 `fieldSession = null` 的特殊组，标题「未归类录制」，渲染在列表末尾。

决策理由：早期录制、独立录制、或采集任务被删后的孤儿录制都需有归属，避免数据"消失"。

### D5: 顶部统计保持全量

现有统计卡片（全部录制 / 录制中 / 已完成 / 失败·取消）继续基于 `recordings` 全量计算，与分组渲染解耦，确保一眼看到整体状态。

### D6: 折叠状态的持久化（可选，默认不做）

本期折叠状态仅用组件内 `useState`，不跨刷新保留。若后续需要跨会话记忆展开/收起，再考虑 `sessionStorage`；当前不引入，避免范围蔓延。

## Risks / Trade-offs

- [Risk] `listFieldSessions()` 默认分页导致部分采集任务不显示。→ Mitigation：录制 Tab 加载时传足够大的 `limit` 或确认后端默认返回全量；分组前先做完整性校验。
- [Risk] 采集任务数量极多时列表过长。→ Mitigation：分组卡支持展开/收起，默认展开但用户可一键折叠；后续可加按状态/日期筛选（本期不做）。
- [Risk] 录制 `field_session_id` 指向已删除采集任务。→ Mitigation：分组逻辑将"找不到对应 FieldSession"的录制归入未归类组，不抛错。
- [Risk] 录制中状态轮询与分组重渲染叠加导致卡片抖动。→ Mitigation：沿用现有 3 秒轮询逻辑，仅在 `recordings` 变化时重算分组；`RecordingTaskCard` 以 `session_id` 作 key 保持稳定。

## Migration Plan

1. 新增 `FieldSessionGroupCard` 组件与 `groupRecordingsByFieldSession` 纯函数，不修改既有录制/采集 API。
2. 修改 `AnalysisTasksPage` 录制 Tab：增加 `fieldSessions` 状态与加载逻辑，渲染由扁平 `map` 改为分组 `map`。
3. 保留 `RecordingTaskCard` 原样，确保播放/分析/删除/轮询行为不变。
4. 验证：前端单测覆盖分组、空分组、未归类、排序；交互测试覆盖展开/收起与录制中高亮。
5. 回滚：移除分组渲染分支即可恢复扁平列表，数据层不受影响。

## Open Questions

- 组间排序默认用"组内最近录制时间"还是"采集任务创建时间"？本期采用最近录制时间，可在实现时按用户最终偏好微调。
- 折叠状态是否需要跨刷新持久化？本期不做，留作后续增强。
