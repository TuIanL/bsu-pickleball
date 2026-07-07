## Context

当前后端主要使用本地文件保存业务元数据和算法产物：摄像头配置位于 `data/cameras/*.json`，录制会话位于 `data/recordings/sessions/*.json`，视频、标定、分析结果和叠加产物也都落在文件系统中。这种方式适合单对象读写和算法产物管理，但 Field Session 会引入更强的对象关系：一次球场采集任务会关联多段录制，未来还会关联双摄分组、人工事件、比分、换边和分段分析。

本 change 需要在不破坏现有录制路径的前提下，引入轻量数据库层。数据库只承担业务索引、状态和关系；大文件和算法产物仍继续由文件系统保存。

## Goals / Non-Goals

**Goals:**

- 引入本地 SQLite 数据库作为业务元数据和关系的持久化基础。
- 新增 Field Session，作为球场采集任务的顶层上下文。
- 让 RecordingSession 可以可选关联 Field Session，并在上下文中继承球场名称和比赛形式。
- 保留现有直接录制流程，避免要求用户必须创建 Field Session。
- 为后续 TimelineEvent、RecordingGroup、Score 和 AnalysisProfile 留出稳定的数据主干。

**Non-Goals:**

- 不迁移视频文件、标定文件、分析产物、叠加视频或报告产物到数据库。
- 不在本 change 中实现人工时间线打点、比分记录、换边、双摄同步或分段分析。
- 不把所有既有 JSON 元数据一次性迁入数据库。
- 不改变现有算法 pipeline 的执行逻辑。

## Decisions

### 使用 SQLite 作为第一版数据库

SQLite 适合当前本地 MVP 形态：无需单独数据库服务，部署成本低，能提供事务、索引和关系约束。Postgres 等服务型数据库更适合多人协作和云端部署，但现在会显著增加运行环境复杂度。

### 数据库保存业务元数据，文件系统保存产物

数据库保存 Field Session、状态、上下文枚举和对象关联。视频文件、分析 JSON、JSONL、图片和叠加视频仍保存到文件系统，并在数据库或 JSON 元数据中只保存 id 或路径引用。这样既能获得关系查询能力，也不会把大文件读写塞进数据库。

### Field Session 第一批进入数据库，RecordingSession 采用渐进兼容

Field Session 是新增主对象，直接落库。RecordingSession 当前已有 JSON 生命周期和录制服务，本 change 只扩展其模型和持久化内容，增加可选 `field_session_id`。如果实现时引入数据库 recording 表，也必须保持旧 JSON 记录可读并确保现有 API 响应兼容；更推荐先不迁移完整 RecordingSession 表，等 RecordingGroup 或 TimelineEvent change 再推进。

### Field Session 状态流转使用专门 API

状态流转通过 `/start`、`/complete`、`/archive` 等专门端点完成，而不是让普通 PATCH 任意改状态。这样能集中控制 `started_at`、`ended_at` 和非法状态转换。

### 录制上下文继承以 Field Session 为默认值，请求显式值可覆盖

当 `field_session_id` 存在时，录制服务读取 Field Session。如果请求没有提供 `court_name` 或 `match_format`，则使用 Field Session 的值；如果请求显式提供，则使用请求值。这保留现场临时覆盖能力，也让旧录制表单继续工作。

## Risks / Trade-offs

- [Risk] 引入数据库依赖会增加后端初始化和测试复杂度。→ Mitigation: 使用 SQLite，本地默认路径放在 `data/app.sqlite3` 或配置项下；测试使用临时数据库。
- [Risk] JSON RecordingSession 与 SQLite FieldSession 混合存储会形成短期双存储模型。→ Mitigation: 明确边界：Field Session 落库，RecordingSession 暂保 JSON 并保存 `field_session_id`；后续迁移再单独 propose。
- [Risk] `match_format` 当前有默认值，可能影响“省略后继承”的判断。→ Mitigation: 后端请求 schema 将 `match_format` 变为可选，服务层在没有请求值时应用默认或继承值；前端也可在控制台中预填 Field Session 值。
- [Risk] 状态流转规则过严会挡住现场误操作修正。→ Mitigation: 第一版允许 `planned -> completed`，用于补录或只归档任务；保留元数据 PATCH，但不通过 PATCH 任意改状态。
- [Risk] 过早设计完整数据库模型会扩大 scope。→ Mitigation: 只实现数据库基础和 Field Session 表，未来对象只在设计中预留，不在本 change 中实现。

## Migration Plan

1. 新增数据库配置、engine/session 初始化和应用启动时的表创建或轻量 migration。
2. 新增 Field Session 数据模型、service、schema 和 API。
3. 扩展 RecordingSession Pydantic 模型和录制开始请求，新增可选 `field_session_id`。
4. 在开始录制时校验 Field Session 是否存在，并执行上下文继承。
5. 前端新增 Field Session 类型和 API client，扩展 `/camera` 页面为任务列表加控制台形态。
6. 补充 API 和服务测试，使用临时 SQLite 数据库隔离测试数据。

Rollback 策略：由于旧直接录制不依赖 Field Session，若数据库初始化失败，应让 Field Session API 返回明确错误；实现阶段可选择让旧录制路径继续可用。数据库文件可删除后重新初始化，已生成视频和算法产物不受影响。

## Open Questions

- 第一版是否需要把 RecordingSession 同步写入数据库索引表，还是只在 JSON 中保存 `field_session_id`？
- Field Session id 使用 UUID 字符串，还是沿用可读前缀如 `fs_YYYYMMDD_HHMMSS`？
- 前端是否引入独立路由 `/field-sessions/{id}/capture`，还是先在 `/camera?fieldSessionId=...` 内完成控制台？
