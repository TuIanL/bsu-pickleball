## Context

当前录制控制台架构存在两个独立的录制路径：

- **单摄录制**：RecordingSession（Pydantic/JSON 文件存储）→ FFmpeg 直接录制 MP4
- **双摄录制**：SyncRecordingSession（Pydantic/JSON 文件存储）→ 多段 .ts 合并为 MP4

事件系统（SessionTimelineEvent）只与单摄的 `recording_session_id` 绑定，双摄无法打点。事件是扁平的时间点，无法表达"盘→局→分"的层级关系。

**关键约束**：
- FieldSession 是规划实体（ORM/SQLite），RecordingSession 是运行实体（JSON 文件）
- 单摄/双摄互斥，同一时间只能有一个录制在进行
- 现有事件创建 API 只接受 `recording_session_id`，需要向后兼容
- 录制生命周期 JSON 与 SQLite 之间存在共识缺口，无法形成真正跨存储事务
- 当前 `init_db()` 只使用 `create_all()`，无法增量增加列

## Goals / Non-Goals

**Goals:**
- 引入 CaptureTake 统一时间轴，抽象单摄/双摄为统一的录制单元
- 引入 CaptureCodingAction 持久化命令模型，支撑幂等、undo、审计
- 实现后端事务内 coding-actions API，保证事件、片段与状态的一致性（SQLite 层面）
- 实现"下一分"一键推进，减少现场操作频率
- 支持双摄录制时打点
- 提供只读多轨实时时间线 UI
- 实现局部深色专业分析模式 UI
- 引入 Alembic 数据库迁移体系

**Non-Goals:**
- 不实现赛后片段管理（编辑边界、拆分、合并、删除、批量选择、按片段分析）——这些进入单独 Change
- 不实现自动得分识别或比分更新
- 不实现完整的离线 PWA（只做事件 Outbox 和重试）
- 不实现视频裁切导出
- 不重构现有的录制服务架构（只在上层添加 CaptureTake 抽象层）
- 不修改现有的分析流水线

## Decisions

### Decision 1: CaptureTake 作为统一时间轴抽象层

**选择**：新增 CaptureTake/CaptureTrack 模型，作为单摄/双摄的统一抽象层

**理由**：
- CaptureTake 是逻辑层，不改变底层录制实现
- 保留 `recording_session_id` 兼容字段，支持旧数据渐进迁移
- 支持双摄分段式时间偏移映射

**数据模型**：

```sql
CREATE TABLE capture_takes (
  id TEXT PRIMARY KEY,              -- ct_{uuid}
  field_session_id TEXT NOT NULL,
  capture_mode TEXT NOT NULL,       -- 'single' | 'dual'
  source_session_type TEXT NOT NULL, -- 'recording' | 'sync_recording'
  source_session_id TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'recording',
  started_at DATETIME NOT NULL,
  ended_at DATETIME,
  duration_ms INTEGER CHECK(duration_ms IS NULL OR duration_ms >= 0),
  revision INTEGER NOT NULL DEFAULT 0 CHECK(revision >= 0),
  archived_at DATETIME,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

  UNIQUE(source_session_type, source_session_id)
);
CREATE INDEX idx_capture_takes_field_session ON capture_takes(field_session_id, started_at);
CREATE INDEX idx_capture_takes_status ON capture_takes(status);
```

```sql
CREATE TABLE capture_tracks (
  id TEXT PRIMARY KEY,              -- tr_{uuid}
  capture_take_id TEXT NOT NULL REFERENCES capture_takes(id) ON DELETE RESTRICT,
  camera_id TEXT NOT NULL,
  role TEXT NOT NULL,               -- 'primary' | 'secondary'
  video_id TEXT,
  offset_ms INTEGER NOT NULL DEFAULT 0,
  offset_source TEXT NOT NULL DEFAULT 'assumed',  -- 'measured' | 'assumed' | 'corrected'
  sync_quality TEXT NOT NULL DEFAULT 'unknown',   -- 'good' | 'degraded' | 'unknown'
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

  UNIQUE(capture_take_id, role)
);
CREATE INDEX idx_capture_tracks_take ON capture_tracks(capture_take_id);
```

**双摄分段式时间映射**：双摄支持多段录制和重启，单一 `offset_ms` 不够。第一版增加 `offset_source` 和 `sync_quality` 字段标记偏移可信度。事件始终保存 CaptureTake 相对时间，映射到具体视频轨道时通过 Track 的 offset 计算：`track_relative_ms = event.timestamp_ms - track.offset_ms`。

