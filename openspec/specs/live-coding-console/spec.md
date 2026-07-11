## ADDED Requirements

### Requirement: CaptureCodingAction 持久化命令模型

系统 MUST 持久化保存每条 coding action 的完整处理记录，支撑幂等、undo、审计和状态重放。

#### Scenario: 保存命令记录

- **WHEN** 执行 coding action 时
- **THEN** 系统 SHALL 创建 CaptureCodingAction 记录
- **AND** 记录 SHALL 包含 `client_action_id`、`action_type`、`timestamp_ms`、`request_hash`、`status`、`revision_before` 和 `revision_after`
- **AND** `request_hash` SHALL 为 payload + action_type 的哈希，用于检测重放攻击
- **AND** `status` SHALL 初始为 `executed`

#### Scenario: 幂等性 —— 相同 client_action_id

- **WHEN** 请求的 `client_action_id` 已存在于同一 CaptureTake
- **THEN** 系统 SHALL 返回 409 Conflict
- **AND** 响应 SHALL 包含 `error: "duplicate_action"` 和原始执行结果
- **AND** 系统 SHALL 不重复执行

#### Scenario: 幂等性 —— 相同 client_action_id 不同 payload（重放攻击）

- **WHEN** 请求的 `client_action_id` 已存在但 `request_hash` 不匹配
- **THEN** 系统 SHALL 返回 409 Conflict
- **AND** 响应 SHALL 包含 `error: "duplicate_action_mismatched_payload"`
- **AND** 系统 SHALL 不执行

#### Scenario: 审计追踪

- **WHEN** 查询 CaptureTake 的操作历史
- **THEN** 系统 SHALL 返回按 `created_at ASC` 排序的 CaptureCodingAction 列表
- **AND** 列表 SHALL 包含每条动作的完整执行状态

### Requirement: Coding Actions 语义命令 API

系统 MUST 提供语义级命令 API，后端在一个 SQLite 事务中完成命令日志、事件、区间投影和状态更新，并返回当前 CaptureTake 的完整有效投影。

#### Scenario: 执行 coding action

- **WHEN** 用户请求 `POST /api/capture-takes/{id}/coding-actions`
- **AND** 请求包含 `action`、`timestamp_ms`、`client_occurred_at`、`client_action_id` 和 `expected_revision`
- **THEN** 系统 SHALL 校验 CaptureTake 状态为 `recording`
- **AND** 系统 SHALL 校验 `expected_revision` 与当前 revision 匹配
- **AND** 系统 SHALL 在一个事务内完成：
  - 创建 CaptureCodingAction 记录
  - 创建、关闭或标记 SessionTimelineEvent
  - 创建、关闭、归档或重建 CaptureSegment 投影
  - 更新 LiveCodingState
  - 更新 CaptureTake.revision
- **AND** 响应 SHALL 返回新 revision、`timeline_events`、`segments` 和 LiveCodingState 的完整有效快照

#### Scenario: revision 冲突返回 409（不同 client_action_id）

- **WHEN** 请求的 `expected_revision` 与当前 revision 不匹配
- **AND** `client_action_id` 是新 ID
- **THEN** 系统 SHALL 返回 409 Conflict
- **AND** 响应 SHALL 包含 `error: "revision_conflict"`、`current_revision` 和权威 LiveCodingState
- **AND** 系统 SHALL 不自动重新执行该动作

#### Scenario: 时间戳校验

- **WHEN** 请求的 `timestamp_ms` 与 CaptureTake 已录制时长相比较
- **AND** 偏差超过 ±5 秒
- **THEN** 系统 SHALL 返回 400 错误
- **AND** 系统 SHALL 不执行该动作

#### Scenario: 使用服务器时间兜底

- **WHEN** 请求未提交 `timestamp_ms`
- **THEN** 系统 SHALL 使用 `当前服务器时间 - CaptureTake.started_at` 计算 `timestamp_ms`

### Requirement: LiveCodingState 快照管理

系统 MUST 维护 CaptureTake 的实时编码状态快照，每次成功 action 在同一事务内更新，并显式表达比赛阶段和间歇原因。

