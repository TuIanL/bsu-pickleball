## Why

Field Session 已经能表达一次场边采集任务的上下文，并能关联录制会话；下一步需要让采集过程留下可对齐视频的人工事件日志。这样后续分析任务不仅拿到一段视频，还能读取“非比赛时间、比分、换边、第几局、备注”等现场先验信息。

## What Changes

- 新增 Field Session 时间线事件能力，支持人工创建、查询、编辑和删除事件。
- 每个事件强关联 `field_session_id`，并可选关联 `recording_session_id`，用于把事件挂到具体录制视频时间线上。
- 事件保存 `timestamp_ms` 与 `occurred_at`，同时支持 `event_type`、`source`、`label`、`note` 和 `payload_json`。
- 事件类型覆盖备注、非比赛开始/结束、局/盘/回合开始结束、比分更新/修正、换边、暂停、练习片段和自定义标记等场边常见打点。
- 新增后端 REST API，用于按 Field Session 创建和筛选事件，并按事件 id 更新或删除事件。
- Field Session 采集控制台增加人工打点面板和时间线列表；不同 `capture_mode` 显示不同快捷按钮。
- Field Session 删除保护扩展到已有时间线事件的任务，避免误删现场日志。
- 暂不实现自动比分识别、自动回合切分、双摄 RecordingGroup 或分析 pipeline 对事件的强制消费。

## Capabilities

### New Capabilities
- `session-timeline-events`: 定义 Field Session 下的时间线事件模型、事件类型、时间戳规则、CRUD API、查询过滤和前端人工打点体验。

### Modified Capabilities
- `field-sessions`: 扩展 Field Session 的采集控制台要求和删除保护，使其能展示/操作时间线事件，并阻止删除已有事件的采集任务。

## Impact

- 后端：新增 timeline event ORM、Pydantic schema、service、API route，并在数据库初始化中注册模型。
- 后端 API：新增 `/api/field-sessions/{field_session_id}/timeline-events` 和 `/api/timeline-events/{event_id}` 相关端点。
- 前端：扩展 `src/types/report.ts`、`src/services/analysisClient.ts` 和 `CameraHubPage` 的 Field Session 控制台区域。
- 测试：新增后端 CRUD/时间戳/保护删除测试，新增前端 API 客户端和 UI 行为测试。
- 数据：新增 SQLite 表；RecordingSession 仍保持现有 JSON metadata 持久化方式，事件只保存其 `session_id` 字符串引用。