**删除行为**：录制前创建错误且无事件/轨道资产的 CaptureTake 可硬删除；已开始录制或存在关联事件的只能通过 `archived_at` 标记归档。

### Decision 2: CaptureCodingAction 持久化命令模型

**选择**：新增 CaptureCodingAction 模型，保存每条语义命令的完整处理记录

**理由**：以下能力都依赖持久化命令日志：
- client_action_id 幂等（重启不丢失）
- undo 操作
- 状态重放与修复
- 审计追踪
- 判断同一 ID 是否被不同 payload 重用

**数据模型**：

```sql
CREATE TABLE capture_coding_actions (
  id TEXT PRIMARY KEY,              -- ca_{uuid}
  capture_take_id TEXT NOT NULL REFERENCES capture_takes(id) ON DELETE RESTRICT,
  client_action_id TEXT NOT NULL,
  action_type TEXT NOT NULL,
  timestamp_ms INTEGER NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{}',

  request_hash TEXT NOT NULL,       -- payload + action_type 的哈希，检测重放
  status TEXT NOT NULL,             -- 'executed' | 'undone' | 'rejected'
  revision_before INTEGER NOT NULL,
  revision_after INTEGER,

  result_json TEXT,                 -- 执行结果：created_events/updated_segments
  error_code TEXT,                  -- 失败时的错误码

  reverses_action_id TEXT,          -- undo：指向被撤销的 action
  created_at DATETIME NOT NULL,
  completed_at DATETIME,

  UNIQUE(capture_take_id, client_action_id)
);
CREATE INDEX idx_coding_actions_take_revision ON capture_coding_actions(capture_take_id, revision_before);
```

**职责分离**：
```
SessionTimelineEvent   = 发生了什么事实（用户或系统创建的时间点）
CaptureCodingAction    = 用户发出了什么命令，系统如何处理
CaptureSegment         = 为查询和显示生成的区间投影
LiveCodingState        = 当前状态的快速快照，可从事务日志重建
```

### Decision 3: 后端事务内 coding-actions API

**选择**：新增语义级命令 API，后端在一个 SQLite 事务中完成 command log + events + segments + state 的创建

**替代方案**：
- A. 前端直接组合多个 API 调用 → 无法保证原子性
- B. 后端异步解析 → 存在不一致窗口

**API 设计**：

```http
POST /api/capture-takes/{capture_take_id}/coding-actions

Request:
{
  "action": "start_next_rally" | "start_set" | "start_game" | "end_rally" | "end_game" | "end_set" | "toggle_non_play" | "change_side" | "add_note" | "undo",
  "timestamp_ms": 62840,
  "client_occurred_at": "2026-07-10T08:15:42.000Z",
  "client_action_id": "01J...",
  "expected_revision": 17,
  "payload": {}
}

Response (200):
{
  "revision": 18,
  "created_events": [...],
  "updated_segments": [...],
  "live_state": { "set_ordinal": 1, "game_ordinal": 2, "rally_ordinal": 8, "non_play": false }
}

Response (409 - revision conflict):
{
  "error": "revision_conflict",
  "current_revision": 18,
  "live_state": {...}
}

Response (409 - duplicate client_action_id):
{
  "error": "duplicate_action",
  "existing_action_id": "ca_...",
  "status": "executed",
  "result": {...}
}
```

**事务结构**（所有操作在同一个 `db.begin()` 内）：

```python
with db.begin():
    action = create_action_record(client_action_id, ...)     # 幂等检查
    events = apply_action(action_type, timestamp_ms, ...)     # 创建/关闭事件
    segments = update_segments(events)                        # 创建/关闭区间
    state = update_live_state(segments)                       # 更新当前状态
    complete_action_record(action, events, state)             # 记录结果
    # 单次 commit
```

**服务层重构**：当前 `create_timeline_event()` 内部直接 `db.commit()`，必须拆为两层：

```python
# 内部方法（不提交事务）
def _add_timeline_event(db: Session, ...) -> SessionTimelineEvent:
    event = SessionTimelineEvent(...)
    db.add(event)
    db.flush()
    return event

# 外部 API 方法（负责事务）
def create_timeline_event(db: Session, ...) -> SessionTimelineEvent:
    with db.begin():
        event = _add_timeline_event(db, ...)
    return event
```