#### Scenario: 初始状态

- **WHEN** 创建新的 CaptureTake
- **THEN** 系统 SHALL 初始化 LiveCodingState
- **AND** `set_ordinal`、`game_ordinal` 和 `rally_ordinal` SHALL 为 0
- **AND** `match_phase` SHALL 为 `idle`
- **AND** `intermission_kind` SHALL 为空
- **AND** 为兼容现有客户端，`non_play` SHALL 为 false

#### Scenario: 每次 action 同步更新

- **WHEN** 执行成功的 coding action
- **THEN** 系统 SHALL 在同一事务中更新 LiveCodingState
- **AND** 系统 SHALL 更新 revision、ordinal、`match_phase`、`intermission_kind` 和 `updated_at`
- **AND** `non_play` SHALL 在 `match_phase` 为 `intermission` 时为 true，否则为 false

#### Scenario: 状态重放恢复

- **WHEN** 状态需要从命令日志重建（如 undo、一致性检查或测试）
- **THEN** 系统 SHALL 按执行顺序重放未标记为 `undone` 的 CaptureCodingAction
- **AND** 系统 SHALL 恢复到与有效事件和有效区间一致的状态

#### Scenario: 获取 LiveCodingState

- **WHEN** 用户请求 `GET /api/capture-takes/{id}/live-state`
- **THEN** 系统 SHALL 返回当前 LiveCodingState
- **AND** 响应 SHALL 包含 revision、ordinal、`match_phase`、`intermission_kind` 和 `non_play`

### Requirement: 完整层级状态转移规则

系统 MUST 根据完整的状态转移表执行层级关闭、开分和间歇操作。

#### Scenario: start_set 关闭所有子级和间歇

- **WHEN** 执行 `start_set` action
- **THEN** 系统 SHALL 关闭所有 open rally
- **AND** 系统 SHALL 关闭所有 open game
- **AND** 系统 SHALL 关闭上一个 set（如果有）
- **AND** 系统 SHALL 关闭当前开启的间歇（如果有）
- **AND** 系统 SHALL 创建新的 open set
- **AND** 系统 SHALL 重置 game_ordinal 和 rally_ordinal 为 0
- **AND** 系统 SHALL 将 `match_phase` 设为 `idle`

#### Scenario: start_game 关闭当前分并创建 inferred set

- **WHEN** 执行 `start_game` action
- **AND** 无 open set
- **THEN** 系统 SHALL 创建 inferred set
- **AND** 系统 SHALL 关闭 open rally 和当前间歇（如果有）
- **AND** 系统 SHALL 创建新的 open game
- **AND** 系统 SHALL 重置 rally_ordinal 为 0
- **AND** 系统 SHALL 将 `match_phase` 设为 `idle`

#### Scenario: start_next_rally 缺父级时自动创建 inferred 父级

- **WHEN** `match_phase` 为 `idle` 或 `intermission`
- **AND** 执行 `start_next_rally` action
- **AND** 无 open game 和 open set
- **THEN** 系统 SHALL 创建 inferred set
- **AND** 系统 SHALL 创建 inferred game
- **AND** 系统 SHALL 关闭当前间歇（如果有）
- **AND** 系统 SHALL 创建新的 open rally
- **AND** 系统 SHALL 增加 rally_ordinal
- **AND** 系统 SHALL 将 `match_phase` 设为 `rally_active`

#### Scenario: start_next_rally 不隐式结束当前分

- **WHEN** `match_phase` 为 `rally_active`
- **AND** 执行 `start_next_rally` action
- **THEN** 系统 SHALL 拒绝该动作
- **AND** 系统 SHALL 不关闭当前 rally
- **AND** 系统 SHALL 不增加 rally_ordinal

#### Scenario: end_rally 开启赛间间歇

- **WHEN** `match_phase` 为 `rally_active`
- **AND** 执行 `end_rally` action
- **THEN** 系统 SHALL 关闭 open rally 并创建 `rally_end` 事件
- **AND** 系统 SHALL 创建 `intermission_kind` 为 `between_rallies` 的 `non_play_start` 事件
- **AND** 系统 SHALL 将 `match_phase` 设为 `intermission`

