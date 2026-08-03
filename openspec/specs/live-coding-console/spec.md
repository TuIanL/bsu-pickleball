# live-coding-console Specification

## Purpose

定义实时录制工作台中的 Coding Action、比赛状态快照、撤销重放、轮询合并和运行状态展示契约。

## Requirements

### Requirement: Coding Actions 语义命令 API

系统 MUST 提供语义级命令 API，后端在一个 SQLite 事务中完成命令日志、事件、区间投影、统一计分 FSM、自动收局和状态更新，并返回当前 CaptureTake 的完整有效投影。

#### Scenario: 执行 rally_result_a 或 rally_result_b
- **WHEN** 用户请求 coding action API
- **AND** action 为 `rally_result_a` 或 `rally_result_b`
- **AND** 存在 open rally
- **THEN** 系统 SHALL 在一个事务中关闭 rally、创建含胜方的 `rally_end`、运行对应规则 reducer、更新 `recent_results` 和 LiveCodingState
- **AND** 达到 21 分时系统 SHALL 在同一事务中自动关闭当前 game、写入最终比分并累计胜局
- **AND** 一方累计 3 个胜局时系统 SHALL 在同一事务中完成比赛

#### Scenario: 执行 rally_replay
- **WHEN** action 为 `rally_replay` 且存在 open rally
- **THEN** 系统 SHALL 关闭当前 rally 并记录 `validity=replay`
- **AND** 系统 SHALL 不改变任何计分或比赛结果字段

#### Scenario: 新规则拒绝无结果分结束
- **WHEN** take 使用 `hybrid_21_best_of_5_v1`
- **AND** 用户执行 `end_rally`
- **THEN** 系统 SHALL 拒绝该 action
- **AND** 系统 SHALL 提示必须选择 A 方胜、B 方胜或重打

#### Scenario: start_game 携带初始发球方
- **WHEN** 用户执行 `start_game`
- **AND** payload 包含 `initial_server_team`
- **THEN** 系统 SHALL 创建唯一的新 game 并初始化 0:0、发球方、每球得分阶段和右区站位

#### Scenario: revision 冲突
- **WHEN** 请求的 `expected_revision` 与当前 revision 不匹配且 `client_action_id` 为新 ID
- **THEN** 系统 SHALL 返回 409 Conflict 和权威 LiveCodingState
- **AND** 系统 SHALL 不自动重新执行该动作

### Requirement: LiveCodingState 快照管理

系统 MUST 维护实时编码状态快照，完整表达比赛阶段、比分、发球状态、胜局和比赛完成状态。

#### Scenario: 新比赛初始状态
- **WHEN** 创建新的单打或双打 match CaptureTake
- **THEN** 系统 SHALL 初始化 `score_a=0`、`score_b=0`、`games_won_a=0`、`games_won_b=0`
- **AND** `server_team` 和 `serving_side` SHALL 为 None
- **AND** `scoring_phase` SHALL 为 `rally`
- **AND** `match_status` SHALL 为 `not_started`
- **AND** `scoring_ruleset_version` SHALL 为 `hybrid_21_best_of_5_v1`

#### Scenario: API 返回完整状态
- **WHEN** 客户端获取 live state 或成功执行 coding action
- **THEN** 响应 SHALL 包含 revision、segment ordinals、match phase、比分、发球方、计分阶段、发球站位、双方胜局、比赛状态和 recent results

#### Scenario: 状态重放恢复
- **WHEN** undo 或一致性检查触发状态重建
- **THEN** 系统 SHALL 按有效命令日志恢复 segment、比分、发球状态、胜局和比赛结果

### Requirement: 完整层级状态转移规则

系统 MUST 根据比赛状态只允许合法的开局、开分和结果操作，并由制胜分自动完成局与比赛层级关闭。

#### Scenario: 等待开局
- **WHEN** 没有 open game 且比赛尚未完成
- **THEN** 系统 SHALL 允许 `start_game`
- **AND** 系统 SHALL 拒绝 `start_next_rally` 和 rally result action

#### Scenario: 等待开分
- **WHEN** 存在 open game 且不存在 open rally
- **THEN** 系统 SHALL 允许 `start_next_rally`
- **AND** 系统 SHALL 拒绝 rally result action

#### Scenario: 回合进行中
- **WHEN** 存在 open rally
- **THEN** 系统 SHALL 允许 `rally_result_a`、`rally_result_b` 或 `rally_replay`
- **AND** 系统 SHALL 拒绝重复开分或开局

#### Scenario: 比赛已结束
- **WHEN** `match_status=completed`
- **THEN** 系统 SHALL 拒绝 `start_game`、`start_next_rally` 和全部 rally result action

