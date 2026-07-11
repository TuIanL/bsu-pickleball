## Why

Change 1 已建立后端录制生命周期的不变量（CaptureTake 硬保证、CameraLease 持久化、Outbox 解耦、CaptureStopResult 统一返回）。但前端 `CaptureConsolePage.tsx` 仍维护单摄/双摄两套并行的状态机（`consoleState` / `dualState`）、两种 session 类型（`RecordingSession` / `SyncRecordingSession`）、两个计时器（`elapsedSec` / `dualElapsedSec`）和两条停止链路（`handleStopRecording` / `handleDualStopRecording`），导致页面 37 个状态变量通过 `isDualMode ? A : B` 整块 fork，增加逻辑重复和维护成本。

本 Change 统一前端录制生命周期和控制接口，消除双状态机，不重写媒体核心，不做全面组件重构。

## What Changes

### 统一录制生命周期 Hook

- 新增 `useCaptureRuntime` Hook，用判别联合 `CaptureRuntimeState` 替代 `consoleState` + `dualState` 双状态机。
- 统一 `elapsedMs`：从 `Date.parse(session.startedAt)` 派生，单一 250ms 刷新定时器，消除 `elapsedSec` + `dualElapsedSec`。
- 统一 start/stop/cancel 对外接口：`runtime.start()` / `runtime.stop()` / `runtime.cancel()`，内部根据 mode adapter 选择 API。
- 统一 `UnifiedCaptureSession`，通过 `adaptRecordingSession()` / `adaptSyncRecordingSession()` 转换，不再让 `RecordingSession | SyncRecordingSession` 联合类型向子组件传播。

### 拆分协作 Hooks

- `useCameraSetup`：管理单摄/双摄的摄像机配置（selectedCameraId / selectedSlots / slotSelecting），不感知录制生命周期。
- `useCapturePreflight`：管理双摄短录测试 / 摄像头 probe / preflight 结果，`testing` 不进 Runtime 状态机。
- `useLiveCoding`：管理 CaptureTake、Outbox、Timeline、Segments，只依赖 `captureTakeId` + `phase` + `elapsedMs`。

### JSX 结构统一

- 控制栏、计时器、Live Coding 面板、MiniTimeline、完成面板、错误恢复**统一为单套 JSX**，不再出现 `isDualMode ? 单摄分支 : 双摄分支`。
- 预览区统一为 `previewTracks[]` + `grid-cols-N` 布局，消除两种预览组件。
- 保留 mode fork 的区域仅限于：摄像机选择方式、双摄测试按钮。

### 删除旧状态与旧 API handler

- 删除 `consoleState`、`dualState`、`elapsedSec`、`dualElapsedSec`、`elapsedTimer`、`activeRecording`、`activeSyncSession`、`completedRecording`、`dualStopResponse`。
- 删除 `handleStartRecording`、`handleDualStartRecording`、`handleStopRecording`、`handleDualStopRecording`，替换为 `runtime.start()` / `runtime.stop()` / `runtime.cancel()`。

## Capabilities

### New Capabilities

- `frontend-capture-runtime`: 统一前端录制生命周期 Hook（`useCaptureRuntime` + 判别联合 `CaptureRuntimeState`），消除双状态机，统一 start/stop/cancel/elapsedMs/CaptureStopResult
- `frontend-capture-session-adapter`: `UnifiedCaptureSession` + `RecordingSession`/`SyncRecordingSession` 适配器，统一前端内部 session 表示

### Modified Capabilities

- `capture-workflow`: 前端录制控制流从 `isDualMode` 整页 fork 改为统一 `useCaptureRuntime` 驱动；预览区从两种组件改为 `previewTracks[]` 统一布局

## Impact

| 影响范围 | 内容 |
|---------|------|
| `src/pages/CaptureConsolePage.tsx` | 瘦身为页面组合器：组合 4 个 Hooks + 统一 JSX |
| `src/hooks/useCaptureRuntime.ts` | **新增**，核心录制生命周期 Hook |
| `src/hooks/useCameraSetup.ts` | **新增**，摄像机配置 Hook |
| `src/hooks/useCapturePreflight.ts` | **新增**，预检 Hook |
| `src/hooks/useLiveCoding.ts` | **新增**，从 CaptureConsolePage 中提取 |
| `src/types/capture.ts` | **新增**，`UnifiedCaptureSession`、`CaptureTrackRuntime`、`CaptureRuntimeState` |
| `src/components/capture/` | **新增**，统一控制栏/预览/完成面板组件 |
| 构建与依赖 | 不新增运行时依赖；使用现有 `vitest` 和 `npm run build` |