#### Scenario: end_rally 无当前分时 no-op

- **WHEN** 执行 `end_rally` action
- **AND** 无 open rally
- **THEN** 系统 SHALL 不报错（no-op）
- **AND** 系统 SHALL 不创建新的间歇事件或 CaptureSegment

#### Scenario: start_timeout 原子进入暂停间歇

- **WHEN** 执行 `start_timeout` action
- **THEN** 系统 SHALL 关闭 open rally（如果有）
- **AND** 系统 SHALL 关闭当前间歇（如果有）
- **AND** 系统 SHALL 创建 `intermission_kind` 为 `timeout` 的 `non_play_start` 事件
- **AND** 系统 SHALL 将 `match_phase` 设为 `intermission`

#### Scenario: change_side 原子结束当前分并进入换边间歇

- **WHEN** 执行 `change_side` action
- **THEN** 系统 SHALL 创建 `side_change` 瞬时事件
- **AND** 系统 SHALL 关闭 open rally（如果有）
- **AND** 系统 SHALL 关闭当前间歇（如果有）
- **AND** 系统 SHALL 创建 `intermission_kind` 为 `side_change` 的 `non_play_start` 事件
- **AND** 系统 SHALL 将 `match_phase` 设为 `intermission`

#### Scenario: end_game 先关闭分、间歇再关闭局

- **WHEN** 执行 `end_game` action
- **THEN** 系统 SHALL 先关闭 open rally
- **AND** 系统 SHALL 关闭当前间歇（如果有）
- **AND** 系统 SHALL 再关闭 open game
- **AND** 系统 SHALL 将 `match_phase` 设为 `idle`

#### Scenario: end_set 先关闭分、局、间歇再关闭盘

- **WHEN** 执行 `end_set` action
- **THEN** 系统 SHALL 先关闭所有 open rally
- **AND** 系统 SHALL 关闭当前间歇和 open game
- **AND** 系统 SHALL 最后关闭 open set
- **AND** 系统 SHALL 将 `match_phase` 设为 `idle`

#### Scenario: toggle_non_play 开启关闭 rally 但保留 set/game

- **WHEN** 执行 `toggle_non_play` action
- **AND** 当前 non_play 为 false
- **THEN** 系统 SHALL 关闭 open rally
- **AND** 系统 SHALL 保留 open set 和 game
- **AND** 系统 SHALL 创建 non_play_start 事件

#### Scenario: toggle_non_play 结束不创建 rally

- **WHEN** 执行 `toggle_non_play` action
- **AND** 当前 non_play 为 true
- **THEN** 系统 SHALL 创建 non_play_end 事件
- **AND** 系统 SHALL 不自动创建新的 rally

#### Scenario: change_side 不改变层级

- **WHEN** 执行 `change_side` action
- **THEN** 系统 SHALL 创建 side_change 点事件
- **AND** 系统 SHALL 不改变任何区间状态

### Requirement: 一键推进操作

系统 MUST 支持"下一分"一键推进操作。

#### Scenario: 第一次点击开始第一分

- **WHEN** 当前没有 open rally
- **AND** 执行 `start_next_rally` action
- **THEN** 系统 SHALL 创建 `rally_start` 事件
- **AND** 系统 SHALL 设置 `rally_ordinal` 为 1
- **AND** 系统 SHALL 创建 CaptureSegment

#### Scenario: 后续点击关闭当前分并开始下一分

- **WHEN** 当前有 open rally
- **AND** 执行 `start_next_rally` action
- **THEN** 系统 SHALL 关闭当前 rally（创建 `rally_end` 事件）
- **AND** 系统 SHALL 创建 `rally_start` 事件
- **AND** 系统 SHALL 增加 `rally_ordinal`

### Requirement: 撤销操作

系统 MUST 支持 undo 操作，不删除数据库行。

#### Scenario: 撤销上一个 action