coding-actions handler 直接调用内部方法，在最外层统一 commit。

### Decision 4: LiveCodingState 是可重建快照

**选择**：LiveCodingState 是当前状态快照，每次成功 action 在同一事务内更新，可从 CaptureCodingAction + SessionTimelineEvent 完全重建

**定位**：
- CaptureCodingAction + SessionTimelineEvent = 不可变审计记录（真相）
- CaptureSegment = 区间投影（派生数据）
- LiveCodingState = 当前状态快照（可以从事务日志重建）

**持久化策略**：每次成功的 coding action 都与 action、event、segment 在同一事务中更新，不需要"每隔 N 次"定期保存。

**状态结构**：

```sql
CREATE TABLE live_coding_states (
  capture_take_id TEXT PRIMARY KEY REFERENCES capture_takes(id) ON DELETE CASCADE,
  revision INTEGER NOT NULL,
  set_ordinal INTEGER NOT NULL DEFAULT 0,
  game_ordinal INTEGER NOT NULL DEFAULT 0,
  rally_ordinal INTEGER NOT NULL DEFAULT 0,
  non_play BOOLEAN NOT NULL DEFAULT 0,
  current_set_segment_id TEXT,
  current_game_segment_id TEXT,
  current_rally_segment_id TEXT,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

事件重放用于：数据库修复、一致性检测、测试、历史数据重建。正常请求不进行全量重放。

### Decision 5: 完整层级状态转移规则

**选择**：定义每个 action 的完整状态转移规则，缺父级时自动创建 inferred 父级

| Action | 处理规则 |
|--------|---------|
| `start_set` | 关闭 open rally → 关闭 open game → 关闭上一个 set，创建新的 open set；Game/Rally ordinal 归零 |
| `start_game` | 关闭 open rally → 关闭上一个 game；如果无 set，创建 inferred set；创建新的 open game；Rally ordinal 归零 |
| `start_next_rally` | 关闭上一个 open rally → 创建新的 open rally；如果无 game，创建 inferred game；如果无 set，创建 inferred set；Rally ordinal +1 |
| `end_rally` | 关闭 open rally；无 open rally → no-op（不报错） |
| `end_game` | 先关闭 open rally，再关闭 open game；无 open game → no-op |
| `end_set` | 先关闭 open rally、game，再关闭 open set；无 open set → no-op |
| `toggle_non_play` 开启 | 关闭 open rally（保留 set/game open），创建 non_play_start 事件 |
| `toggle_non_play` 结束 | 创建 non_play_end 事件，不自动创建新 rally |
| `change_side` | 创建 side_change 点事件，不改变层级 |
| 录制停止 | 所有 open 区间以 `status=inferred`、`close_reason=recording_stopped` 关闭 |

**设计原则**：现场操作不能因为漏点「盘开始」就拒绝用户记录下一分。缺父级时自动创建 inferred 父级。

### Decision 6: 误双击与 409 冲突处理

**选择**：禁止 stale revision 动作无条件自动重试；相同 client_action_id 直接返回结果；不同 client_action_id 返回 409 但不自动重试

**规则**：

1. **相同 client_action_id**（无论 revision 是否过期）→ 直接返回第一次执行结果，幂等
2. **不同 client_action_id，revision 匹配** → 正常执行
3. **不同 client_action_id，revision 过期** → 返回 409 + 当前 revision + live_state，不自动重试

**前端处理**：
- 每个 CaptureTake 维护单路 FIFO 发送队列
- 同一时间最多一个 inflight action
- 前一个确认后，用服务器返回的最新 revision 发送下一个
- 同一按钮增加 ~400ms debounce/误双击抑制
- 用户快速连续操作（如连续点击"下一分"）通过队列顺序发送，不会并发

### Decision 7: FIFO Outbox 有序队列

**选择**：Outbox 定义为每个 capture_take_id 一条 FIFO 队列，失败阻塞后续，保证顺序

**数据结构**：

```ts
interface CodingOutboxItem {
  clientActionId: string;
  captureTakeId: string;
  sequenceNumber: number;
  action: CodingActionType;
  timestampMs: number;             // 用户点击时的原始时间戳，重试不改变
  clientOccurredAt: string;
  payload: Record<string, unknown>;

