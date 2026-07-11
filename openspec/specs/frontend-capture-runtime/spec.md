# frontend-capture-runtime Specification

## Purpose
TBD - created by syncing change unify-single-dual-capture-controller.

## Requirements

### Requirement: 判别联合状态替代双状态机

系统 MUST 使用 `CaptureRuntimeState` 判别联合替代 `consoleState` 和 `dualState` 两个独立状态。状态机包含 `canceled` 和 `recovering` phase。

#### Scenario: 恢复网络不确定性

- **WHEN** 用户点击停止且 stop API 返回前网络断开
- **THEN** runtime phase MUST 进入 `recovering`（不是 `failed`）
- **AND** 系统 MUST 按 sourceSessionId 查询服务器确认最终状态
- **AND** 确认后 MUST 进入 `completed`、`partial` 或 `failed`

#### Scenario: 用户主动取消进入 canceled

- **WHEN** 用户点击取消录制
- **THEN** runtime phase MUST 进入 `canceled`
- **AND** MUST NOT 进入 `failed`（用户取消不是录制失败）

#### Scenario: STOP_REQUESTED 不等 API 返回

- **WHEN** runtime.stop() 被调用
- **THEN** dispatch STOP_REQUESTED MUST 在 API 请求之前执行
- **AND** UI MUST 立即进入 stopping（不等网络响应）

#### Scenario: completed 状态保留 session 上下文

- **WHEN** phase 为 completed 或 partial
- **THEN** state.session MUST 保留 UnifiedCaptureSession（不仅仅 result）
- **AND** 完成面板 MUST 可访问 fps、auto_analysis_job_id、摄像机名称

### Requirement: 统一 elapsedMs 从服务器时间派生

系统 MUST 使用 `Date.parse(session.startedAt)` 派生 `elapsedMs`，停止后从 `result.capture_take.duration_ms` 读取。

#### Scenario: 录制中 250ms 刷新

- **WHEN** capturePhase 为 recording
- **THEN** 系统 MUST 每 250ms 刷新 clockNow
- **AND** elapsedMs MUST = clockNow - Date.parse(session.startedAt)

#### Scenario: 停止后从 result 读取时长

- **WHEN** phase 为 completed 或 partial
- **THEN** elapsedMs MUST 从 result.capture_take.duration_ms 读取
- **AND** MUST NOT 使用时钟计算

### Requirement: 统一 start/stop/cancel 接口

系统 MUST 提供 `runtime.start(intent)` / `runtime.stop()` / `runtime.cancel()` 统一接口。`start` 的 intent 为 `CaptureStartIntent` 判别联合。

#### Scenario: start intent 判别

- **WHEN** runtime.start() 被调用且 intent.mode = "single"
- **THEN** intent MUST 包含 cameraId
- **WHEN** runtime.start() 被调用且 intent.mode = "dual"
- **THEN** intent MUST 包含 slots { cam_1, cam_2 }

#### Scenario: TypeScript 阻止非法 intent 组合

- **WHEN** 开发者构造 `{ mode: "single", slots: {...} }`
- **THEN** TypeScript MUST 报编译错误

### Requirement: Runtime 不直接控制 Outbox

Runtime Hook MUST NOT 直接调用 `freeze()` 或 `flushWithDeadline()`。Outbox 冻结和 flush 由页面协调层处理。

#### Scenario: 停止时页面协调 freeze + stop + flush

- **WHEN** 用户点击停止
- **THEN** 页面协调层 MUST 先调用 liveCoding.freeze()
- **AND** MUST 立即调用 runtime.stop()
- **AND** MUST 同时调用 liveCoding.flushWithDeadline(3000)（不阻塞 stop）

### Requirement: session-specific polling 替代全局 active

录制中 MUST 使用按 sourceSessionId 的 session-specific 查询（`getRecording` / `getSyncRecording`），不再使用 `/api/sync-recordings/active`。

#### Scenario: 单摄录制中轮询

- **WHEN** mode 为 single 且 phase 为 recording
- **THEN** 系统 MUST 调用 `getRecording(sourceSessionId)` 轮询状态

#### Scenario: 双摄录制中轮询

- **WHEN** mode 为 dual 且 phase 为 recording
- **THEN** 系统 MUST 调用 `getSyncRecording(sourceSessionId)` 轮询状态

### Requirement: 删除空 CaptureStopResult 伪造

异常恢复 MUST NOT 伪造空的 `CaptureStopResult`（tracks: []）。异常时 MUST 读取真实 session + take，或进入 recovering/failed。

#### Scenario: 双摄异常结束不伪造完成结果

- **WHEN** 双摄轮询发现 session 异常退出
- **THEN** 系统 MUST 读取真实 session 状态
- **AND** MUST NOT dispatch 空 CaptureStopResult