- **WHEN** 执行 `undo` action
- **THEN** 系统 SHALL 找到最后一个可撤销且未被撤销的 CaptureCodingAction
- **AND** 系统 SHALL 创建新的 undo CaptureCodingAction，`reverses_action_id` 指向被撤销的 action
- **AND** 系统 SHALL 为被撤销的事件设置 `is_undone=true`（或创建 corrected 事件）
- **AND** 系统 SHALL 重建受影响的 CaptureSegment 和 LiveCodingState
- **AND** 系统 SHALL 增加 revision

#### Scenario: 无法撤销时返回错误

- **WHEN** 没有可撤销的动作
- **OR** 唯一可撤销的动作类型为录制开始/停止
- **THEN** 系统 SHALL 返回 400 错误
- **AND** 错误信息 SHALL 说明无法撤销的原因

#### Scenario: 不能跨 CaptureTake 撤销

- **WHEN** 请求 undo 的 CaptureTake 与目标 action 的 CaptureTake 不匹配
- **THEN** 系统 SHALL 返回 400 错误

### Requirement: 前端 FIFO 发送队列

系统 MUST 为每个 CaptureTake 维护单路 FIFO 发送队列。

#### Scenario: 顺序发送

- **WHEN** 用户连续执行多个 coding action
- **THEN** 前端 SHALL 将 action 按顺序加入 FIFO 队列
- **AND** 前端 SHALL 同一时间最多发送一个 inflight action
- **AND** 前一个确认后，前端 SHALL 使用服务器返回的最新 revision 发送下一个

#### Scenario: 误双击抑制

- **WHEN** 用户在 400ms 内对同一按钮点击两次
- **THEN** 前端 SHALL 忽略第二次点击（debounce）

#### Scenario: 队列失败阻塞后续

- **WHEN** 队列中某个 action 发送失败（非 409）
- **THEN** 前端 SHALL 暂停后续所有动作
- **AND** 前端 SHALL 将失败 action 和后续等待动作的状态展示给用户

### Requirement: FIFO Outbox 持久化

系统 MUST 在 IndexedDB 中持久化事件 Outbox。

#### Scenario: action 加入 Outbox

- **WHEN** 执行 coding action
- **THEN** 前端 SHALL 将 action 存入 IndexedDB Outbox
- **AND** 记录 SHALL 包含 `sequenceNumber`、`timestampMs`、`clientOccurredAt`
- **AND** 状态 SHALL 为 `pending`

#### Scenario: 同步成功更新状态

- **WHEN** 后端确认 action 执行成功
- **THEN** 前端 SHALL 更新 Outbox 中记录状态为 `synced`

#### Scenario: 同步失败指数退避重试

- **WHEN** action 发送失败
- **THEN** 前端 SHALL 使用指数退避重试（1s → 2s → 4s → 8s）
- **AND** 最大重试次数 SHALL 为 5
- **AND** 重试时 SHALL 保留原始 `timestampMs`，不更新为重试时时间

#### Scenario: 刷新后恢复 Outbox

- **WHEN** 页面刷新后重新加载
- **THEN** 前端 SHALL 从 IndexedDB 读取未完成的 Outbox 记录
- **AND** 前端 SHALL 按 `sequenceNumber` 顺序重新发送

#### Scenario: 最终失败显示给用户

- **WHEN** 重试次数超过最大限制
- **THEN** 前端 SHALL 将 action 状态设置为 `failed`
- **AND** UI SHALL 显示失败状态
- **AND** 后续 pending action 保持 `blocked`

### Requirement: 键盘快捷键

系统 MUST 支持键盘快捷键操作。

#### Scenario: 快捷键映射

- **WHEN** 录制中且焦点不在 input/textarea/select，且无弹窗
- **THEN** 系统 SHALL 响应以下快捷键：
  - `1` → 开始新盘
  - `2` → 开始新局
  - `3` → 下一分
  - `4` → 非比赛开始/结束
  - `5` → 换边
  - `6` → 暂停开始/结束
  - `H` → 重点片段
  - `Backspace` → 撤销

#### Scenario: 快捷键不响应

- **WHEN** 焦点在 input/textarea/select 或打开弹窗
- **THEN** 系统 SHALL 不响应快捷键

### Requirement: 前端乐观更新

