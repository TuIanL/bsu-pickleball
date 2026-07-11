## MODIFIED Requirements

### Requirement: 采集控制台内录制状态机

系统 SHALL 在采集控制台内部使用统一的 `CaptureRuntimeState` 判别联合驱动 UI（含 `canceled` 和 `recovering`），替代原有的 `preview → recording → stopped`（单摄）和 `setup → testing → recording → stopped`（双摄）两套并行状态机。

#### Scenario: 录制状态统一

- **WHEN** runtime.phase 为 recording
- **THEN** 统一的录制中指示器（不区分单摄/双摄）
- **AND** 统一的停止按钮（不区分 handleStopRecording / handleDualStopRecording）
- **AND** 统一的 Live Coding 面板
- **AND** 统一的 elapsedMs 计时器

#### Scenario: 完成面板统一且保留上下文

- **WHEN** runtime.phase 为 completed 或 partial
- **THEN** 统一的完成面板，从 runtime.result + runtime.session 读取
- **AND** 可访问 fps、auto_analysis_job_id、摄像机名称（不仅仅是 tracks）
- **AND** 不再需要 isDualMode 分支

### Requirement: 双摄采集控制台

系统 SHALL 在 Field Session 的 `camera_setup` 为 `dual` 时展示双摄像头选择界面。预览区通过 `previewTracks[]` 统一渲染。

#### Scenario: 预览区根据轨道数自适应

- **WHEN** tracks.length 为 1 → grid-cols-1
- **WHEN** tracks.length 为 2 → grid-cols-2
- **AND** 不区分单摄和双摄的独立 JSX 分支

## ADDED Requirements

### Requirement: useCaptureRuntime 替代分散的录制 handler

系统 MUST 提供 `useCaptureRuntime` Hook 作为录制生命周期唯一入口。页面使用协调层（freeze → stop → flushWithDeadline）。

#### Scenario: 停止流程由页面协调

- **WHEN** 页面需要停止录制
- **THEN** 页面协调层 MUST 先 liveCoding.freeze()
- **AND** MUST 立即 runtime.stop()（媒体优先）
- **AND** 同时 flushWithDeadline(3000)（best-effort）
- **AND** MUST NOT 存在 handleStopRecording / handleDualStopRecording

#### Scenario: 使用 session-specific polling

- **WHEN** 录制中轮询状态
- **THEN** 系统 MUST 使用 `getRecording(sourceSessionId)` 或 `getSyncRecording(sourceSessionId)`
- **AND** MUST NOT 使用 `/api/sync-recordings/active`
