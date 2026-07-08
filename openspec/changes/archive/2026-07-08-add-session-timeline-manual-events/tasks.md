## 1. 后端数据模型与 schema

- [x] 1.1 新增 `backend/app/models/timeline_event.py`，定义 `SessionTimelineEvent`、`TimelineEventType` 和 `TimelineEventSource`
- [x] 1.2 在数据库初始化中注册 timeline event 模型，确保 SQLite 启动时创建 `session_timeline_events` 表
- [x] 1.3 新增 `backend/app/schemas/timeline_event.py`，定义创建、更新、详情和列表筛选所需 Pydantic schema
- [x] 1.4 为 `timestamp_ms`、`event_type`、`source` 和 `payload_json` 添加 schema 级校验

## 2. 后端服务与 API

- [x] 2.1 新增 `backend/app/services/timeline_event_service.py`，实现创建、列表、读取、更新和删除事件
- [x] 2.2 在创建事件时校验 Field Session 存在，并校验可选 `recording_session_id` 存在且归属匹配
- [x] 2.3 实现时间戳策略：前端提交优先，缺省且有关联录制时后端兜底计算，否则保存为 0
- [x] 2.4 新增 `backend/app/api/routes_timeline_events.py`，提供创建、查询、更新和删除 REST API
- [x] 2.5 在 `backend/app/main.py` 注册 timeline event router
- [x] 2.6 扩展 Field Session 删除服务和 route，使已有 timeline events 的任务删除时返回 409

## 3. 前端类型与 API 客户端

- [x] 3.1 在 `src/types/report.ts` 中新增 timeline event 类型、创建请求、更新请求和筛选参数类型
- [x] 3.2 在 `src/services/analysisClient.ts` 中新增创建、列表、更新和删除 timeline event 的 API 函数
- [x] 3.3 为前端快捷事件生成稳定的 `event_type`、`label`、`note` 和 `payload_json` 映射

## 4. Field Session 控制台 UI

- [x] 4.1 在 `CameraHubPage` 选择 Field Session 时加载对应 timeline events，并在事件变更后刷新列表
- [x] 4.2 在存在关联录制中的 RecordingSession 时显示人工快捷打点面板
- [x] 4.3 按 `capture_mode` 显示比赛、练习和工程模式的不同快捷按钮
- [x] 4.4 实现比分更新、比分修正、换边、非比赛开始/结束、备注和自定义标记的创建流程
- [x] 4.5 新增时间线事件列表，按时间戳展示事件类型、label、note 和 payload 摘要
- [x] 4.6 新增事件编辑入口，允许修改时间戳、label、note 和 payload
- [x] 4.7 新增事件删除入口，并展示后端删除或保护失败原因
- [x] 4.8 保持直接录制模式不要求加载或创建 timeline events

## 5. 测试

- [x] 5.1 新增后端测试覆盖 timeline event 创建、读取、筛选、更新和删除
- [x] 5.2 新增后端测试覆盖不存在 Field Session、无效 RecordingSession、录制归属不匹配和负时间戳校验
- [x] 5.3 新增后端测试覆盖 timestamp 兜底计算和无录制事件默认 `timestamp_ms=0`
- [x] 5.4 扩展 Field Session 删除测试，覆盖已有 timeline events 时返回 409
- [x] 5.5 新增或扩展前端测试，覆盖 API 客户端请求路径和 Field Session 控制台事件操作主流程

## 6. 验证

- [x] 6.1 运行后端相关 pytest，确认 Field Session、RecordingSession 和 timeline event 流程通过
- [x] 6.2 运行前端类型检查和测试，确认新增类型/API/UI 没有回归
- [x] 6.3 手动验证场边流程：创建 Field Session、开始任务、开始录制、打点、停止录制、编辑/删除事件、查看时间线列表
- [x] 6.4 运行 `openspec status --change add-session-timeline-manual-events`，确认 change 达到 apply-ready 状态
