## Context

单摄录制存在两个独立但同样严重的回归问题：

1. **停止必失败**：`routes_recording.py` 的 `POST /api/recordings/{id}/stop` 路由在组装 `CaptureStopResult` 时调用 `get_session_factory()`，但该模块从未导入此函数。每次停止都抛出 `NameError`，返回 HTTP 500。双摄路由 `routes_sync_recording.py` 有正确的 `from app.database import get_session_factory`。

2. **无实时时间线**：`CaptureConsolePage` 的 "MiniTimeline" 区仅渲染了最近 20 条事件的时间戳胶囊，真正的 `MiniTimeline` 组件（三层轨道 + 非比赛叠加 + 换边标记 + 播放头）从未被导入。同时 `useLiveCoding` 中存在两处调用参数错误和双写风险。

此外，前端停止恢复机制本身也有缺陷：`recovering` 需要手动点击、`operationError` 不可见、状态映射不正确、恢复结果缺少 `tracks`/`videoId`/`analysisAvailable`。

## Goals / Non-Goals

**Goals:**

- 修复 `routes_recording.py` 缺少的 `get_session_factory` 导入，消除停止路由 HTTP 500
- 在 `CaptureConsolePage` 中接入真正的 `MiniTimeline` 组件，替换时间戳胶囊占位
- 修复 `useLiveCoding` 中 `listTimelineEvents` 调用参数错误
- 删除 `addTimelineEvent` 中的双写路径，统一通过 Outbox → coding-actions 写入
- 停止异常后自动查询服务器恢复，减少用户手动交互
- 修复 `operationError` 显示、`RECOVERED` 状态映射、恢复结果完整性

**Non-Goals:**

- 不改动录制核心架构（TrackRecorder / Coordinator / Finalizer）
- 不重新设计 Capture Runtime 状态机
- 不新增独立录制架构
- 不新增后端 API 端点
- 不修改 `MiniTimeline` 组件自身逻辑

**修正 reducer 的状态映射和增加恢复控制元数据不构成"重新设计状态机"，属于本 Change 加固范围。**

## Decisions

### 1. 单摄停止路由修复

**决策**：在 `routes_recording.py` 顶部增加 `from app.database import get_session_factory`，与双摄路由保持一致。不采用局部导入，因为路由函数中多处可能用到数据库会话。

**原因**：最小的单行修复，消除每次停止的 500 错误。这是最高优先级修复。

### 2. MiniTimeline 集成

**决策**：在 `CaptureConsolePage` 的 `recording`、`stopping` 和 `recovering` 阶段渲染 `<MiniTimeline>` 组件，使用 `useLiveCoding` 提供的 `segments`、`events`、`liveCodingState` 和 `elapsedMs`。删除原有时间戳胶囊占位。

**条件**：需要 `runtime.captureTakeId` 存在时才渲染，避免 hydration 阶段无数据。

**播放头行为**：`showDurationHint={runtime.phase === "recording"}`，离开 recording 后计时停止，播放头自然冻结。

**原因**：MiniTimeline 组件已经开发完成并可通过测试，仅缺少页面集成。recovering 阶段保留时间线可避免用户点击停止后时间条突然消失。

### 3. 删除双写路径

**决策**：`addTimelineEvent` 不再直接调用 `createTimelineEvent`，仅通过 Outbox 写入。Outbox sender 通过 `coding-actions` 接口发送，响应更新 `events`/`segments`/`liveState`。

**原因**：同一次按钮点击可能产生两条 DB 记录（一条来自旧 Timeline API，一条来自 coding-actions 响应中的 upsert），导致事件重复。

### 4. 停止自动恢复

**决策**：`STOP_RESULT_UNKNOWN` 进入 `recovering` 后，通过 `useRef` 控制恢复状态，启动带状态控制的自动查询。

**恢复控制状态**：
```ts
const recoveryRef = useRef({
  startedAt: 0,         // 进入 recovering 的时间戳
  attemptCount: 0,       // 查询次数
  inFlight: false,       // 当前是否有查询进行中
  timer: null as ReturnType<typeof setTimeout> | null,  // 定时器引用
});
```

