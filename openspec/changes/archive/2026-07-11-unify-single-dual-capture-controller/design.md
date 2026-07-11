## Context

Change 1 已建立后端录制不变量：CaptureTake 硬保证、CameraLease 持久化、Outbox 解耦、CaptureStopResult 统一返回。但 `CaptureConsolePage.tsx` 仍维护两套并行的状态机和 API 调用链。

当前页面结构：
- 37 个状态变量（31 useState + 6 useRef）
- `isDualMode` 在 3 处整块 fork JSX（预览区、控制面板、完成面板）
- `handleStopRecording` 和 `handleDualStopRecording` 各自实现 drain + API 调用
- `handleStartRecording` 和 `handleDualStartRecording` 各自组装请求参数
- Live Coding 在两套路径中各自初始化

本 Change 只统一前端状态机和 JSX，不修改后端 API、不重构录播核心。

## Goals / Non-Goals

**Goals:**

- 消灭双状态机，统一为 `CaptureRuntimeState` 判别联合（含 `canceled`、`recovering`）。
- 消灭双计时器，统一为 `Date.parse(session.startedAt)` 派生。
- 消灭双 session 类型对外暴露，统一为 `UnifiedCaptureSession`。
- completed/partial 状态保留 `UnifiedCaptureSession`（不仅仅是 `CaptureStopResult`），确保完成面板可访问 source session 上下文。
- 消灭 `isDualMode ? 整块单摄 : 整块双摄`，统一控制栏/计时器/Live Coding/完成面板 JSX。
- Runtime 不直接控制 Outbox：冻结和 flush 由页面级协调层处理。
- 启动参数使用判别联合 `CaptureStartIntent`，避免 `mode=single` 搭配 dual slots 的非法组合。
- 使用 session-specific polling（按 `sourceSessionId` 查询），不再依赖 `/api/sync-recordings/active` 全局端点。

**Non-Goals:**

- 不修改后端 API 路由或返回结构。
- 不重写 Recorder / SyncRecorder。
- 不做全面视觉组件拆分。
- 不支持页面刷新后恢复 active session（若实现复杂度可控可作为增项，不作为硬要求）。
- 不迁移 `modularize-frontend-routing-and-domain-boundaries` 的路由拆分工作。

## Decisions

### 1. Hook 架构：1 核心 + 3 协作 + 1 协调层

**决策**：拆为 4 个 Hook + 页面级协调函数。

```text
useCaptureRuntime     ← 核心：phase、session、elapsedMs、start/stop/cancel
                        不直接引用 Outbox，不直接调用 freeze()
useCameraSetup        ← 摄像机配置唯一所有者（列表、选择、probeResults、previewTracks）
useCapturePreflight   ← 双摄短录测试，slots 变化时自动 reset
useLiveCoding         ← CaptureTake、Outbox、Timeline、Segments
                        输入含 fieldSessionId

页面协调层：
  const handleStop = async () => {
    liveCoding.freeze();
    const stopPromise = runtime.stop();                     // 媒体停止优先
    void liveCoding.flushWithDeadline(3000);                // 后台 best-effort
    await stopPromise;
  };
```

**原因**：Runtime 拥有媒体生命周期，LiveCoding 拥有 Outbox，冻结和 flush 由页面协调。不存在 Runtime → LiveCoding 的隐藏依赖。

### 2. 判别联合状态（含 canceled + recovering）

**决策**：

```ts
type CaptureRuntimeState =
  | { phase: "idle" }
  | { phase: "starting"; intent: CaptureStartIntent }
  | { phase: "recording"; session: UnifiedCaptureSession }
  | { phase: "stopping"; session: UnifiedCaptureSession; operationError?: string }
  | { phase: "recovering"; session: UnifiedCaptureSession; operationError: string }
  | { phase: "completed"; session: UnifiedCaptureSession; result: NormalizedCaptureStopResult }
  | { phase: "partial"; session: UnifiedCaptureSession; result: NormalizedCaptureStopResult }
  | { phase: "failed"; session: UnifiedCaptureSession | null; result: NormalizedCaptureStopResult | null; error: string }
  | { phase: "canceled"; session: UnifiedCaptureSession };

type CaptureMode = "single" | "dual";
```

