## MODIFIED Requirements

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
- **THEN** 系统 SHALL 关闭所有 open rally、open game 和上一个 set（如果有）
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
- **THEN** 系统 SHALL 创建 inferred set 和 inferred game
- **AND** 系统 SHALL 关闭当前间歇（如果有）
- **AND** 系统 SHALL 创建新的 open rally 并增加 rally_ordinal
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
- **WHEN** 不存在 open rally
- **AND** 执行 `end_rally` action
- **THEN** 系统 SHALL 不报错
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
- **THEN** 系统 SHALL 关闭 open rally 和当前间歇（如果有）
- **AND** 系统 SHALL 再关闭 open game
- **AND** 系统 SHALL 将 `match_phase` 设为 `idle`

#### Scenario: end_set 先关闭分、局、间歇再关闭盘
- **WHEN** 执行 `end_set` action
- **THEN** 系统 SHALL 关闭 open rally、当前间歇和 open game
- **AND** 系统 SHALL 最后关闭 open set
- **AND** 系统 SHALL 将 `match_phase` 设为 `idle`

### Requirement: 一键推进操作

系统 MUST 支持只开始新分的 `start_next_rally` 操作，不得将结束当前分与开始下一分合并为一个用户动作。

#### Scenario: 第一次点击开始第一分
- **WHEN** 当前没有 open rally
- **AND** 执行 `start_next_rally` action
- **THEN** 系统 SHALL 创建 `rally_start` 事件
- **AND** 系统 SHALL 设置 rally_ordinal 为 1
- **AND** 系统 SHALL 创建 CaptureSegment

#### Scenario: 间歇后开始下一分
- **WHEN** 当前存在开启的赛间、暂停或换边间歇
- **AND** 执行 `start_next_rally` action
- **THEN** 系统 SHALL 先创建对应原因的 `non_play_end` 事件
- **AND** 系统 SHALL 再创建下一分的 `rally_start` 事件
- **AND** 系统 SHALL 增加 rally_ordinal

### Requirement: 撤销操作

系统 MUST 支持 undo 操作，不删除审计数据，并将事件、区间与状态恢复为撤销目标之前的完整有效投影。

#### Scenario: 撤销上一个 action
- **WHEN** 执行 `undo` action
- **THEN** 系统 SHALL 找到最后一个可撤销且未被撤销的 CaptureCodingAction
- **AND** 系统 SHALL 创建新的 undo CaptureCodingAction，`reverses_action_id` 指向被撤销的 action
- **AND** 系统 SHALL 将目标 action 直接创建的 TimelineEvent 标记 `is_undone=true`
- **AND** 系统 SHALL 使目标 action 创建或修改的 CaptureSegment 退出有效投影
- **AND** 系统 SHALL 重放剩余有效 action 以重建 CaptureSegment 和 LiveCodingState
- **AND** 系统 SHALL 增加 revision 并返回完整有效投影

#### Scenario: 撤销开始新分后再次开始相同序号
- **WHEN** 用户开始第 N 分、撤销该动作、再执行 `start_next_rally`
- **THEN** 完整有效投影 SHALL 只包含一个 ordinal 为 N 的 rally Segment
- **AND** 时间线 SHALL 不包含被撤销动作产生的 rally 色条或事件

#### Scenario: 无法撤销时返回错误
- **WHEN** 没有可撤销的动作
- **THEN** 系统 SHALL 返回 400 错误
- **AND** 错误信息 SHALL 说明无法撤销的原因

#### Scenario: 不能跨 CaptureTake 撤销
- **WHEN** 请求 undo 的 CaptureTake 与目标 action 的 CaptureTake 不匹配
- **THEN** 系统 SHALL 返回 400 错误

### Requirement: 键盘快捷键

系统 MUST 支持与比赛控制台按钮一致的键盘快捷键操作。

