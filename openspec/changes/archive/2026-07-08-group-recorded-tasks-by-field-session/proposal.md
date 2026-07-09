## Why

当前「分析任务」页面的「录制视频任务」Tab 把所有 `RecordingSession` 以**扁平列表**呈现，用户无法直观看到"哪几条录制属于同一次球场采集任务"。后端早已在 `RecordingSession.field_session_id` 上建立与 `FieldSession`（采集任务）的关联，且现场开录时已写入该字段，但前端没有利用这层关系做分组。随着采集任务增多，扁平列表会让用户难以按采集场景归并、回溯和批量管理录制。

## What Changes

- 在「录制视频任务」Tab 中，先以 `FieldSession`（采集任务）作为大分组卡呈现，再在其下按采集任务分类展示对应的录制任务条（`RecordingTaskCard` 复用，不重写）。
- 分组卡支持**展开 / 收起**：采集任务多时可折叠，组内录制数用徽标提示。
- 展示**全部采集任务分组（含 0 条录制的空分组）**，空分组内部显示"暂无录制"占位。
- 录制任务条按 `field_session_id` 分发到对应采集任务；`field_session_id` 为空或指向已删除采集任务的录制归入底部**「未归类录制」**兜底分组。
- 顶部统计卡片（全部 / 录制中 / 已完成 / 失败·取消）保持跨全量计数，不受分组影响。
- **纯前端分组重构**：先拉取 `listFieldSessions()` 取全量采集任务作分组骨架，再拉取 `listRecordings()` 按 `field_session_id` 分发；磁盘 JSON / 视频文件不动，后端零改动。

## Capabilities

### New Capabilities
- `recorded-task-grouping`: 定义「录制视频任务」Tab 内按 `FieldSession` 分组展示 `RecordingSession` 的行为，包括分组骨架来源、组内任务条复用、分组卡展开/收起、空采集任务分组、未归类兜底分组与排序规则。

### Modified Capabilities
- （无）本变更不修改既有 spec 的需求；`field-sessions` 仅作为关联上下文被引用。

## Impact

- 前端：
  - `src/App.tsx` 的 `AnalysisTasksPage`：「录制视频任务」Tab 增加 `fieldSessions` 状态与 `loadFieldSessions` 加载逻辑，渲染由扁平 `recordings.map(RecordingTaskCard)` 改为按分组 `map`。
  - 新增 `FieldSessionGroupCard` 组件（建议置于 `src/components/platform/`），承载分组大卡、展开/收起状态、录制数徽标与组内任务条列表。
  - 新增分组 / 排序纯函数（如 `groupRecordingsByFieldSession`），便于单测。
- 后端：无需改动。`field_session_id` 关联、`listFieldSessions()`、`listRecordings({ field_session_id })` 均已就绪。
- 数据：不迁移。`RecordingSession` 仍按 `data/recordings/sessions/{id}.json` 存储，仅靠 `field_session_id` 字段关联。
- 依赖：不新增前端依赖。
- 测试：新增前端分组逻辑单测（分组、空分组、未归类、排序），并补充 `AnalysisTasksPage` 录制 Tab 分组渲染的交互测试。
