## MODIFIED Requirements

### Requirement: Coding Actions 语义命令 API

系统 MUST 提供语义级命令 API，后端在一个 SQLite 事务中完成命令日志、事件、区间投影、计分状态机和状态更新，并返回当前 CaptureTake 的完整有效投影。

**修改内容**: 新增三种结果 action 类型（`rally_result_a`、`rally_result_b`、`rally_replay`），match + singles 模式下替代 `end_rally`；新增 `correct_score` action 类型；`start_game` 新增 `initial_server_team` payload。每个 result action 在同一事务内完成段操作、比分 FSM 和状态更新。`end_rally` 作为后端合法 action 保留。

#### Scenario: 执行 rally_result_a action
- **WHEN** 用户请求 `POST /api/capture-takes/{id}/coding-actions`
- **AND** `action` 为 `rally_result_a`
- **AND** 存在 open rally
- **THEN** 系统 SHALL 在一个事务内完成：
  - 关闭 open rally segment，创建 `rally_end` 事件（payload 含 `winner:"A"`、`validity:"valid"`）
  - 关闭当前间歇（如果有）
  - 创建 `non_play_start` 事件（`intermission_kind: "between_rallies"`）
  - 执行 FSM reducer：发球方为 A 时 `score_a` 加 1；发球方为 B 时 side out
  - push 到 `recent_results` 尾部
  - 更新 `LiveCodingState` 的 `score_a`、`server_team`、`match_phase`、`recent_results` 等字段
  - 更新 `CaptureTake.revision`

#### Scenario: 执行 rally_result_b action
- **WHEN** `action` 为 `rally_result_b`
- **AND** 存在 open rally
- **THEN** 系统 SHALL 在同一事务内完成 rally 关闭、`rally_end` 事件创建（`winner:"B"`）、FSM 更新（发球方赢则加分，接发方赢则 side out）

#### Scenario: 执行 rally_replay action
- **WHEN** `action` 为 `rally_replay`
- **AND** 存在 open rally
- **THEN** 系统 SHALL 在同一事务内完成 rally 关闭、`rally_end` 事件创建（`validity:"replay"`）
- **AND** FSM SHALL 不改变 `score_a`、`score_b` 和 `server_team`
- **AND** `recent_results` SHALL push `{"validity": "replay"}`

#### Scenario: 无 open rally 时结果 action 返回错误
- **WHEN** 不存在 open rally
- **AND** 用户执行 `rally_result_a`、`rally_result_b` 或 `rally_replay`
- **THEN** 系统 SHALL 返回错误
- **AND** 系统 SHALL 不执行 FSM 更新

#### Scenario: 执行 correct_score action
- **WHEN** `action` 为 `correct_score`
- **AND** payload 包含 `score_a`、`score_b`、`server_team`
- **THEN** 系统 SHALL 将 `LiveCodingState` 的 `score_a`、`score_b`、`server_team` 设为 payload 中的值
- **AND** 系统 SHALL 不创建或关闭任何 `CaptureSegment` 或段相关 `TimelineEvent`
- **AND** 系统 SHALL 创建一条 `score_correction` 类型的 TimelineEvent

#### Scenario: start_game 携带初始发球方
- **WHEN** 用户执行 `start_game` action
- **AND** payload 包含 `initial_server_team`
- **THEN** 系统 SHALL 在现有段操作之外额外执行：
  - `score_a` = 0
  - `score_b` = 0
  - `server_team` = `payload.initial_server_team`
  - `recent_results` = []

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

系统 MUST 维护 CaptureTake 的实时编码状态快照，每次成功 action 在同一事务内更新，并显式表达比赛阶段、间歇原因、计分状态和计分模式。

**修改内容**: `LiveCodingState` 新增 `server_team`、`score_a`、`score_b`、`scoring_mode`、`scoring_ruleset_version`、`recent_results` 字段；`start_game` 初始化比分和发球方。

#### Scenario: 初始状态（单打）
- **WHEN** 创建新的 CaptureTake
- **AND** `match_format` 为 `singles`
- **THEN** 系统 SHALL 初始化 LiveCodingState：
  - `set_ordinal` = 0, `game_ordinal` = 0, `rally_ordinal` = 0
  - `match_phase` = `idle`, `intermission_kind` = None
  - `score_a` = 0, `score_b` = 0, `server_team` = None
  - `scoring_mode` = `"side_out_singles_v1"`
  - `scoring_ruleset_version` = `"side_out_singles_v1"`
  - `recent_results` = []

#### Scenario: 双打初始状态
- **WHEN** 创建新的 CaptureTake
- **AND** `match_format` 为 `doubles`
- **THEN** 系统 SHALL 将 `scoring_mode` 设为 `"manual"`
- **AND** `scoring_ruleset_version` 设为 `"manual"`
- **AND** 不初始化计分相关字段

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
- **AND** 响应 SHALL 包含 revision、ordinal、`match_phase`、`intermission_kind`、`non_play`、`score_a`、`score_b`、`server_team`、`scoring_mode`、`scoring_ruleset_version`、`recent_results`

### Requirement: 完整层级状态转移规则

系统 MUST 根据完整的状态转移表执行层级关闭、开分、间歇操作和计分状态机更新。

**修改内容**: match + singles 模式下 `end_rally` 被三种结果 action 替代；`side_change` 额外要求不改变比分和发球方；双打模式不执行 FSM。