系统 MUST 在前端实现乐观更新机制。

#### Scenario: 乐观显示新状态

- **WHEN** 用户执行 coding action
- **THEN** 前端 SHALL 立即乐观显示新状态
- **AND** 前端 SHALL 将 action 加入 FIFO 队列等待发送

#### Scenario: 后端确认后更新

- **WHEN** 收到后端成功响应
- **THEN** 前端 SHALL 以后端返回的状态为准
- **AND** 前端 SHALL 更新本地 LiveCodingState 副本

#### Scenario: 后端拒绝后回滚

- **WHEN** 收到后端 409 Conflict 响应（revision 冲突）
- **THEN** 前端 SHALL 回滚到上一个确认状态
- **AND** 前端 SHALL 显示冲突提示
- **AND** 前端 SHALL 不自动重试

### Requirement: Outbox Sender 生命周期管理

系统 MUST 在开始录制时初始化 Outbox Sender，在录制结束和组件卸载时清理。

#### Scenario: 单摄开始录制时初始化

- **WHEN** 单摄开始录制并获取到 `capture_take_id`
- **THEN** 系统 SHALL 调用 `getLiveCodingState()` 获取初始状态
- **AND** 系统 SHALL 使用 `useRef` 保存 revision 和 liveCodingState 的权威副本
- **AND** 系统 SHALL 调用 `createOutboxSender()` 初始化 sender
- **AND** sender SHALL 绑定到当前 `capture_take_id`
- **AND** sender SHALL 从 ref 读取当前 revision 作为 `expected_revision`
- **AND** 系统 SHALL 立即执行 `flush()` 发送积压的 pending 项

#### Scenario: 双摄开始录制时初始化

- **WHEN** 双摄同步录制开始且 `SyncRecordingSession` 包含 `capture_take_id`
- **THEN** 系统 SHALL 执行与单摄相同的初始化流程
- **AND** 系统 SHALL 调用同一 `initializeLiveCoding()` 函数

#### Scenario: 双摄无 capture_take_id 时静默降级

- **WHEN** 双摄同步录制开始且 `capture_take_id` 为空
- **THEN** 系统 SHALL 跳过 live coding 初始化
- **AND** 系统 SHALL 不展示实时编码 UI

#### Scenario: 录制停止时清理

- **WHEN** 单摄或双摄停止录制
- **THEN** 系统 SHALL 调用 `outboxSender.stop()`
- **AND** 系统 SHALL 将 `outboxSenderRef.current` 置为 null

#### Scenario: 组件卸载时清理

- **WHEN** CaptureConsolePage 组件卸载
- **THEN** 系统 SHALL 调用 `outboxSender.stop()`
- **AND** 系统 SHALL 清理计时器和定时轮询

#### Scenario: 开始新录制前清理旧 sender

- **WHEN** 在已有 sender 的情况下开始新录制
- **THEN** 系统 SHALL 先 stop 旧 sender
- **AND** 系统 SHALL 再创建新 sender

### Requirement: Coding Action 响应回写

系统 MUST 在收到 `executeCodingAction` 成功响应后将后端结果合并回前端状态。

#### Scenario: 成功后更新 revision 和 LiveCodingState

- **WHEN** sender 收到 `CodingActionResponse`
- **THEN** 系统 SHALL 以顶层 `response.revision` 更新 `revisionRef`
- **AND** 系统 SHALL 以 `response.live_state` 更新 `liveCodingStateRef` 和 `liveCodingState`
- **AND** `response.live_state.revision` 若与顶层不一致，以顶层为准

#### Scenario: 成功后合并 TimelineEvent

- **WHEN** 响应包含 `created_events`
- **THEN** 系统 SHALL 将每个事件按 `id` 合并到 `timelineEvents`
- **AND** `id` 已存在时替换，不存在时追加

#### Scenario: 成功后合并 CaptureSegment

- **WHEN** 响应包含 `updated_segments`
- **THEN** 系统 SHALL 将每个段按 `id` 合并到 `segments`
- **AND** `id` 已存在时替换，不存在时追加

#### Scenario: 幂等响应容忍

