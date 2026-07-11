## Context

`CaptureConsolePage.tsx` 的实时编码（live coding）控制台通过 `codingOutbox.ts` 的 FIFO 队列管理 coding action。设计上要求队列按序发送至后端 `POST /api/capture-takes/{id}/coding-actions`，后端在同一事务内创建 TimelineEvent、CaptureSegment 并更新 LiveCodingState。

当前实现存在系统性断裂：

- `createOutboxSender()` 在开始录制后从未被调用，sender ref 始终为 null，所有 action 永久堆积在 localStorage
- `executeCodingAction` 成功后丢弃响应体，前端无法获得后端创建的事件和段
- revision 通过 React 闭包读取，发送第 N+1 条时仍用第 N 条发起时的旧值
- 页面刷新后 `_sequenceCounter` 归零，新 action 序号低于旧 pending action，FIFO 顺序错乱
- 停止录制时未排空 outbox，正在发送的 action 可能被丢弃
- 409 revision_conflict 会盲目重试 5 次，可能重复创建语义动作
- TimelineEvent 按 `sessionId` 查询而非 `captureTakeId`，连续录制多个 Take 时事件串数据
- MiniTimeline 开放 segment 画到未来 30s，底部倒三角标记无法直观表达比赛结构
- 非比赛区间仅靠 `liveCodingState.non_play` boolean，缺少历史区间推导
- 双摄模式未走任何 live coding 初始化路径

## Goals / Non-Goals

**Goals:**
- coding action 可靠送达后端，响应回写前端
- 停止录制前排空 outbox，不丢事件
- 刷新后 FIFO 顺序正确恢复
- 409 revision_conflict 不自动语义重放
- revision 在多 action 排队时准确递增
- TimelineEvent 按 CaptureTake 隔离
- MiniTimeline 实时显示色条增长，去掉倒三角
- 非比赛区间从事件序列正确推导
- MiniTimeline 位于视频预览正下方
- 双摄与单摄统一初始化

**Non-Goals:**
- 不引入 IndexedDB，继续使用 localStorage 持久化 outbox
- 不改动后端 CaptureCodingAction 主事务逻辑
- 不重写 MiniTimeline 组件，仅修改绘制逻辑和视觉细节
- 不修改键盘快捷键映射

## Decisions

### 1. Sender 接口扩展：add `drain()`

当前 `OutboxSender` 接口：

```
interface OutboxSender {
  flush(): Promise<void>;
  stop(): void;
}
```

扩展为：

```
interface OutboxSender {
  flush(): Promise<void>;
  drain(): Promise<void>;   // 新增
  stop(): void;
}
```

`drain()` 行为：

- 等待当前 inflight 请求完成
- 继续处理队列中剩余的 pending item，直到所有 item 状态为 `synced` 或 `failed`/`blocked`
- 返回后调用者可安全停止录制
- 设置 `_draining = true`，后续 `flush()` 调用不启动新发送（防止 drain 过程中外部再触发）

`drain()` 实现：

```
async drain() {
  _draining = true;
  await this.flush(); // 处理完当前 + 剩余 pending
}
```

`flush()` 修改：在循环开始时检查 `_draining || _stopped`，在 `_draining` 模式下仍然处理队列，但不接受外部新触发。

### 2. 停止录制前 drain

单摄停止顺序：

```
await outboxSenderRef.current?.drain()
  → 如果有 failed/blocked 项，返回 { unsynced: number }
await stopRecording(...)
outboxSenderRef.current?.stop()
```

如果 `drain()` 后仍有未同步项，显示确认弹窗：

```
仍有 2 个事件未同步
[放弃停止] [仍然停止]
```

双摄停止同理。

### 3. 修复 sequenceNumber 刷新归零

当前 `_sequenceCounter` 是模块级变量：

```
let _sequenceCounter = 0;
```

每次页面刷新归零。

改为在 `createOutboxItem` 内从 localStorage 动态计算：

```
function nextSequenceNumber(captureTakeId: string): number {
  const items = loadOutbox();
  const takeItems = items.filter(i => i.captureTakeId === captureTakeId);
  const maxSeq = takeItems.reduce((max, i) => Math.max(max, i.sequenceNumber), 0);
  return maxSeq + 1;
}
```

`createOutboxItem` 不再使用 `_sequenceCounter`：

```
export function createOutboxItem(
  captureTakeId: string,
  action: CodingActionType,
  timestampMs: number,
  payload: Record<string, unknown> = {},
): CodingOutboxItem {
  return {
    clientActionId: generateActionId(),
    captureTakeId,
    sequenceNumber: nextSequenceNumber(captureTakeId),
    action,
    timestampMs,
    ...
  };
}
```

### 4. 409 revision_conflict 策略

区分两种 409：

