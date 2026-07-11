## Why

实时录制模式下的事件编码（live coding）功能存在数据链路断裂和可视化不足两个核心问题。编码动作通过 FIFO outbox 排队后从未实际发送到服务端，导致 CaptureSegment 和 TimelineEvent 无法被创建，MiniTimeline 始终空白。同时 MiniTimeline 的视觉设计使用底部倒三角事件标记，用户无法直观通过色条理解比赛结构。

## What Changes

1. **修复 Outbox Sender 初始化**：`CaptureConsolePage` 在开始录制后从未调用 `createOutboxSender()`，所有 coding action 堆积在 localStorage。单摄/双摄开始录制时初始化 sender。

2. **添加响应回写机制**：sender 在 `executeCodingAction` 成功后丢弃了响应体。添加 `onResponse` 回调，将 `created_events`、`updated_segments`、`live_state` 和 `revision` 合并回前端状态。

3. **修复 revision 同步问题**：sender 使用 React 闭包读取 `liveCodingState.revision` 会导致陈旧值。使用 `useRef` 维护权威 revision 值，每次响应后同步更新。

4. **添加 sender.drain()**：停止录制前必须排空 outbox。当前 stop() 只设置 `_stopped=true`，不等待发送中的队列。新增 `drain()` 方法，在所有 pending action 完成（或失败）后才允许停止录制。drain 失败时提示用户，不静默丢弃。

5. **修复刷新后 FIFO 顺序错乱**：`_sequenceCounter` 是模块内变量，刷新归零后新 action 序号低于旧 pending action，排序错乱。改为按 CaptureTake 从 localStorage 计算下一序号。

6. **409 revision_conflict 不自动语义重放**：不同 `client_action_id` 的 conflict 不应在刷新 revision 后盲目重试。应停止队列、标记 blocked、提示用户确认。

7. **修复后端 revision 不一致**：后端响应中顶层 `revision` 与 `live_state.revision` 可能不一致，导致下一条 409。后端保证两者一致，前端以顶层为准兜底。

8. **修复后端幂等响应缺字段**：命中相同 `client_action_id` 的幂等分支缺少 `created_events` 和 `updated_segments`，刷新重放时可能校验失败。

9. **TimelineEvent 按 CaptureTake 隔离**：当前 `listTimelineEvents(sessionId)` 返回整个 Field Session 的事件。需增加 `capture_take_id` 过滤，防止同一 Field Session 中连续录制多个 Take 时事件串数据。

10. **修复 open segment 绘制逻辑**：MiniTimeline 中开放 segment 的宽度画到了 `viewDuration`（未来 30s），改为跟随 `elapsedMs` 实时增长。

11. **MiniTimeline 视觉重构**：去掉底部倒三角事件标记行，色条本身表达事件递进。瞬时事件（换边、重点标记）改用细竖线或小图标。非比赛状态用灰色覆盖区间。非比赛区间需从事件序列推导，而非仅依赖 liveCodingState 的 boolean。

12. **双摄模式接入 live coding**：双摄开始录制后未设置 `captureTakeId` 也未初始化 sender，导致双摄无法使用事件编码。

13. **MiniTimeline 位置调整**：将 MiniTimeline 从独立卡片移入视频预览正下方，成为播放器时间轴的一部分。

## Capabilities

### New Capabilities

无。本次 change 不引入新能力，仅修复和增强已有能力。

### Modified Capabilities

- `live-coding-console`: 修复 outbox sender 生命周期和响应回写的缺失；增强 MiniTimeline 可视化要求
- `capture-workflow`: 更新采集控制台底部时间线的布局规格，明确 MiniTimeline 位于视频预览正下方

## Impact

| 影响范围 | 内容 |
|---------|------|
| `CaptureConsolePage.tsx` | 初始化 sender、ref 同步、双摄接入、drain 顺序 |
| `codingOutbox.ts` | 添加 `onResponse` 回调、`drain()` 方法、修复 `sequenceNumber` |
| `MiniTimeline.tsx` | open segment 绘制修复、视觉重构、非比赛区间推导 |
| `analysisClient.ts` | TimelineEvent 查询增加 `capture_take_id` 参数 |
| 后端 | `live_state.revision` 同步、幂等响应补字段 |