- **WHEN** 响应包含 `duplicate: true`
- **AND** `created_events` 或 `updated_segments` 为空
- **THEN** 系统 SHALL 不因字段缺失报错
- **AND** 系统 SHALL 仍更新 revision 和 liveCodingState

### Requirement: Revision 权威值管理

系统 MUST 使用 `useRef` 而非 React 闭包维护 revision 权威值。

#### Scenario: 使用 ref 避免陈旧闭包

- **WHEN** sender 在录制开始时创建
- **THEN** 获取 revision 的回调 SHALL 读取 `revisionRef.current`
- **AND** 不 SHALL 不通过 `liveCodingState` 闭包获取

#### Scenario: 每次响应后更新 ref

- **WHEN** 收到成功响应
- **THEN** 系统 SHALL 立即将 `revisionRef.current` 设为 `response.revision`
- **AND** 后续 flush 的 `expected_revision` SHALL 使用新值

#### Scenario: 初始 revision 来源

- **WHEN** `getLiveCodingState()` 返回初始状态
- **THEN** `revisionRef.current` SHALL 初始化为 `state.revision`
- **AND** `liveCodingStateRef.current` SHALL 初始化为 state

### Requirement: MiniTimeline 开放 Segment 实时绘制

系统 MUST 在 MiniTimeline 中将开放 segment 的右边界对齐当前录制时间。

#### Scenario: 无 end_ms 的 segment 跟随录制进度

- **WHEN** segment 的 `end_ms` 为 null 或 undefined
- **THEN** 色条右边界 SHALL 为 `Math.max(elapsedMs, seg.start_ms)`
- **AND** 色条 SHALL 随 `elapsedMs` 增长而实时向右延伸

#### Scenario: 已关闭 segment 固定宽度

- **WHEN** segment 的 `end_ms` 非 null
- **THEN** 色条右边界 SHALL 使用 `end_ms`
- **AND** 色条不随录制进度变化

### Requirement: MiniTimeline 移除倒三角事件标记

系统 MUST 移除 MiniTimeline 底部的倒三角 SVG 事件标记行。

#### Scenario: 不渲染事件标记行

- **WHEN** MiniTimeline 渲染时
- **THEN** 不 SHALL 不显示倒三角事件标记轨道
- **AND** 不 SHALL 不筛选 `side_change`、`non_play_start`、`session_note` 事件作为标记

### Requirement: MiniTimeline 瞬时事件可视化

系统 MUST 用细竖线和图标替代倒三角标记瞬时事件。

#### Scenario: 换边事件显示紫色竖线

- **WHEN** `side_change` 事件出现在时间线上
- **THEN** 系统 SHALL 在对应时间戳位置渲染 1px 紫色竖线
- **AND** 竖线顶部 SHALL 带 4px 菱形标记
- **AND** 颜色 SHALL 为 `#A855F7`

#### Scenario: 重点标记事件显示黄色星形

- **WHEN** `add_note` 或 `session_note` 事件且 `highlight: true`
- **THEN** 系统 SHALL 在对应时间戳位置渲染 8px 星形图标
- **AND** 颜色 SHALL 为 `#F59E0B`

#### Scenario: 竖线和图标叠加在色条轨道上方

- **WHEN** 渲染瞬时事件
- **THEN** 竖线和图标 SHALL 叠加在最上层
- **AND** 高度 SHALL 不超过 16px
- **AND** 不 SHALL 不占用独立轨道行

### Requirement: MiniTimeline 非比赛覆盖

系统 MUST 在非比赛时段用灰色半透明覆盖层标记。

#### Scenario: 非比赛时段覆盖

- **WHEN** 存在 `non_play_start` 事件到对应 `non_play_end` 事件之间的时段
- **THEN** 系统 SHALL 在三轨道上叠加灰色半透明遮罩
- **AND** 遮罩颜色 SHALL 为 `#9CA3AF`，透明度 20%

#### Scenario: 录制中非比赛覆盖增长

- **WHEN** `non_play` 为 true 且尚未 `non_play_end`
- **THEN** 灰色覆盖层 SHALL 从 non_play_start 时间戳延伸到当前 elapsedMs
- **AND** 覆盖层随录制进度增长