| 场景 | 后端 error | 前端行为 |
|------|-----------|---------|
| 相同 client_action_id（幂等） | `duplicate_action` | 与成功相同，信任后端已执行 |
| 不同 client_action_id revision 冲突 | `revision_conflict` | 停队列、标记 blocked、提示用户 |

后端已在 `live-coding-console` spec 中区分这两种响应。前端 sender 根据 `error` 字段判断：

```
if (response.duplicate) {
  // 幂等：信任后端
  updateItem(item.clientActionId, { status: "synced" });
  return;
}

if (status === 409 && error === "revision_conflict") {
  // 真正的冲突：不自动重试
  updateItem(item.clientActionId, { status: "blocked", lastError: "revision_conflict" });
  // 标记后续所有 pending 为 blocked
  blockAllSubsequentItems(captureTakeId, item.sequenceNumber);
  // 通知用户
  onStateChange(getPendingItems(captureTakeId));
  return;
}
```

前端提示：

```
事件状态已发生变化
“下一分”未自动重试，以避免重复创建。
[放弃此操作] [确认重新执行]
```

用户确认后手动将 blocked 项重新标记为 pending 并 flush。

### 5. Revision 权威值：useRef 而非闭包

**决策**：放弃 `() => liveCodingState?.revision`，改用独立 `revisionRef`。

```
const revisionRef = useRef(0);
const liveCodingStateRef = useRef<LiveCodingState | null>(null);
```

sender 获取 revision 的回调：`() => revisionRef.current`。

每次响应后同步写入 ref。

### 6. Response 回调设计

`createOutboxSender` 新增第 4 个参数 `onResponse`。

sender 在 `executeCodingAction` 成功后调用 `onResponse(response)`，由 `CaptureConsolePage` 执行合并：

```
function applyCodingResponse(response: CodingActionResponse) {
  revisionRef.current = response.revision;

  const state = {
    ...response.live_state,
    revision: response.revision,
  };
  if (response.duplicate) {
    // 幂等：仅更新 state
    liveCodingStateRef.current = state;
    setLiveCodingState(state);
    return;
  }

  liveCodingStateRef.current = state;
  setLiveCodingState(state);

  if (response.created_events?.length) {
    setTimelineEvents(prev => upsertById(prev, response.created_events));
  }
  if (response.updated_segments?.length) {
    setSegments(prev => upsertById(prev, response.updated_segments));
  }
}
```

`upsertById`：如果 `id` 已存在则替换，否则追加。

### 7. TimelineEvent 按 CaptureTake 隔离

**问题**：当前 `listTimelineEvents(sessionId)` 返回整个 Field Session 的事件。同一 Field Session 内连续录制两个 Take 时，第二个 Take 的 MiniTimeline 可能画出第一个 Take 的事件。

**方案**：`listTimelineEvents` 新增 `capture_take_id` 查询参数。

```
GET /api/field-sessions/{sessionId}/timeline-events?capture_take_id={takeId}
```

前端在 `loadTimelineEvents` 中传入当前 `captureTakeId`：

```
const loadTimelineEvents = useCallback(async () => {
  if (!captureTakeId) return;
  const events = await listTimelineEvents(sessionId, { capture_take_id: captureTakeId });
  setTimelineEvents(events);
}, [sessionId, captureTakeId]);
```

**切换 Take 时清空旧状态**：`initializeLiveCoding` 中 setCaptureTakeId 后，清空旧 events 和 segments：

```
setTimelineEvents([]);
setSegments([]);
```

### 8. 非比赛区间推导

`liveCodingState.non_play` 只有当前 boolean，不包含历史区间。

定义推导函数：

```
interface TimelineRange {
  startMs: number;
  endMs: number;
}

function deriveNonPlayRanges(
  events: SessionTimelineEvent[],
  elapsedMs: number,
): TimelineRange[]
```

规则：

- 遍历 events，按 `timestamp_ms` 排序
- `non_play_start` → 打开新区间
- `non_play_end` → 关闭最近一个未关闭区间
- 录制中仍未关闭 → `endMs = elapsedMs`
- 连续两个 start → 忽略第二个并记录诊断警告
- 孤立 end → 忽略并记录诊断警告

MiniTimeline 接收 `nonPlayRanges` 作为 prop 或在组件内调用推导函数。

灰色覆盖渲染：对每个 `TimelineRange`，在三条轨道上叠加 `background: rgba(156, 163, 175, 0.2)` 的绝对定位块。

### 9. MiniTimeline 视觉方案

**去掉倒三角标记行**：删除 MiniTimeline.tsx 中 event markers 的 SVG 三角渲染代码。

**瞬时事件**：

| 类型 | 可视化方式 | 颜色 |
|------|-----------|------|
| `side_change` | 紫色 1px 竖线 + 顶部菱形 | `#A855F7` |
| `add_note` / `session_note` | 黄色星形图标 | `#F59E0B` |

