## Why

当前球场采集页已经能注册摄像头、预览视频流并创建录制会话，但录制仍是孤立的摄像头级 JSON 记录，缺少“一次真实球场采集任务”的上层业务上下文。后续要支持双摄、人工事件、比分、换边、多人多局和半实时分析时，继续把关联关系堆在零散文件里会让状态追踪、筛选和归属变得脆弱。

现在引入轻量 SQLite 数据层，并先把 Field Session 作为第一批数据库业务对象落地，可以在不重构算法产物文件存储的前提下，为后续采集、录制和分析任务建立稳定主干。

## What Changes

- 新增本地 SQLite 数据层，用于保存业务索引、状态和对象关系。
- 新增 Field Session（球场采集任务）能力，作为一次球场采集活动的顶层容器。
- 新增 Field Session API，支持创建、列表、详情、更新和状态流转。
- 扩展现有 RecordingSession，让录制会话可以可选关联到 Field Session。
- 扩展开始录制接口，支持 `field_session_id`，并在 Field Session 上下文中继承 `court_name` 和 `match_format`。
- 前端新增 Field Session 创建入口、任务列表和任务采集控制台，并在控制台中复用现有摄像头预览与录制能力。
- 保留现有直接录制路径，不要求用户必须先创建 Field Session。
- 算法输出、视频文件、标定文件、叠加结果和报告产物继续保存在文件系统中，本 change 不迁移这些大文件和产物。

## Capabilities

### New Capabilities

- `local-database-foundation`: 定义本地 SQLite 数据层的职责、生命周期、初始化和与文件系统产物的边界。
- `field-sessions`: 定义 Field Session 作为球场采集任务上下文的创建、查询、更新、状态流转和前端使用方式。

### Modified Capabilities

- `recording-session-control`: 录制会话可以可选关联 Field Session；开始录制时可以从 Field Session 继承球场名称和比赛形式，并保持旧的直接录制行为。

## Impact

- 后端新增数据库依赖和初始化代码，建议使用 SQLAlchemy 或 SQLModel 管理 SQLite 连接与模型。
- 后端新增 Field Session schema、service 和 API route，并在 `app.main` 注册路由。
- 后端扩展 `RecordingStartRequest`、`RecordingSession`、录制服务和录制 API。
- 前端扩展 API client、类型定义和 `/camera` 采集页面路由/状态。
- 测试新增数据库初始化、Field Session API、录制关联和旧录制兼容场景。
- 存储边界调整为：SQLite 保存业务元数据和关系，文件系统继续保存视频、JSON 分析产物和可视化文件。