### Requirement: MiniTimeline 录制中始终显示三轨

系统 MUST 在录制中即使 segments 为空也显示空轨道。

#### Scenario: 空轨道预留空间

- **WHEN** 录制中且 segments 数组为空
- **THEN** 三条轨道 SHALL 以空白背景色渲染
- **AND** 轨道高度 SHALL 为 26px
- **AND** 轨道标签（盘/局/分）SHALL 正常显示
- **AND** 录制进行中不显示"录制中·持续扩展"文字

### Requirement: 轮询数据合并

系统 MUST 将轮询获取的 segments 和 events 与本地状态按 ID 合并，而非全量替换。

#### Scenario: 轮询合并 segments

- **WHEN** `loadSegmentsData()` 从服务端获取最新 segments
- **THEN** 系统 SHALL 按 `id` 合并到当前 `segments` 状态
- **AND** 服务端返回中存在且本地也存在的项 SHALL 以服务端版本为准
- **AND** 服务端返回中不存在的本地项 SHALL 保留

#### Scenario: 轮询合并 events

- **WHEN** `loadTimelineEvents()` 从服务端获取最新 events
- **THEN** 系统 SHALL 按 `id` 合并到当前 `timelineEvents` 状态

### Requirement: 后端 revision 一致性

系统 MUST 保证 coding action 响应中顶层 revision 与 live_state.revision 一致。

#### Scenario: 同步写入 revision

- **WHEN** 后端执行 coding action 后
- **THEN** `CaptureTake.revision` 和 `LiveCodingState.revision` SHALL 使用同一个新值
- **AND** 响应中 `revision === response.live_state.revision`

### Requirement: 后端幂等响应完整性

系统 MUST 在幂等分支返回完整的响应字段。

#### Scenario: 重复 client_action_id 返回完整字段

- **WHEN** 后端命中相同 `client_action_id` 的幂等分支
- **THEN** 响应 SHALL 包含 `revision`、`created_events`（空数组）、`updated_segments`（空数组）、`live_state`、`duplicate: true`
- **AND** 不 SHALL 不因缺少 `created_events` 或 `updated_segments` 导致前端校验失败

### Requirement: Outbox Sender drain 排空

系统 MUST 在停止录制前排空 outbox，确保所有 pending action 完成或明确失败。

#### Scenario: 停止录制前 drain

- **WHEN** 用户触发停止录制
- **THEN** 系统 SHALL 先调用 `sender.drain()` 等待当前 inflight 请求完成
- **AND** 系统 SHALL 继续处理队列中剩余的 pending item
- **AND** 所有 item 状态变为 `synced` 或 `failed`/`blocked` 后 `drain()` 返回
- **AND** 系统 SHALL 再调用 `stopRecording()` API

#### Scenario: drain 失败时提示用户

- **WHEN** `drain()` 完成后仍有 `failed` 或 `blocked` 的 item
- **THEN** 系统 SHALL 显示确认弹窗，提示未同步事件数量
- **AND** 弹窗 SHALL 提供"仍然停止"和"取消停止"选项
- **AND** 用户确认后系统 SHALL 继续停止录制

#### Scenario: drain 超时保护

- **WHEN** drain 执行超过 10 秒
- **THEN** 系统 SHALL 超时返回当前未同步状态
- **AND** 系统 SHALL 仍显示确认弹窗

### Requirement: Outbox Sender drain() 接口

系统 MUST 在 `OutboxSender` 接口上提供 `drain()` 方法。

#### Scenario: drain 定义

- **WHEN** 调用 `sender.drain()`
- **THEN** 方法 SHALL 返回 Promise<void>
- **AND** 方法 SHALL 设置 `_draining = true`
- **AND** 方法 SHALL 调用 `flush()` 处理完当前 inflight 及剩余 pending 项
- **AND** drain 期间外部 `flush()` 调用 SHALL 不再启动新发送

### Requirement: sequenceNumber 刷新恢复

系统 MUST 保证页面刷新后 coding action 的 FIFO 顺序不被打乱。