竖线/图标叠加在色条轨道上方，高度 16px，不单独占用一行。

**非比赛覆盖**：使用 `deriveNonPlayRanges()` 获得区间列表，在三轨道上叠加灰色遮罩。

**录制中始终显示三轨**：即使 segments 为空，三条轨道以空白背景色渲染。移除 "录制中·持续扩展" 文字。轨道高度 26px。

**open segment**：右边界 `Math.max(elapsedMs, seg.start_ms)`。

### 10. MiniTimeline 位置调整

从当前页面底部的独立卡片移入视频预览区域正下方，作为播放器时间轴的一部分。

具体布局：

```
┌─────────────────────────────┐
│         实时视频预览          │
├─────────────────────────────┤
│ 盘 ▓▓▓▓▓▓▓░░░░░░░░░░░░░░░░░ │
│ 局 ░░░░░▓▓▓▓▓▓▓▓░░░░░░░░░░░ │
│ 分 ░░░░░░░░░░░░▓▓▓▓▓▓▓▓░░░░ │
│ 0:00               0:30  1:00│
├─────────────────────────────┤
│      录制控制 / 事件按钮      │
└─────────────────────────────┘
```

去掉 MiniTimeline 的外层白色卡片（`rounded-2xl border bg-white p-4`），改为无边框背景与预览区融为一体的样式。

### 11. Sender 生命周期管理

单摄与双摄共享 `initializeLiveCoding(takeId)`：

```
async function initializeLiveCoding(takeId: string) {
  setCaptureTakeId(takeId);
  setTimelineEvents([]);
  setSegments([]);

  try {
    const state = await getLiveCodingState(takeId);
    revisionRef.current = state.revision;
    liveCodingStateRef.current = state;
    setLiveCodingState(state);
  } catch (err) {
    // 新 Take 可能尚无 state（修订版后端），使用 revision 0
    revisionRef.current = 0;
    liveCodingStateRef.current = null;
    setLiveCodingState(null);
  }

  outboxSenderRef.current?.stop();
  outboxSenderRef.current = createOutboxSender(
    takeId,
    () => revisionRef.current,
    setOutboxItems,
    applyCodingResponse,
  );

  setOutboxItems(getPendingItems(takeId));
  await outboxSenderRef.current.flush();
}
```

清理时机：

| 场景 | 操作 |
|------|------|
| 停止录制 | `await sender.drain()` → `stopRecording()` → `sender.stop()` |
| 组件卸载 | `sender.stop()` + 清理计时器 |
| 新录制替换旧 sender | 先 stop 旧 sender，再创建新的 |

**初始化失败处理**：

```
type LiveCodingInitResult =
  | { status: "ready" }
  | { status: "degraded"; reason: string }
  | { status: "unavailable"; reason: string };
```

- `getLiveCodingState` 404（新 Take）→ `degraded`，使用 revision 0，允许 flush
- `getLiveCodingState` 其他错误 → `unavailable`，禁止 flush，显示"编码暂不可用"
- 刷新后 `getLiveCodingState` 失败 → `unavailable`，不允许用 revision 0

### 12. 双摄接入

双摄开始录制后，检查 `session.capture_take_id`，调用 `initializeLiveCoding(takeId)`。为空时跳过，静默降级。

### 13. 后端改动

**13a. revision 一致**：`_apply_action()` 末尾：

```
new_revision = take.revision + 1
take.revision = new_revision
state.revision = new_revision
```

**13b. 幂等响应补字段**：

```
return {
    "revision": ...,
    "created_events": [],
    "updated_segments": [],
    "live_state": ...,
    "duplicate": True,
}
```

### 14. 轮询合并

简单规则：服务端同 ID 数据覆盖本地，服务端新 ID 追加，本地独有的 optimistic 数据保留。

```
setSegments(current => {
  const merged = new Map(current.map(s => [s.id, s]));
  for (const s of serverSegments) {
    merged.set(s.id, s);
  }
  return Array.from(merged.values());
});
```

不实现 `updated_at` 时间戳比较（当前 segments 响应无此字段）。

## Risks / Trade-offs

| 风险 | 缓解措施 |
|------|---------|
| drain() 期间用户等待时间长 | drain 显示进度；超时 10s 后允许强制停止 |
| getLiveCodingState 失败误用 revision 0 | 区分新 Take（404）和临时错误（500），后者阻止 flush |
| 双摄后端尚未创建 CaptureTake | 检查为空时跳过初始化，静默降级 |
| old outbox 重放时 409 阻塞 | 用户确认后手动重试；幂等 action（同 client_action_id）自动成功 |
| 轮询合并与服务端删除不同步 | 服务端不删除 segment/event，仅标记状态，合并后本地保留旧 ID 无实际影响 |