#### Scenario: rally_result_a 关闭当前分并进入间歇
- **WHEN** `match_phase` 为 `rally_active`
- **AND** 执行 `rally_result_a` action
- **THEN** 系统 SHALL 关闭 open rally 并创建 `rally_end` 事件（`payload.winner="A"`）
- **AND** 系统 SHALL 创建 `intermission_kind` 为 `between_rallies` 的 `non_play_start` 事件
- **AND** 系统 SHALL 将 `match_phase` 设为 `intermission`
- **AND** 系统 SHALL 执行 FSM 计分和发球权更新

#### Scenario: side_change 不改比分和发球权
- **WHEN** 执行 `change_side` action
- **THEN** 系统 SHALL 不改变 `score_a`、`score_b`、`server_team`
- **AND** A/B 身份 SHALL 保持不变

#### Scenario: start_next_rally 后比分不变
- **WHEN** 执行 `start_next_rally` action
- **THEN** 系统 SHALL 不改变 `score_a`、`score_b`、`server_team` 和 `recent_results`
- **AND** FSM 状态 SHALL 保持不动

### Requirement: 一键推进操作

**修改内容**: 新增 "分开始后再点结果按钮" 的配搭操作模式。

#### Scenario: 比分模式下的一分两击
- **WHEN** 比赛录制中
- **AND** 用户点击 `start_next_rally` 开分
- **AND** 用户随后点击 `rally_result_a`、`rally_result_b` 或 `rally_replay`
- **THEN** 系统 SHALL 记录该分结果并更新计分状态
- **AND** 每分必须经过"分开始"和"结果按钮"两次操作

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

**修改内容**: 新增三个结果按钮和修正比分的快捷键映射。

#### Scenario: 快捷键映射
- **WHEN** 录制中且焦点不在 input/textarea/select，且无弹窗
- **THEN** 系统 SHALL 响应以下快捷键：
  - `1` → 开始新盘
  - `2` → 开始新局
  - `3` → 开始下一分
  - `4` → A 方胜
  - `5` → B 方胜
  - `6` → 重打
  - `7` → 换边
  - `8` → 战术暂停
  - `H` → 重点片段
  - `Backspace` → 撤销

#### Scenario: 快捷键不响应
- **WHEN** 焦点在 input/textarea/select 或打开弹窗
- **THEN** 系统 SHALL 不响应快捷键

### Requirement: 前端乐观更新

**修改内容**: 前端在等待 `rally_result_*` 响应时，乐观显示计分板 pending 状态而非伪造比分。

#### Scenario: 结果按钮 pending 状态
- **WHEN** 用户点击 `rally_result_a`
- **AND** 等待后端响应期间
- **THEN** 前端 SHALL 将结果按钮展示为 pending 状态（禁用、旋转动画或透明度变化）
- **AND** 前端 SHALL 不自行增加比分或改变发球方显示
- **AND** 计分板 SHALL 保持之前的状态

#### Scenario: 结果确认后计分板同步
- **WHEN** 收到后端成功响应
- **THEN** 前端 SHALL 以后端返回的 `live_state.score_a`、`score_b`、`server_team`、`recent_results` 更新计分板
- **AND** 前端 SHALL 释放按钮的 pending 状态

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

### Requirement: 桌面端实时录制工作台层级

实时录制实施页 SHALL 按标题栏、双机位预览、录制控制条、事件标注时间线和底部信息区的顺序组织主要内容。

#### Scenario: 双摄桌面工作台

- **WHEN** 用户打开双摄实时录制实施页
- **THEN** 页面 SHALL 同时展示两个机位预览、录制状态、录制控制、事件按钮和时间线
- **AND** 页面 SHALL 在 1024px 及以上视口不产生横向滚动

#### Scenario: 单摄桌面工作台

- **WHEN** 用户打开单摄实时录制实施页
- **THEN** 页面 SHALL 展示一个主预览和与其对应的设备/比分上下文
- **AND** 不得渲染空白的第二机位占位

### Requirement: 真实运行指标展示

工作台 SHALL 使用 CaptureTake 运行状态 API 展示存储容量、文件大小、码率、帧率和轨道健康状态；指标不可用时 SHALL 展示对应的采集或不可用状态。

#### Scenario: 运行状态成功更新

- **WHEN** 运行状态 API 返回 `ready` 指标
- **THEN** 页面 SHALL 展示后端返回的数值和单位
- **AND** 页面不得使用硬编码系统状态覆盖返回值

#### Scenario: 运行状态请求失败

- **WHEN** 运行状态轮询请求失败
- **THEN** 页面 SHALL 保留最后一次成功快照
- **AND** SHALL 显示状态更新失败及最后更新时间
- **AND** 不得阻塞停止、取消或事件标注操作

### Requirement: 系统状态真实性

系统状态卡 SHALL 只展示后端能够确认的存储、录制轨道、双路同步和事件同步状态。

#### Scenario: 没有音频链路

- **WHEN** 当前录制链路没有音频编码
- **THEN** 系统状态卡 SHALL 不展示“音频编码正常”或等价的虚假状态

#### Scenario: 双摄局部故障

- **WHEN** 一个轨道失败而另一个轨道仍可录制
- **THEN** 页面 SHALL 展示整体状态和对应轨道的独立错误信息