#### Scenario: side_change 不改比赛投影
- **WHEN** 用户执行 `change_side`
- **THEN** 系统 SHALL 不改变比分、胜局、发球方、计分阶段或 A/B 身份

### Requirement: 一键推进操作

系统 MUST 采用状态化的比赛推进流程，每一分通过一次开始操作和一次明确结果操作完成。

#### Scenario: 完成一分
- **WHEN** 用户在等待开分状态执行 `start_next_rally`
- **AND** 随后执行 `rally_result_a`、`rally_result_b` 或 `rally_replay`
- **THEN** 系统 SHALL 记录完整 rally 区间和结果
- **AND** 系统 SHALL 回到等待开分、等待下一局或比赛完成状态之一

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

系统 MUST 让比赛快捷键服从当前状态和先发方选择流程，不得绕过 UI 可用性约束。

#### Scenario: 动态快捷键
- **WHEN** 录制中且焦点不在表单控件或弹窗内
- **THEN** `2` SHALL 在允许开局时打开初始发球方选择器
- **AND** `3` SHALL 仅在等待开分时开始下一分
- **AND** `4`、`5`、`6` SHALL 仅在回合进行中分别提交 A 方胜、B 方胜和重打
- **AND** `7`、`8`、`H`、`Backspace` SHALL 分别保持换边、暂停、重点标记和撤销语义

#### Scenario: 选择器打开时
- **WHEN** 初始发球方选择器处于打开状态
- **THEN** 比赛 action 快捷键 SHALL 不触发后台 action

### Requirement: 前端乐观更新

系统 MUST 在等待比赛 action 响应时展示 pending 状态，但不得在客户端伪造比分、发球权、胜局或比赛结果。

#### Scenario: 结果提交中
- **WHEN** 用户提交 A 方胜、B 方胜或重打并等待后端响应
- **THEN** 当前结果操作 SHALL 显示 pending
- **AND** 所有会造成冲突的比赛主操作 SHALL 暂时禁用
- **AND** 计分板 SHALL 保持最近一次权威状态

#### Scenario: 权威响应返回
- **WHEN** coding action 成功返回
- **THEN** 前端 SHALL 用完整响应替换 live state、segments 和 timeline events
- **AND** 操作区 SHALL 根据新权威状态重新派生可用动作
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

CaptureConsolePage SHALL 在录制和停止阶段使用 MiniTimeline 展示实时分层时间线，而不是使用时间戳胶囊占位。

**变更**：替换 `CaptureConsolePage` 中时间戳胶囊占位为真正的 `MiniTimeline` 组件。

**修改前**：`CaptureConsolePage` 在录制阶段将最近 20 条事件渲染为时间戳芯片，不显示区间增长、非比赛时段叠加或分层轨道。

**修改后**：CaptureConsolePage SHALL 在 `recording` 和 `stopping` 阶段渲染 `<MiniTimeline>` 组件。
- MiniTimeline SHALL 显示盘/局/分三层区间轨道
- MiniTimeline SHALL 显示非比赛时段（回合间、暂停、换边）叠加层
- MiniTimeline SHALL 显示换边和重点标记
- MiniTimeline SHALL 显示实时播放头
- MiniTimeline SHALL 使用 `segments`、`events`、`liveState` 和 `elapsedMs` 作为数据源

#### Scenario: 录制阶段显示实时 MiniTimeline

- **WHEN** CaptureConsolePage 处于 `recording` 或 `stopping` 阶段
- **THEN** 页面 SHALL 渲染 MiniTimeline，并使用当前 segments、events、liveState 和 elapsedMs
- **AND** 页面 MUST NOT 退回仅显示时间戳胶囊的旧占位视图

### Requirement: 事件写入唯一入口

系统 SHALL 通过 Outbox 和 `coding-actions` 作为时间线事件的唯一写入入口，不得直接创建重复的 timeline event。

**变更**：`addTimelineEvent` 不再直接调用 `createTimelineEvent` API，仅通过 Outbox 写入。

**修改前**：按钮点击 → 创建 Outbox item → enqueue → 直接调用 `createTimelineEvent` → Outbox sender flush。同一事件可能产生两条 DB 记录。

**修改后**：按钮点击 → 创建 Outbox item → enqueue → Outbox sender 通过 `coding-actions` 接口发送 → 响应更新 `events`/`segments`/`liveState`。SHALL 不再直接调用 `POST /api/field-sessions/{id}/timeline-events`。

#### Scenario: 时间线事件只经 Outbox 写入

- **WHEN** 用户在实时录制工作台添加一个时间线事件
- **THEN** 前端 SHALL 创建并发送一个 Outbox item
- **AND** 前端 MUST NOT 直接调用 `POST /api/field-sessions/{id}/timeline-events`

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
