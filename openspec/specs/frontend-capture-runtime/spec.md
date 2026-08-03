# frontend-capture-runtime Specification

## Purpose
TBD - created by syncing change unify-single-dual-capture-controller.

## Requirements

### Requirement: 判别联合状态替代双状态机

系统 MUST 使用 `CaptureRuntimeState` 判别联合替代 `consoleState` 和 `dualState` 两个独立状态。状态机包含 `canceled` 和 `recovering` phase。

#### Scenario: 恢复网络不确定性

**变更**：进入 `recovering` 后增加自动恢复机制，无需用户手动点击；恢复结果保留完整媒体和分析入口。

**修改前**：`recovering` 仅显示"重试恢复"按钮等待用户手动操作。`recover()` 恢复时构造的结果固定为空 `tracks`、`analysisAvailable: false`，丢失视频与分析入口。

**修改后**：
- **WHEN** 用户点击停止且 stop API 返回前网络断开
- **THEN** runtime phase MUST 进入 `recovering`（不是 `failed`）
- **AND** 系统 MUST 按 sourceSessionId 查询服务器确认最终状态
- **AND** 系统 SHALL 在进入 recovering 后 500ms 启动第一次查询
- **AND** 系统 SHALL 使用 `recoveryRef` 控制查询状态（查询次数、飞行中标志、定时器引用）
- **AND** 查询成功且终态为 `completed/partial/failed` 时 SHALL 自动进入对应终态
- **AND** 查询结果为 `recording` 时 SHALL 保持 recovering，每 3 秒继续查询
- **AND** 查询发生网络错误时 SHALL 保持 recovering，更新 `operationError`，不进入 `failed`
- **AND** 超过 30 秒后 SHALL 停止自动高频轮询，仍保持 recovering，显示"再次停止"和"取消录制"

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

系统 MUST 使用 `Date.parse(session.startedAt)` 派生 `elapsedMs`，停止后从结果的 track duration 读取。

#### Scenario: 录制中 250ms 刷新

- **WHEN** capturePhase 为 recording
- **THEN** 系统 MUST 每 250ms 刷新 clockNow
- **AND** elapsedMs MUST = clockNow - Date.parse(session.startedAt)

#### Scenario: 停止后从 track duration 读取时长

- **WHEN** phase 为 completed 或 partial
- **THEN** elapsedMs MUST 从 result.tracks[0]?.durationMs 读取
- **AND** MUST NOT 使用时钟计算

#### Scenario: RECOVERED 后从 track duration 读取

- **WHEN** phase 为 recovered
- **THEN** 系统 SHALL 更新 elapsedMs 为 result.tracks[0]?.durationMs ?? 0

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

### Requirement: 恢复结果完整性

系统 SHALL 在恢复阶段联合 Source Session 和 CaptureTake 构造包含媒体、轨道和分析入口的完整停止结果。

**变更**：恢复时联合 Source Session 和 CaptureTake 构造完整结果。

**修改前**：恢复时仅使用 `sourceSession.status` 映射为 `completed`，结果对象固定为 `tracks: []`、`analysisAvailable: false`。

**修改后**：系统 SHALL 联合 Source Session 和 CaptureTake 恢复完整停止结果。
- 系统 SHALL 查询 Source Session 获取媒体信息（`video_id`、`duration_sec`、`camera_id`）
- 系统 SHALL 查询 CaptureTake 获取业务终态（`completed/partial/failed`）
- 系统 SHALL 使用 CaptureTake 的 `status` 决定终态（而非 Source Session 的 `status`）
- `normalizeRecoveredSingleResult` SHALL 从单摄 Session 恢复 `videoId`、`durationMs`、`tracks`、`analysisAvailable`
- `normalizeRecoveredDualResult` SHALL 从双摄 Session 恢复 `registered_video_ids`、`default_analysis_video_id`、`camera_slots`

#### Scenario: 双摄异常结束不伪造完成结果

- **WHEN** 双摄轮询发现 session 异常退出
- **THEN** 系统 MUST 读取真实 session 和 take 状态
- **AND** MUST NOT dispatch 空 CaptureStopResult

### Requirement: 运行状态轮询

前端 SHALL 在 CaptureTake 处于 `recording`、`stopping` 或 `recovering` 阶段时按固定间隔轮询运行状态，并以当前 `captureTakeId` 校验响应归属。

#### Scenario: 录制中轮询

- **WHEN** runtime phase 为 `recording`
- **THEN** 前端 SHALL 以不高于 2 秒的间隔请求运行状态
- **AND** SHALL 使用最新成功响应更新工作台指标

#### Scenario: 过期响应

- **WHEN** 页面已切换到另一个 CaptureTake
- **AND** 旧 Take 的运行状态响应随后返回
- **THEN** 前端 SHALL 丢弃旧响应
- **AND** 不得污染当前页面指标

### Requirement: 运行状态降级

运行状态数据不可用时，前端 SHALL 将每个指标单独显示为 loading、采集中、不可用或错误，不得因为单项指标失败隐藏整个工作台。

#### Scenario: 首次请求尚未返回

- **WHEN** 页面尚未收到任何运行状态快照
- **THEN** 指标区 SHALL 展示稳定的 loading 或 collecting 占位

#### Scenario: 部分指标不可用

- **WHEN** API 返回存储和文件大小但有效帧率为 unavailable
- **THEN** 页面 SHALL 正常展示可用指标
- **AND** 仅将有效帧率标记为不可用

### Requirement: Hydration 孤儿检测与兜底清理

`useCaptureRuntime.hydrate()` 过程中，若通过 `listRecordings` / `listSyncRecordings` 发现 session 已为终态（`failed`/`canceled`/`completed`）但 `GET /api/capture-takes/active` 仍返回活跃记录（CaptureTake 未清理），MUST 提供兜底清理行为。

#### Scenario: session 已自愈为 failed 但 CaptureTake 未清理

- **WHEN** hydrate 调用 `listRecordings({ status: "recording" })` 返回空
- **AND** `listRecordings({ status: "failed" })` 返回该 fieldSessionId 下的 session（表明 session 已被自愈为 failed）
- **BUT** `GET /api/capture-takes/active` 仍返回该录制为活跃
- **THEN** hook SHALL 暴露 `isOrphan: true` 标志
- **AND** runtime phase SHALL 设为 `idle`（不进入 recording 状态）
- **AND** 调用方 MAY 展示「检测到僵尸录制」提示和终止按钮

#### Scenario: session 正常活跃无需兜底

- **WHEN** hydrate 调用 `listRecordings({ status: "recording" })` 找到活跃 session
- **AND** session 有有效的 `capture_take_id`
- **THEN** runtime phase MUST 进入 `recording`
- **AND** `isOrphan` MUST 为 false

### Requirement: 终态停止轮询

前端 SHALL 在 CaptureTake 进入 `completed`、`partial`、`failed` 或 `canceled` 后停止运行状态轮询，并保留最后一次快照用于完成信息展示。

#### Scenario: 正常停止

- **WHEN** runtime phase 进入 `completed`
- **THEN** 前端 SHALL 停止定时器
- **AND** SHALL 展示最后一次后端返回的文件大小、存储和轨道结果
