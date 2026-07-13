## Context

现有实时编码以 `start_next_rally` 同时关闭当前分并创建下一分，`toggle_non_play` 再次承担关闭分和切换非比赛状态的职责，`change_side` 只写瞬时事件。三个命令无法表达真实的赛间流程。`LiveCodingState` 只有 `non_play` boolean，`CaptureSegment` 和 TimelineEvent 则由 action 就地修改。

undo 当前只把 `rally_ordinal` 减一，既未标记目标 action 产生的事件，也未恢复、归档或重建受影响的 CaptureSegment；前端轮询和 action 响应都按 ID `upsert`，因此服务端快照中不存在的条目仍被保留。MiniTimeline 又以 `elapsedMs` 作为全时间轴的百分比基准，每秒重算布局，造成历史色条整体跳动。

本变更覆盖单摄和双摄共享的 CaptureTake live coding 路径。已有的人工时间线 REST API 保持可用；仅比赛实时控制台改用新的语义 action。

## Goals / Non-Goals

**Goals:**

- 用显式状态表达等待开分、进行中分和带原因的间歇，令控制按钮与比赛实际操作一一对应。
- 以 CaptureCodingAction 的未撤销命令序列重放出 LiveCodingState、有效 TimelineEvent 和有效 CaptureSegment，保证 undo 后没有重复或残留。
- 让 coding action 与轮询都返回或获取权威完整投影，前端以替换而非增量保留的方式同步。
- 用固定时宽滚动窗口和连续时钟渲染 MiniTimeline，使已发生区间不因总时长增长而缩放。
- 保留旧事件和已完成 Take 的可读性，并为缺少原因的历史非比赛事件提供默认解释。

**Non-Goals:**

- 不实现比分录入、发球方、自动换边规则或依据 pickleball 赛制自动触发暂停。
- 不重写 CaptureTake、视频录制、Outbox FIFO 或 Segment Manager 的整体架构。
- 不改变练习、工程模式的快捷事件集，也不迁移或删除历史 TimelineEvent。
- 不引入新的前端动画或状态管理依赖。

## Decisions

### D1: 采用分、间歇、原因三层状态，而不是新的独立“非比赛”开关

LiveCodingState 增加 `match_phase: idle | rally_active | intermission` 与可选 `intermission_kind: between_rallies | timeout | side_change`；保留 `non_play` 作为向后兼容的派生字段，只有 `match_phase === intermission` 时为 true。按钮及 action 约束如下：

| 动作 | 前置状态 | 原子结果 |
|---|---|---|
| `start_next_rally` | `idle` 或 `intermission` | 关闭已有间歇，创建并打开下一分 |
| `end_rally` | `rally_active` | 关闭当前分，开启 `between_rallies` 间歇 |
| `start_timeout` | 任意非终止状态 | 若有当前分先关闭；关闭已有间歇；开启 `timeout` 间歇 |
| `change_side` | 任意非终止状态 | 写入 `side_change` 点事件；若有当前分先关闭；关闭已有间歇；开启 `side_change` 间歇 |

`start_next_rally` 在 `rally_active` 时由服务端拒绝，前端也禁用按钮；不再使用“点击下一分即推进”的捷径。`end_rally` 在无当前分时维持 no-op，避免离线 Outbox 重放失败。`start_set` 与 `start_game` 仍关闭必要层级和现有间歇。

选择保留一个通用间歇事件对 `non_play_start` / `non_play_end`，并在 `payload_json.intermission_kind` 写入原因。这样现有查询、历史数据和通用时间线 API 无需分裂；已有 `timeout_start/end` 枚举不再作为此控制台的第二套区间协议。替代方案是为三种原因建立三组事件类型，否决原因是范围配对和历史兼容会更复杂。

### D2: CaptureCodingAction 是唯一事实来源，区间与状态是可替换投影

每个 action 记录其直接创建或修改的 event/segment ID，并将这些关联写入 action 结果。执行 undo 时，服务端标记目标 action 为 `undone`、写入 `reverses_action_id`，将该 action 直接产生的事件标记 `is_undone=true`，并使由其产生或边界受其影响的 Segment 退出 active 投影。随后按时间和 revision 重放未撤销的业务 action，生成当前有效的 LiveCodingState、TimelineEvent 与 CaptureSegment 投影。

