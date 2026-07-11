## ADDED Requirements

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