#### Scenario: 快捷键映射
- **WHEN** 录制中且焦点不在 input/textarea/select，且无弹窗
- **THEN** 系统 SHALL 响应以下快捷键：
  - `1` → 开始新盘
  - `2` → 开始新局
  - `3` → 开始下一分
  - `4` → 结束当前分
  - `5` → 换边
  - `6` → 战术暂停
  - `H` → 重点片段
  - `Backspace` → 撤销

#### Scenario: 快捷键不响应
- **WHEN** 焦点在 input/textarea/select 或打开弹窗
- **THEN** 系统 SHALL 不响应快捷键

### Requirement: 前端乐观更新

系统 MUST 在前端即时反映 action 的提交状态，但不得在未收到服务端确认前伪造 ordinal、事件或 CaptureSegment。

#### Scenario: 乐观显示提交状态
- **WHEN** 用户执行 coding action
- **THEN** 前端 SHALL 立即将动作加入 FIFO 队列
- **AND** 前端 SHALL 将受影响按钮展示为 pending 或禁用状态
- **AND** 前端 SHALL 不自行增加或减少盘、局、分 ordinal

#### Scenario: 后端确认后替换权威投影
- **WHEN** 收到后端成功响应
- **THEN** 前端 SHALL 以后端返回的 revision、LiveCodingState、`timeline_events` 和 `segments` 为准
- **AND** 前端 SHALL 整体替换当前 CaptureTake 的事件和区间状态

#### Scenario: 后端拒绝后回滚
- **WHEN** 收到后端 409 Conflict 响应（revision 冲突）
- **THEN** 前端 SHALL 取消对应 pending 状态
- **AND** 前端 SHALL 回滚到服务端返回的权威状态
- **AND** 前端 SHALL 显示冲突提示且不自动重试

### Requirement: Coding Action 响应回写

系统 MUST 在收到 `executeCodingAction` 成功响应后以完整权威投影同步当前 Take 的前端状态。

#### Scenario: 成功后更新 revision 和 LiveCodingState
- **WHEN** sender 收到 CodingActionResponse
- **THEN** 系统 SHALL 以顶层 `response.revision` 更新 `revisionRef`
- **AND** 系统 SHALL 以 `response.live_state` 更新 `liveCodingStateRef` 和 `liveCodingState`
- **AND** `response.live_state.revision` 若与顶层不一致，以顶层为准

#### Scenario: 成功后替换 TimelineEvent 和 CaptureSegment
- **WHEN** 响应包含完整 `timeline_events` 和 `segments`
- **THEN** 系统 SHALL 使用响应数组整体替换当前 Take 的 `timelineEvents` 和 `segments`
- **AND** 服务端未返回的本地 ID SHALL 被移除

#### Scenario: 幂等响应容忍
- **WHEN** 响应包含 `duplicate: true`
- **THEN** 系统 SHALL 不因重复 action 报错
- **AND** 系统 SHALL 仍以响应的权威 revision、LiveCodingState 和完整投影同步前端

### Requirement: MiniTimeline 平滑滚动视口

系统 MUST 在实时录制中以固定时宽窗口平滑推进 MiniTimeline，且历史区间的显示长度不得因录制总时长增长而重新缩放。

#### Scenario: 录制未超过视口长度
- **WHEN** 当前 elapsedMs 小于或等于 90 秒
- **THEN** 时间线 SHALL 从 0 展示至固定的 90 秒可视窗口
- **AND** 段、间歇遮罩和游标 SHALL 使用稳定的时间到像素映射

#### Scenario: 录制超过视口长度
- **WHEN** 当前 elapsedMs 大于 90 秒
- **THEN** 时间线 SHALL 展示截至当前时间的最近 90 秒
- **AND** 窗口起点 SHALL 连续向前移动
- **AND** 已显示段的像素宽度 SHALL 不因窗口推进而改变

#### Scenario: 连续推进游标和开放区间
- **WHEN** 录制进行中
- **THEN** MiniTimeline SHALL 使用连续时钟推进游标和开放段的右边界
- **AND** 系统 SHALL 不以秒级 React state 的离散更新作为时间线布局时钟