  status: "pending" | "sending" | "synced" | "blocked" | "failed";
  retryCount: number;
  lastError?: string;
  createdAt: number;
}
```

**关键约束**：
- 前一条成功后，用服务器返回的 revision 发送下一条
- 失败时暂停后续所有动作
- 重试时保留用户点击时的 `timestamp_ms`，不使用重试发生时的当前时间
- 指数退避重试（1s → 2s → 4s → 8s），最大 5 次

### Decision 8: undo 语义

**选择**：undo 不删除数据库行，而是新增 undo action 记录 + corrected/tombstone 事件，重建受影响区间和状态

**实现**：
- 找到当前 CaptureTake 最后一个可撤销且未被撤销的 CodingAction
- 新增一条 undo CodingAction，`reverses_action_id` 指向被撤销的 action
- 创建 corrected 事件或为原事件设置 `is_undone=true`
- 重建受影响的 CaptureSegment 和 LiveCodingState
- revision +1

**限制**：
- 不能撤销录制开始/停止
- 不能跨 CaptureTake 撤销
- 默认只撤销最后一个用户动作
- 已经被后续动作依赖时，通过重放重建

### Decision 9: 时间戳来源策略

**选择**：前端提交 `timestamp_ms` + `client_occurred_at`，后端负责权威时间计算和合理性校验

**规则**：
1. 在线操作优先使用前端计算的 take-relative `timestamp_ms`
2. 后端根据 `CaptureTake.started_at` 做合理范围校验（允许 ±5s 误差）
3. 未提交时，后端按 `now - CaptureTake.started_at` 计算
4. Outbox 重试保留原始点击时间，不更新
5. Track offset 不参与事件 timestamp 的保存
6. 前端的 `setInterval` 显示计时器仅作 UI 参考

### Decision 10: 局部深色主题

**选择**：只在 `/capture/{id}/live` 路由启用局部 CSS 变量

```css
.capture-workspace {
  --workspace-bg: #11171c;
  --workspace-panel: #1b242c;
  --workspace-border: #33414d;
  --workspace-text: #f7fafc;
}
```

**按钮颜色编码**：
```text
盘 (Set)      橙色 #F97316
局 (Game)     蓝色 #3B82F6
分 (Rally)    绿色 #22C55E
暂停 (Timeout) 黄色 #EAB308
换边 (Side)   紫色 #A855F7
非比赛         灰色 #6B7280
撤销 (Undo)   红色 #EF4444
```

### Decision 11: 时间线只渲染区间和事件

只渲染盘/局/分区间和离散事件，不按秒生成数据点。第一版使用 DOM 绝对定位，渲染模型：

```
left  = start_ms / total_duration_ms * 100%
width = (end_ms - start_ms) / total_duration_ms * 100%
```

当前进行中的区间（open）右边界随时间动态延伸。缩放级别自动跟随——最近 N 分钟占满视口。

### Decision 12: 暂停 vs 停止语义分离

- 比赛暂停：创建 `timeout_start` / `timeout_end`，录制继续，文件不中断
- 录制停止：物理文件结束，关闭所有 open 区间（状态 = `inferred`）

### Decision 13: 跨存储事务补偿

录制 JSON（文件系统）与 SQLite 之间无法原子化。采用补偿流程：

```text
1. 完成底层录制停止（JSON 更新）
2. 更新 CaptureTake 和 open segments（SQLite）
3. 如果步骤 2 失败，记录 reconciliation_pending
4. 下次启动或查询时执行修复
```

coding-action 内部的事件、区间、状态和 action log 在 SQLite 层面保证原子性。不声称跨存储原子性。

### Decision 14: Alembic 数据库迁移

当前 `init_db()` 使用 `Base.metadata.create_all()`，无法增量修改已有表结构。必须引入 Alembic：

```text
alembic init
生成 initial baseline（现有 schema）
新增 migration：capture_takes / capture_tracks / capture_coding_actions / live_coding_states / capture_segments
ALTER TABLE session_timeline_events ADD COLUMN capture_take_id
ALTER TABLE session_timeline_events ADD COLUMN is_undone
创建索引和约束
```

## Data Model Constraints

TimelineEvent：
```sql
ALTER TABLE session_timeline_events ADD COLUMN capture_take_id TEXT REFERENCES capture_takes(id);
ALTER TABLE session_timeline_events ADD COLUMN is_undone BOOLEAN NOT NULL DEFAULT 0;
CREATE INDEX idx_timeline_events_take_time ON session_timeline_events(capture_take_id, timestamp_ms);
```

CaptureSegment（最小投影模型，第一版只支持创建和查询）：
```sql
CREATE TABLE capture_segments (
  id TEXT PRIMARY KEY,
  capture_take_id TEXT NOT NULL REFERENCES capture_takes(id) ON DELETE RESTRICT,
  segment_type TEXT NOT NULL,       -- 'set' | 'game' | 'rally'
  parent_segment_id TEXT REFERENCES capture_segments(id),
  ordinal INTEGER NOT NULL DEFAULT 1,
  label TEXT NOT NULL DEFAULT '',
  start_event_id TEXT,
  end_event_id TEXT,
  start_ms INTEGER NOT NULL,
  end_ms INTEGER,
  status TEXT NOT NULL DEFAULT 'open',   -- 'open' | 'closed' | 'inferred'
  close_reason TEXT,                     -- 'user_action' | 'recording_stopped' | null
  source TEXT NOT NULL DEFAULT 'manual', -- 'manual' | 'algorithm' | 'corrected'
  is_highlight BOOLEAN NOT NULL DEFAULT 0,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

  CHECK(end_ms IS NULL OR end_ms >= start_ms)
);
CREATE INDEX idx_segments_take_type ON capture_segments(capture_take_id, segment_type, start_ms);
CREATE INDEX idx_segments_parent ON capture_segments(parent_segment_id);
```

## Risks / Trade-offs

### Risk 1: 旧数据迁移复杂度
**风险**：现有 RecordingSession 需要适配到 CaptureTake，可能存在数据不一致
**缓解**：读时渐进迁移，不强制批量迁移；保留 `recording_session_id` 兼容字段

### Risk 2: 双摄分段式时间偏移
**风险**：多段录制重启后偏移可能不一致
**缓解**：offset_source/offset_quality 标记可信度；事件始终保存 CaptureTake 相对时间；赛后可修正

### Risk 3: 前端乐观队列与后端不一致
**风险**：FIFO 队列中的操作可能因为历史 revision 冲突而延迟
**缓解**：UI 显示每条动作的同步状态（pending/syncing/synced/blocked）；队列长度不宜超过 ~5

### Risk 4: coding-actions 事务竞争
**风险**：快速连续点击时的事务锁竞争
**缓解**：前端 FIFO 队列保证单路请求；SQLite WAL 模式支持并发读

### Risk 5: Alembic 迁移失败
**风险**：首次引入迁移框架时的配置错误
**缓解**：保留 create_all() 作为 fallback；迁移脚本支持幂等执行

### Trade-off: 复杂度 vs 可靠性
引入 CaptureTake、CaptureCodingAction 和 FIFO Outbox 增加了系统复杂度，但换取了：单摄/双摄统一体验、事务内一致性、幂等性、undo 和审计能力。

## Migration Plan

### Phase 1: 基础设施
1. 引入 Alembic，创建 initial baseline
2. 编写 migration 脚本（新增 5 张表、修改 session_timeline_events）
3. 实现旧数据适配逻辑（RecordingSession → CaptureTake）

### Phase 2: 后端服务
1. 实现 CaptureTake/ CaptureTrack 模型和服务
2. 重构 timeline_event_service（拆分为内部方法 + 外部事务）
3. 实现 CaptureCodingAction 日志模型
4. 实现 LiveCodingState 状态机
5. 实现 CaptureSegment 最小投影
6. 实现 coding-actions API（含事务、幂等、undo）

### Phase 3: 前端
1. 实现 FIFO Outbox
2. 实现 LiveCodingState 乐观 reducer
3. 实现只读多轨时间线
4. 实现局部深色主题
5. 重构 CaptureConsolePage（统一单摄/双摄）

### Phase 4: 集成
1. 单摄录制打点测试
2. 双摄录制打点测试
3. 刷新恢复测试
4. 幂等性测试
5. 误双击抑制测试

### Rollback Strategy
- 新增表不影响现有功能
- coding-actions 有问题可回退到直接事件创建
- 前端可降级到不显示时间线

## Open Questions

所有 Open Questions 已在此版设计中给出明确答案：

1. **CaptureTake 是否软删除**：录制前创建错误可硬删除，已录制只归档（archived_at）
2. **LiveCodingState 快照频率**：每次成功 coding action 在同一事务内更新
3. **双摄初始 offset**：优先根据 started_at 计算；无法测量时 offset_ms=0, offset_source=assumed
4. **赛后 Segment Manager 优先级**：不进入第一版，放入后续 Change