**关键设计**：
- `completed`/`partial` 保留 `session: UnifiedCaptureSession`，不是只存 `result`。这样完成面板可以访问 `fps`、`auto_analysis_job_id`、摄像机名称等。
- `canceled` 是独立 phase（用户主动取消 ≠ 录制失败）。
- `recovering`：网络不确定性恢复。停止时 API 返回前网络断开 → 进入 recovering → 按 sourceSessionId 查询服务器确认最终状态。
- `stopping` 的 dispatch 在请求发出之前（`STOP_REQUESTED`），避免请求期间 UI 仍显示 recording。

Reducer actions：

```ts
type RuntimeAction =
  | { type: "START"; intent: CaptureStartIntent }
  | { type: "STARTED"; session: UnifiedCaptureSession }
  | { type: "START_FAILED"; error: string }
  | { type: "STOP_REQUESTED" }
  | { type: "STOP_SUCCEEDED"; session: UnifiedCaptureSession; result: NormalizedCaptureStopResult }
  | { type: "STOP_RESULT_UNKNOWN"; error: string }
  | { type: "RECOVERED"; session: UnifiedCaptureSession; result?: NormalizedCaptureStopResult }
  | { type: "CANCEL_REQUESTED" }
  | { type: "CANCELED"; session: UnifiedCaptureSession }
  | { type: "FAILED"; session: UnifiedCaptureSession | null; error: string }
  | { type: "RESET" };
```

**原因**：TypeScript discriminated union 在编译时阻止 `phase=idle` 同时 `session!=null` 等非法组合。`STOP_REQUESTED` 立即更新 UI，不等 API 返回。

**替代方案**：多个 `useState`。拒绝原因：不保证状态原子性。

### 3. UnifiedCaptureSession + NormalizedCaptureStopResult

**决策**：

```ts
type CaptureTrackRuntime = {
  trackId?: string;                     // 启动时可能不存在，停止后从 result.tracks 补充
  slot: "single" | "cam_1" | "cam_2";
  cameraId: string;
  analysisRole: "default" | "supplementary" | "disabled";
};

type UnifiedCaptureSession = {
  sourceType: "recording" | "sync_recording";
  sourceSessionId: string;
  captureTakeId: string;
  mode: "single" | "dual";
  startedAt: string;
  fps: number;
  status: "starting" | "recording" | "stopping" | "completed" | "partial" | "failed" | "canceled";
  tracks: CaptureTrackRuntime[];
  cameraDisplayNames: Record<string, string>;  // cameraId → name
  autoAnalysisJobId?: string;
};

type NormalizedCaptureStopResult = {
  captureTakeId: string;                // 必填（StopResult Normalizer 保证）
  fieldSessionId: string;
  status: string;
  tracks: NormalizedTrackStopResult[];
  analysisAvailable: boolean;
  defaultAnalysisTrackId?: string;
  defaultAnalysisVideoId?: string;
  analysisBlockedReason?: string;
  warnings: string[];
};
```

Adapter 转换 `started_at` 缺失时必须抛出 invariant error，不使用 `Date.now()` 静默替代。

**原因**：`trackId` 在启动时不可得（只在 `CaptureTrackStopResult` 中返回），必须允许为可选。`NormalizedCaptureStopResult` 确保 `captureTakeId` 必填。

### 4. Session-polling 替代全局 active 轮询

**决策**：录制中始终按已知 ID 轮询。

```text
single: getRecording(sourceSessionId)
dual:   getSyncRecording(sourceSessionId)
```

不再使用 `/api/sync-recordings/active`。

**原因**：global active 没有 FieldSession 过滤条件，且只适用于双摄。session-specific 轮询对单摄和双摄统一。

### 5. 启动参数：CaptureStartIntent

**决策**：

```ts
type CaptureStartIntent =
  | { mode: "single"; cameraId: string; fps: number; autoAnalyze: boolean }
  | { mode: "dual"; slots: { cam_1: string; cam_2: string }; fps: number; autoAnalyze: boolean };
```

调用：

```ts
runtime.start({
  ...cameraSetup.startIntent,
  fps: recordingFps,
  autoAnalyze: analysisIntent === "auto_analyze",
});
```

FieldSession 通过回调处理：

```ts
useCaptureRuntime({
  fieldSessionId,
  onFieldSessionStarted: (fs) => setFieldSession(fs),
});
```

**原因**：discriminated union 阻止 `mode=single` 搭配 dual slots 的非法组合。

### 6. CameraSetup 唯一所有权

**决策**：`useCameraSetup` 是摄像机相关状态的唯一所有者。