#### Scenario: 刷新后序号不归零

- **WHEN** 页面刷新后创建新的 coding action
- **THEN** 系统 SHALL 读取 localStorage 中同一 `captureTakeId` 的最大 `sequenceNumber`
- **AND** 新 action 的 `sequenceNumber` SHALL 为 `maxSequence + 1`
- **AND** 不 SHALL 不使用模块内计数器

#### Scenario: 排序稳定

- **WHEN** 同时存在旧 pending action 和新 action
- **THEN** 排序 SHALL 按 `sequenceNumber` + `createdAt` 升序排列
- **AND** 新 action 的 `sequenceNumber` SHALL 大于所有旧 pending action

### Requirement: 409 revision_conflict 安全处理

系统 MUST 区分幂等 409 和真正的 revision conflict，不自动重放冲突动作。

#### Scenario: 错误类型区分

- **WHEN** sender 收到 409 响应
- **AND** 响应包含 `error: "duplicate_action"`
- **THEN** 系统 SHALL 视为幂等成功，将 item 标记为 `synced`
- **AND** 系统 SHALL 继续正常处理后续队列

- **WHEN** sender 收到 409 响应
- **AND** 响应包含 `error: "revision_conflict"`
- **THEN** 系统 SHALL 将冲突 item 标记为 `blocked`
- **AND** 系统 SHALL 将后续所有 pending item 标记为 `blocked`
- **AND** 系统 SHALL 更新本地 liveCodingState 为服务端返回的当前状态
- **AND** 系统 SHALL 不自动重新执行该动作

#### Scenario: 用户确认重试

- **WHEN** revision conflict 阻塞队列
- **THEN** 系统 SHALL 显示提示信息
- **AND** 提示 SHALL 说明动作未执行的原因
- **AND** 提示 SHALL 提供"放弃此操作"和"确认重新执行"选项
- **AND** 用户确认后系统 SHALL 将 blocked 项重新标记为 pending 并 flush

### Requirement: TimelineEvent 按 CaptureTake 隔离

系统 MUST 保证 MiniTimeline 只显示当前 CaptureTake 的事件。

#### Scenario: 查询参数过滤

- **WHEN** 请求 TimelineEvent 列表
- **THEN** 前端 SHALL 传入当前 `captureTakeId` 作为筛选参数
- **AND** API 查询 SHALL 增加 `capture_take_id` 过滤

#### Scenario: 切换 Take 时清空旧数据

- **WHEN** 开始新的录制（新的 CaptureTake）
- **THEN** 系统 SHALL 清空 `timelineEvents` 和 `segments`
- **AND** 系统 SHALL 重置 `liveCodingState`

#### Scenario: 第一个 Take 的事件不影响第二个 Take

- **WHEN** 在同一 Field Session 中连续录制两个 Take
- **THEN** 第二个 Take 的 MiniTimeline SHALL 不显示第一个 Take 的事件和段

### Requirement: 非比赛区间推导

系统 MUST 从事件序列推导非比赛时间区间，而非仅依赖 liveCodingState 的 boolean 值。

#### Scenario: 标准起止

- **WHEN** 存在 `non_play_start` 事件及其后的 `non_play_end` 事件
- **THEN** 系统 SHALL 生成 `TimelineRange { startMs, endMs }`
- **AND** 区间 SHALL 以 `startMs` 为 `non_play_start.timestamp_ms`
- **AND** 区间 SHALL 以 `endMs` 为 `non_play_end.timestamp_ms`

#### Scenario: 录制中未关闭

- **WHEN** 存在 `non_play_start` 但无对应的 `non_play_end`
- **AND** 当前正在录制
- **THEN** 区间 `endMs` SHALL 为当前 `elapsedMs`

#### Scenario: 异常事件序列容忍

- **WHEN** 存在连续两个 `non_play_start` 无中间 `non_play_end`
- **THEN** 系统 SHALL 忽略第二个 `non_play_start` 并记录诊断警告

- **WHEN** 存在孤立的 `non_play_end`（无对应 start）
- **THEN** 系统 SHALL 忽略该事件并记录诊断警告
