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

系统 MUST 提供语义级命令 API，后端在一个 SQLite 事务中完成命令日志 + 事件 + 区间 + 状态更新。

#### Scenario: 执行 coding action

- **WHEN** 用户请求 `POST /api/capture-takes/{id}/coding-actions`
- **AND** 请求包含 `action`、`timestamp_ms`、`client_occurred_at`、`client_action_id` 和 `expected_revision`
- **THEN** 系统 SHALL 校验 CaptureTake 状态为 `recording`
- **AND** 系统 SHALL 校验 `expected_revision` 与当前 revision 匹配
- **AND** 系统 SHALL 在一个 `db.begin()` 内完成：
  - 创建 CaptureCodingAction 记录
  - 创建/关闭 SessionTimelineEvent
  - 创建/关闭 CaptureSegment
  - 更新 LiveCodingState
  - 更新 CaptureTake.revision
- **AND** 系统 SHALL 返回新 revision、创建的事件、更新的片段和 LiveCodingState

#### Scenario: revision 冲突返回 409（不同 client_action_id）

- **WHEN** 请求的 `expected_revision` 与当前 revision 不匹配
- **AND** `client_action_id` 是新 ID
- **THEN** 系统 SHALL 返回 409 Conflict
- **AND** 响应 SHALL 包含 `error: "revision_conflict"`、`current_revision` 和 `live_state`
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

系统 MUST 维护 CaptureTake 的实时编码状态快照，每次成功 action 在同一事务内更新。

#### Scenario: 初始状态

- **WHEN** 创建新的 CaptureTake
- **THEN** 系统 SHALL 初始化 LiveCodingState
- **AND** `set_ordinal` SHALL 为 0
- **AND** `game_ordinal` SHALL 为 0
- **AND** `rally_ordinal` SHALL 为 0
- **AND** `non_play` SHALL 为 false

#### Scenario: 每次 action 同步更新

- **WHEN** 执行成功的 coding action
- **THEN** 系统 SHALL 在同一事务中更新 LiveCodingState
- **AND** 系统 SHALL 更新 `revision`、ordinal 和 `updated_at`

#### Scenario: 状态重放恢复

- **WHEN** 状态可能需要从命令日志重建（如一致性检查、测试）
- **THEN** 系统 SHALL 按 revision 顺序重放 CaptureCodingAction
- **AND** 系统 SHALL 恢复到与日志一致的状态

#### Scenario: 获取 LiveCodingState

- **WHEN** 用户请求 `GET /api/capture-takes/{id}/live-state`
- **THEN** 系统 SHALL 返回当前 LiveCodingState
- **AND** 响应 SHALL 包含 `revision`、`set_ordinal`、`game_ordinal`、`rally_ordinal` 和 `non_play`

### Requirement: 完整层级状态转移规则

系统 MUST 根据完整的状态转移表执行层级关闭和打开操作。

#### Scenario: start_set 关闭所有子级

- **WHEN** 执行 `start_set` action
- **THEN** 系统 SHALL 关闭所有 open rally
- **AND** 系统 SHALL 关闭所有 open game
- **AND** 系统 SHALL 关闭上一个 set（如果有）
- **AND** 系统 SHALL 创建新的 open set
- **AND** 系统 SHALL 重置 game_ordinal 和 rally_ordinal 为 0

#### Scenario: start_game 关闭 rally 并创建 inferred set

- **WHEN** 执行 `start_game` action
- **AND** 无 open set
- **THEN** 系统 SHALL 创建 inferred set
- **AND** 系统 SHALL 创建新的 open game
- **AND** 系统 SHALL 重置 rally_ordinal 为 0

#### Scenario: start_next_rally 缺父级时自动创建 inferred 父级

- **WHEN** 执行 `start_next_rally` action
- **AND** 无 open game 和 open set
- **THEN** 系统 SHALL 创建 inferred set
- **AND** 系统 SHALL 创建 inferred game
- **AND** 系统 SHALL 创建新的 open rally

#### Scenario: end_rally no-op

- **WHEN** 执行 `end_rally` action
- **AND** 无 open rally
- **THEN** 系统 SHALL 不报错（no-op）

#### Scenario: end_game 先关闭 rally 再关闭 game

- **WHEN** 执行 `end_game` action
- **AND** 有 open rally
- **THEN** 系统 SHALL 先关闭 open rally
- **AND** 系统 SHALL 再关闭 open game

#### Scenario: end_set 先关闭 rally、game 再关闭 set

- **WHEN** 执行 `end_set` action
- **THEN** 系统 SHALL 先关闭所有 open rally
- **AND** 系统 SHALL 再关闭 open game
- **AND** 系统 SHALL 最后关闭 open set

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