**规则**：
```
进入 recovering
  → startedAt = Date.now(), attemptCount = 0
  → 500ms 后第一次查询

查询结果为 completed/partial/failed
  → 联合 Source Session 恢复完整结果
  → dispatch(RECOVERED)
  → 清理定时器

查询结果为 recording（停止请求未到达服务器）
  → 保持 recovering
  → attemptCount++
  → 3 秒后继续轮询

查询发生网络错误
  → 保持 recovering
  → attemptCount++
  → 更新 operationError
  → 不进入 failed
  → 3 秒后继续

超过 30 秒 (Date.now() - startedAt > 30000)
  → 停止自动高频轮询
  → 仍保持 recovering
  → 显示"再次停止"和"取消录制"按钮
  → 用户点击"再次停止"时再次调用 stop()

手动操作（点击"再次停止"或"取消"）
  → 取消自动定时器
  → 清除 recoveryRef

页面卸载
  → 清理定时器，防止 unmount 后 dispatch
```

**原因**：后端最终化是同步的，最多数十秒完成。自动轮询通常能在几秒内成功。30 秒超时不代表录制失败，只是前端暂时无法确认终态，此时应允许用户再次停止而不是错误进入 failed。

### 5. 恢复结果完整性（联合 Source Session + CaptureTake）

**决策**：在 `captureAdapter.ts` 新增两个纯函数，联合 Source Session 和 CaptureTake 恢复完整结果。

```ts
normalizeRecoveredSingleResult(
  session: RecordingSession,
  take: CaptureTakeSummary,
): NormalizedCaptureStopResult
```

```ts
normalizeRecoveredDualResult(
  session: SyncRecordingSession,
  take: CaptureTakeSummary,
): NormalizedCaptureStopResult
```

**数据来源**：
- 单摄：`video_id`、`duration_sec`、`camera_id`、`capture_take_id`、`auto_analysis_job_id` 均从 Session 恢复
- 双摄：`registered_video_ids`、`default_analysis_video_id`、`camera_slots`、`duration_sec`、`segments`、`total_restarts` 从 Session 恢复

**恢复流程**：
```ts
const sourceSession = await getRecording(sourceSessionId);
const take = await getCaptureTake(sourceSession.capture_take_id);
const result = normalizeRecoveredSingleResult(sourceSession, take);
```

**终态依据**：使用 `take.status` 进入 `completed / partial / failed`，而非 `sourceSession.status`。因为 `partial` 是 CaptureTake 的专有状态，源 Session 只有 `recording / completed / failed / canceled`。

### 6. 合并 Timeline 初始化加载

**决策**：删除 `useLiveCoding` 中第二个独立的 `listTimelineEvents` useEffect，合并为单个初始化流程。

**合并后**：
```ts
useEffect(() => {
  if (!fieldSessionId || !captureTakeId) return;

  Promise.all([
    getLiveCodingState(captureTakeId),
    listSegments(captureTakeId),
    listTimelineEvents(fieldSessionId, {
      capture_take_id: captureTakeId,
    }),
  ]);
}, [fieldSessionId, captureTakeId]);
```

**删除的部分**：当前第二个 effect（仅依赖 `fieldSessionId` 和 `captureTakeId` 加载 Timeline Events）与初始化 effect 重复，删除后消除重复请求。

**原因**：两处加载参数都不正确且调用冗余，修复后若保留两处会导致 Take 初始化时发送两次完全相同的请求。

### 7. 状态映射统一

**决策**：抽取 `phaseFromStopStatus` 函数，统一映射 `NormalizedCaptureStopResult["status"]` → `RuntimePhase`:
- `completed` → `completed`
- `partial` → `partial`
- `failed` / 其他 → `failed`

替换 `RECOVERED` reducer 中硬编码的 `completed` 兜底。

**原因**：当前若后端返回 `failed`，前端会错误地显示为 `completed`，丢失失败状态的视觉反馈。

## Risks / Trade-offs

- [Risk] 自动恢复轮询可能干扰用户主动操作。→ 用户手动点击"再次停止"或"取消"时取消自动轮询；手动恢复仅清理定时器但不改变 recovering 状态。
- [Risk] MiniTimeline 组件在录制初始阶段（`captureTakeId` 刚生成但 segments/events 为空）渲染空白时间线。→ MiniTimeline 已有空状态处理，渲染空轨道但不报错。
- [Risk] 删除直接 Timeline API 写路径不影响存量 Outbox。存量 pending item 本来就是 `CodingOutboxItem`，可继续通过 `executeCodingAction` 正常发送。

## Open Questions

- 无
