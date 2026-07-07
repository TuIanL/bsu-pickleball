## 1. 数据库基础

- [x] 1.1 选择并加入后端 SQLite ORM 依赖（SQLAlchemy），更新依赖文件。
- [x] 1.2 新增数据库配置项，默认指向本地 `data` 目录下的 SQLite 文件。
- [x] 1.3 新增数据库 engine、session factory 和 FastAPI dependency。
- [x] 1.4 新增应用启动时的数据库初始化逻辑，确保所需表存在。
- [x] 1.5 为测试提供临时 SQLite 数据库配置或 fixture，避免污染开发数据。

## 2. Field Session 后端模型与服务

- [x] 2.1 新增 FieldSession 数据库模型，包含任务上下文、状态和时间戳字段。
- [x] 2.2 新增 Field Session 枚举或校验常量：`capture_mode`、`match_format`、`camera_setup`、`status`。
- [x] 2.3 新增 Field Session Pydantic schemas：创建、更新、详情、列表项。
- [x] 2.4 新增 Field Session service，封装创建、列表、读取、更新和状态流转。
- [x] 2.5 实现状态流转规则：`planned -> live`、`live -> completed`、`planned -> completed`、`completed -> archived`。

## 3. Field Session API

- [x] 3.1 新增 `POST /api/field-sessions` 创建 Field Session。
- [x] 3.2 新增 `GET /api/field-sessions` 列表接口，支持 `status`、`capture_mode`、`match_format`、`limit`、`offset` 查询参数。
- [x] 3.3 新增 `GET /api/field-sessions/{field_session_id}` 详情接口。
- [x] 3.4 新增 `PATCH /api/field-sessions/{field_session_id}` 元数据更新接口。
- [x] 3.5 新增 `POST /api/field-sessions/{field_session_id}/start` 开始任务接口。
- [x] 3.6 新增 `POST /api/field-sessions/{field_session_id}/complete` 完成任务接口。
- [x] 3.7 新增 `POST /api/field-sessions/{field_session_id}/archive` 归档任务接口。
- [x] 3.8 在 FastAPI app 中注册 Field Session router。
- [x] 3.9 新增 `DELETE /api/field-sessions/{field_session_id}` 删除空采集任务接口，并保护进行中或已有录制的任务。

## 4. RecordingSession 集成

- [x] 4.1 扩展 `RecordingStartRequest`，新增可选 `field_session_id`，并让 `match_format` 支持省略以便继承。
- [x] 4.2 扩展 `RecordingSession` 响应和 JSON metadata，新增可选 `field_session_id`。
- [x] 4.3 在开始录制前校验 `field_session_id` 是否存在，不存在时返回 404 且不启动 FFmpeg。
- [x] 4.4 实现 Field Session 上下文继承：未提供 `court_name` 时继承任务球场，未提供 `match_format` 时继承任务比赛形式。
- [x] 4.5 保持不传 `field_session_id` 的直接录制流程可用。
- [x] 4.6 扩展 `GET /api/recordings`，支持按 `field_session_id` 筛选。
- [x] 4.7 确保自动分析创建使用 RecordingSession 最终确定的 `court_name` 和 `match_format`。

## 5. 前端 API 与类型

- [x] 5.1 新增 Field Session TypeScript 类型定义。
- [x] 5.2 新增 Field Session API client 方法：create、list、get、update、start、complete、archive。
- [x] 5.3 扩展 `RecordingStartRequest` 和 `RecordingSession` 前端类型，加入可选 `field_session_id`。
- [x] 5.4 扩展 `listRecordings()` client，支持传入 `field_session_id` 查询参数。

## 6. 前端采集体验

- [x] 6.1 在球场采集页新增 Field Session 任务列表和新建任务入口。
- [x] 6.2 新增 Field Session 创建表单，包含任务名称、场馆、球场、采集模式、比赛形式、摄像头方案和备注。
- [x] 6.3 新增 Field Session 控制台状态，展示当前任务上下文和状态操作按钮。
- [x] 6.4 在 Field Session 控制台复用现有摄像头列表、探测、实时预览和录制控制。
- [x] 6.5 在 Field Session 控制台开始录制时传递 `field_session_id`。
- [x] 6.6 在 Field Session 控制台默认使用任务的 `court_name` 和 `match_format` 预填录制表单。
- [x] 6.7 保留无 Field Session 的旧直接录制入口和最近录制展示。
- [x] 6.8 在 Field Session 控制台为非进行中任务提供删除入口，并展示后端阻止原因。

## 7. 测试

- [x] 7.1 添加数据库初始化和临时数据库测试。
- [x] 7.2 测试创建 Field Session，验证默认状态和时间戳。
- [x] 7.3 测试 Field Session 列表、筛选和详情读取。
- [x] 7.4 测试 Field Session 元数据更新不改变状态。
- [x] 7.5 测试 Field Session 状态流转和非法流转错误。
- [x] 7.6 测试录制开始时有效 `field_session_id` 被保存到 RecordingSession。
- [x] 7.7 测试录制开始时不存在的 `field_session_id` 返回 404 且不启动录制。
- [x] 7.8 测试 `court_name` 和 `match_format` 从 Field Session 继承，以及请求显式值覆盖继承值。
- [x] 7.9 测试不带 `field_session_id` 的旧录制请求仍然正常。
- [x] 7.10 测试按 `field_session_id` 查询录制列表。
- [x] 7.11 测试删除空 Field Session、拒绝删除进行中 Field Session、拒绝删除已有录制的 Field Session。

## 8. 验证与文档

- [x] 8.1 运行后端测试套件，确认 Field Session 和录制兼容场景通过。
- [x] 8.2 运行前端类型检查和测试。
- [x] 8.3 手动验证创建 Field Session、进入控制台、选择摄像头、开始录制的端到端流程。
- [x] 8.4 更新必要的 README 或开发说明，记录 SQLite 数据库位置和存储边界。
