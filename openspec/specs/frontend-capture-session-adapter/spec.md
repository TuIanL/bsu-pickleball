# frontend-capture-session-adapter Specification

## Purpose
TBD - created by syncing change unify-single-dual-capture-controller.

## Requirements

### Requirement: UnifiedCaptureSession 统一内部表示

系统 MUST 提供 `UnifiedCaptureSession` 类型和 adapter 函数，将 `RecordingSession` 和 `SyncRecordingSession` 转换为统一表示。`started_at` 缺失时 adapter MUST 抛出错误，不使用 `Date.now()` 静默替代。

#### Scenario: 单摄 session 适配

- **WHEN** 调用 `adaptRecordingSession(session)`
- **THEN** sourceType MUST 为 "recording"，mode MUST 为 "single"
- **AND** tracks.length MUST 为 1，tracks[0].slot MUST 为 "single"
- **AND** fps、startedAt MUST 从 session 正确映射

#### Scenario: 双摄 session 适配

- **WHEN** 调用 `adaptSyncRecordingSession(session)`
- **THEN** sourceType MUST 为 "sync_recording"，mode MUST 为 "dual"
- **AND** tracks.length MUST 为 2，slots 为 "cam_1" 和 "cam_2"

#### Scenario: started_at 缺失抛 invariant error

- **WHEN** session.started_at 为 null 或 undefined
- **THEN** adapter MUST 抛出错误
- **AND** MUST NOT 使用 Date.now() 静默替代

### Requirement: CaptureTrackRuntime.trackId 可为空

系统 SHALL 允许启动时 `CaptureTrackRuntime.trackId` 暂时为空，并在停止后从 `result.tracks` 补充该字段。

#### Scenario: 启动时 trackId 为空

- **WHEN** 录制刚开始且 CaptureTrackStopResult 尚未返回
- **THEN** CaptureTrackRuntime.trackId MUST 允许为 undefined
- **AND** slot、cameraId、analysisRole MUST 已填充

#### Scenario: 停止后 trackId 补充

- **WHEN** stop API 返回 CaptureStopResult
- **THEN** 系统 MUST 从 result.tracks 中取 trackId 更新 tracks

### Requirement: NormalizedCaptureStopResult captureTakeId 必填

系统 MUST 提供 `NormalizedCaptureStopResult`，其中 `captureTakeId` 为必填字段。后端 `CaptureStopResult.capture_take` 可选，Normalizer 在缺失时 MUST 进入错误状态。

#### Scenario: capture_take 存在时正常归一

- **WHEN** CaptureStopResult.capture_take 不为 null
- **THEN** NormalizedCaptureStopResult.captureTakeId MUST 取 capture_take.id

#### Scenario: capture_take 缺失时进入错误

- **WHEN** CaptureStopResult.capture_take 为 null 或 undefined
- **THEN** Normalizer MUST NOT 返回空 NormalizedCaptureStopResult
- **AND** MUST 触发 failed 或 recovering 状态