重放产物以完整 `timeline_events`、`segments` 和 `live_state` 返回给 action 调用者；`GET` 列表同样是完整的有效快照。前端收取任何权威快照时整体替换当前 Take 的对应数组，绝不保留服务端未返回的 ID。这样连续“开始第 6 分 → 撤销 → 再开始第 6 分”只会留下一个有效第 6 分。

不直接物理删除原始 action、事件或 Segment，审计数据仍保留。替代方案是仅返回 deleted ID 供前端差量删除，否决原因是 undo 常会同时影响起止事件、开放区间和层级状态，差量协议易漏且难以在刷新后校正。

### D3: 前端只乐观展示请求状态，不乐观伪造 ordinal 或 Segment

点击后，按钮进入 pending/禁用状态并向 Outbox 入队；显示中的第几盘、局、分和时间线条必须等待服务端 action 响应的权威投影。成功响应替换快照，409 冲突则以服务端状态替换并阻塞后续队列。这样牺牲一次网络往返内的计数即时变化，换取与 FIFO、undo、离线重放一致的可观察状态。

### D4: MiniTimeline 使用固定时宽滚动窗口和连续 elapsed 时钟

时间线使用固定 90 秒可视窗口。录制不满窗口时从 0 开始；超过窗口后 `windowStartMs = elapsedMs - 90s`，所有段、遮罩和游标以相对窗口的稳定像素坐标渲染，窗口平滑向前移动。时钟由录制起点结合 `requestAnimationFrame` 推进，React 的秒级状态仅用于其他 UI，不作为时间线布局时钟。

赛间间歇使用现有浅灰半透明遮罩；暂停使用更深的条纹遮罩；换边间歇使用带紫色边界的浅紫遮罩，并保留紫色竖线和菱形瞬时标记。历史 `non_play` 事件缺少 kind 时按 `between_rallies` 显示。

替代方案是继续百分比布局并添加 CSS transition。否决原因是坐标系仍会每秒重算，transition 只会把整体缩放变成拖影，无法保证区间长度稳定。

### D5: 接口和数据兼容策略

前端类型增加 `start_timeout` action、`match_phase`、`intermission_kind` 和 action 响应的完整投影字段。后端在一个事务中写 action、事件、Segment 投影与 state；旧的 `toggle_non_play` 可继续被历史客户端识别，但比赛控制台不再产生它。历史未带 `intermission_kind` 的 `non_play_start/end` 在读模型和前端均默认解释为 `between_rallies`。

## Risks / Trade-offs

- [Risk] 重放实现与现有就地 Segment 更新暂时并存，可能产生两种有效性判定。→ Mitigation：先为投影定义唯一的 active 查询路径，并为每个 action 保存关联 ID；所有 action 响应和列表均通过该路径生成。
- [Risk] 90 秒窗口会隐藏更早的时间线。→ Mitigation：该组件定位为实时 MiniTimeline；结束录制后由 Segment Manager 提供全时长浏览和编辑。
- [Risk] 异步 Outbox 期间按钮状态可能短暂滞后。→ Mitigation：为 pending 操作提供明确的禁用和同步反馈，响应到达后以权威快照更新。
- [Risk] 历史事件没有间歇原因。→ Mitigation：默认映射到 `between_rallies`，不做破坏性迁移。
- [Risk] 新旧客户端混用 `toggle_non_play`。→ Mitigation：后端保留兼容处理，并在 action 审计中保留原始类型；新 UI 不暴露该操作。

## Migration Plan

1. 扩展后端 schema、action enum、state 字段和 action-result 关联；部署保持旧记录可读。
2. 实现重放和完整投影 API，并以服务端测试验证新旧 action 序列、undo 和历史间歇兼容。
3. 更新前端类型、Outbox、控制台和 MiniTimeline；仅在新响应字段可用时启用替换策略。
4. 在单摄与双摄录制中验证完整流程：开始分、结束分、暂停、换边、撤销、再次开始相同序号的分。
5. 如需回滚，前端可回退至旧控制台构建；数据库中新增字段和审计记录保持向后兼容，无需删除数据。

## Open Questions

无。战术暂停采用“按下即可原子结束当前分并开始暂停”的操作，以减少场边连续点击；如未来需要严格裁判流程，可再增加只在间歇可用的限制。