```ts
useCameraSetup({ sessionId, mode })
  → 摄像机列表加载/注册/删除/刷新
  → probeResults
  → 单摄 selectedCameraId / 双摄 selectedSlots + slotSelecting
  → sessionStorage 持久化
  → previewTracks
  → startIntent (CaptureStartIntent)
  → isReady
```

`useCapturePreflight` 只负责：
- `preflightState` + `testResult`
- `runTest()`（依赖 cameraSetup.startIntent 中的 slots）
- slots 变化时自动 `resetPreflight()`

设备抽屉（drawerOpen/drawerTab/newCameraForm）留在页面，属于临时 UI 状态。

**原因**：消除 probe、cameras、slots 三处所有权矛盾。

### 7. Live Coding 输入完整化

**决策**：

```ts
useLiveCoding({
  fieldSessionId,
  captureTakeId,       // 由 runtime selector 提供：recording→session.captureTakeId, completed→result.captureTakeId
  phase,
  elapsedMs,
})
```

captureTakeId 变化时自动：
- 终止旧 sender
- 清空旧 timeline/segments
- 获取 live state + 恢复 pending outbox
- 创建新 sender
- 忽略旧异步请求的迟到结果（防串线）

保留 `captureTakeIdRef`、`revisionRef`、`liveCodingStateRef` 等内部 ref。

**原因**：当前 Timeline 加载需要 `field_session_id`，Take 切换需要 ref 防串线。

### 8. 渐进迁移：先单摄，再双摄

**决策**：

```text
阶段 A：单摄 → 新 Runtime，双摄 → 旧逻辑
阶段 B：单摄 + 双摄 → 新 Runtime
阶段 C：删除全部旧状态和旧 handler
```

不要单摄同时更新旧 state 和新 reducer（双真相源）。

### 9. 页面行为保护测试

**决策**：Step 0 包含真正的组件级契约测试，不只是 reducer 单测。

使用已有 Vitest + React Testing Library + jsdom：
- 单摄 start → recording → Live Coding 初始化 → stop → 完成面板
- 双摄选择 slots → 短录测试 → start → stop → 完成面板
- Outbox：点击停止 → freeze 立即发生 → stop API 不等 flush → pending 提示保留
- 恢复：stop API 网络错误 → recovering → 查询 session 最终状态
- 完成面板：自动分析入口不消失，参数保留 sessionId/fps/videoId

## Risks / Trade-offs

- [Risk] `UnifiedCaptureSession.startedAt` 必填，但 `SyncRecordingSession.started_at` 类型为可选。→ Mitigation：Adapter 中 `started_at` 缺失时抛 invariant error，不使用 `Date.now()` 静默替代。
- [Risk] completed 状态保留 `UnifiedCaptureSession` 增加了 reducer 复杂度。→ Mitigation：停止后立即调用 `getRecording/getSyncRecording` 刷新 session 后再 dispatch `STOP_SUCCEEDED`。
- [Risk] `NormalizedCaptureStopResult` 要求 `captureTakeId` 必填，但后端 `CaptureStopResult.capture_take` 是可选的。→ Mitigation：在 Normalizer 中检测，缺失时进入 `failed` 或 `recovering`，不静默跳过。
- [Risk] 当前双摄轮询在异常结束时伪造空 `CaptureStopResult`。→ Mitigation：删除此伪造逻辑；异常恢复时读取真实 session + take，或进入 `recovering/failed`。
- [Risk] 单摄和双摄在迁移期间不能同时由新旧状态驱动。→ Mitigation：阶段 A 只把单摄切到新 Runtime，双摄保持旧逻辑，不混用。

## Migration Plan

1. Step 0：编写页面行为保护测试（组件测试、outbox 停止测试、完成面板测试）
2. Step 1：新增统一类型 + Normalizer + Adapter
3. Step 2：纯 reducer 实现 + reducer 状态转换测试
4. Step 3：`useCaptureRuntime`（媒体生命周期，不引用 Outbox）
5. Step 4：单摄迁移（单摄切到 Runtime，双摄保持旧逻辑）
6. Step 5：双摄迁移（删除全局 active 轮询，改为 session-specific polling）
7. Step 6：提取 `useLiveCoding` + `useCameraSetup` + `useCapturePreflight`
8. Step 7：统一公共 JSX（控制栏、计时器、完成面板、预览区）
9. Step 8：删除旧状态、旧 handler、旧计时器
10. Step 9：验证 `npm run test` + `npm run build`