### Requirement: MiniTimeline 非比赛覆盖

系统 MUST 依据间歇事件及其原因在三条轨道上呈现可区分的间歇覆盖层。

#### Scenario: 赛间间歇覆盖
- **WHEN** 存在 `intermission_kind` 为 `between_rallies` 的间歇区间
- **THEN** 系统 SHALL 在三轨道上叠加 `#9CA3AF`、20% 透明度的灰色覆盖层

#### Scenario: 战术暂停覆盖
- **WHEN** 存在 `intermission_kind` 为 `timeout` 的间歇区间
- **THEN** 系统 SHALL 在三轨道上叠加与赛间间歇可区分的深灰条纹覆盖层

#### Scenario: 换边间歇覆盖和标记
- **WHEN** 存在 `intermission_kind` 为 `side_change` 的间歇区间及 `side_change` 事件
- **THEN** 系统 SHALL 使用带紫色边界的浅紫覆盖层表示该间歇
- **AND** 系统 SHALL 在 `side_change` 的时间戳位置渲染紫色竖线和菱形标记

#### Scenario: 未关闭间歇持续增长
- **WHEN** 间歇开始事件没有对应结束事件且当前正在录制
- **THEN** 覆盖层 SHALL 从开始时间延伸到连续 elapsedMs
- **AND** 覆盖层 SHALL 随时间平滑增长

### Requirement: 轮询数据合并

系统 MUST 将当前 CaptureTake 的服务端有效快照作为轮询结果的权威来源，不得保留快照中不存在的本地事件或区间。

#### Scenario: 轮询替换 segments
- **WHEN** `loadSegmentsData()` 从服务端获取当前 Take 的完整有效 segments
- **THEN** 前端 SHALL 使用返回数组替换当前 `segments`
- **AND** 返回中不存在的本地 segment SHALL 被移除

#### Scenario: 轮询替换 events
- **WHEN** `loadTimelineEvents()` 从服务端获取当前 Take 的完整有效 events
- **THEN** 前端 SHALL 使用返回数组替换当前 `timelineEvents`
- **AND** 返回中不存在的本地 event SHALL 被移除

#### Scenario: 过期 Take 响应不污染当前状态
- **WHEN** 前端已切换到新的 CaptureTake
- **AND** 旧 Take 的轮询请求随后返回
- **THEN** 前端 SHALL 丢弃该旧 Take 响应
- **AND** 前端 SHALL 不修改新 Take 的事件或区间状态

### Requirement: 录制中实时时间线视图

**变更**：替换 `CaptureConsolePage` 中时间戳胶囊占位为真正的 `MiniTimeline` 组件。

**修改前**：`CaptureConsolePage` 在录制阶段将最近 20 条事件渲染为时间戳芯片，不显示区间增长、非比赛时段叠加或分层轨道。

**修改后**：CaptureConsolePage SHALL 在 `recording` 和 `stopping` 阶段渲染 `<MiniTimeline>` 组件。
- MiniTimeline SHALL 显示盘/局/分三层区间轨道
- MiniTimeline SHALL 显示非比赛时段（回合间、暂停、换边）叠加层
- MiniTimeline SHALL 显示换边和重点标记
- MiniTimeline SHALL 显示实时播放头
- MiniTimeline SHALL 使用 `segments`、`events`、`liveState` 和 `elapsedMs` 作为数据源

### Requirement: 事件写入唯一入口

**变更**：`addTimelineEvent` 不再直接调用 `createTimelineEvent` API，仅通过 Outbox 写入。

**修改前**：按钮点击 → 创建 Outbox item → enqueue → 直接调用 `createTimelineEvent` → Outbox sender flush。同一事件可能产生两条 DB 记录。

**修改后**：按钮点击 → 创建 Outbox item → enqueue → Outbox sender 通过 `coding-actions` 接口发送 → 响应更新 `events`/`segments`/`liveState`。SHALL 不再直接调用 `POST /api/field-sessions/{id}/timeline-events`。
